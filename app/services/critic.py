import re

from app.deps import get_settings
from app.schemas import Draft, Issue, Verdict
from app.services import director
from app.services.llm import generate_json, load_prompt, render_facts

NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
CDR_RE = re.compile(r"(?:\bCDR\b|cup[- ]to[- ]disc(?: ratio)?)\D{0,30}?(\d*\.?\d+)", re.I)
GRADES = ["no glaucoma", "possible glaucoma", "likely glaucoma", "glaucoma detected"]

FORBIDDEN = [
    (re.compile(r"patient has glaucoma", re.I), "definitive statement that the patient has glaucoma"),
    (re.compile(r"\bdiagnosed\b", re.I), "the word 'diagnosed' (implies a definitive diagnosis)"),
    (re.compile(r"\d+(?:\.\d+)?\s?(?:mg|mcg)\b|\d+(?:\.\d+)?\s?%", re.I), "dose or percentage pattern"),
]


def _all_text(d: Draft) -> str:
    return "\n".join([d.impression, *d.findings, *d.recommendations, *d.disagreements, *d.caveats])


def deterministic_checks(draft: Draft, facts: dict[str, str]) -> list[Issue]:
    """Cheap, exact checks that run BEFORE the LLM check. `facts` = CAD facts + note facts."""
    issues: list[Issue] = []

    # (a) every number in impression/findings must appear in the source facts (±0.01)
    allowed = {float(n) for v in facts.values() for n in NUM_RE.findall(v)}
    seen: set[str] = set()
    for n in NUM_RE.findall("\n".join([draft.impression, *draft.findings])):
        if n in seen:
            continue
        seen.add(n)
        if not any(abs(float(n) - a) <= 0.01 for a in allowed):
            issues.append(Issue(
                kind="numeric_mismatch",
                detail=f"The number {n} in the impression/findings does not appear in the source facts.",
            ))

    # (b) forbidden phrases anywhere in the draft
    text = _all_text(draft)
    for rx, label in FORBIDDEN:
        m = rx.search(text)
        if m:
            issues.append(Issue(
                kind="unsafe_language",
                detail=f"Forbidden wording: {label} — found '{m.group(0)}'.",
            ))

    # (c) caveats non-empty and quality note echoed
    if not any(c.strip() for c in draft.caveats):
        issues.append(Issue(kind="omission", detail="The caveats list is empty."))
    quality = facts.get("quality", "").strip().lower()
    if quality and quality not in " ".join(draft.caveats).lower():
        issues.append(Issue(
            kind="omission",
            detail=f"Caveats must echo the image quality note verbatim: '{facts['quality']}'.",
        ))

    # (d) CDR and grade in findings must match the CAD facts
    findings_text = "\n".join(draft.findings)
    cdr_fact = facts.get("cdr")
    for m in CDR_RE.finditer(findings_text):
        try:
            cited = float(m.group(1))
        except ValueError:
            continue
        if cdr_fact is None:
            issues.append(Issue(kind="unsupported",
                                detail=f"Findings cite a CDR of {cited}, but no CDR is available."))
        elif abs(cited - float(cdr_fact)) > 0.01:
            issues.append(Issue(kind="numeric_mismatch",
                                detail=f"Findings cite a CDR of {cited}; the source CDR is {cdr_fact}."))
    expected_grade = facts.get("grade", "").lower()
    if expected_grade:
        lowered = findings_text.lower().replace("no glaucoma detected", "no glaucoma")
        for g in GRADES:
            if g != expected_grade and g in lowered:
                issues.append(Issue(
                    kind="unsupported",
                    detail=f"Findings mention the grade '{g}', but the source grade is '{expected_grade}'.",
                ))
    return issues


async def llm_check(draft: Draft, facts: dict[str, str]) -> Verdict:
    block = (
        "SOURCE FACTS (ground truth):\n" + render_facts(facts)
        + "\n\nDRAFT REPORT (JSON):\n" + draft.model_dump_json(indent=2)
    )
    return await generate_json(load_prompt("critic"), block, Verdict)


def _merge(det: list[Issue], verdict: Verdict) -> list[Issue]:
    merged: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for iss in [*det, *verdict.issues]:
        key = (iss.kind, iss.detail.strip().lower())
        if key not in seen:
            seen.add(key)
            merged.append(iss)
    if not merged and not verdict.approved:
        merged.append(Issue(kind="unsupported",
                            detail="The critic rejected the draft without specifying an issue."))
    return merged


async def audit_loop(draft: Draft, facts: dict[str, str]) -> tuple[Draft, list[Issue], bool]:
    """Audit -> (reject -> Director revises -> audit) up to critic_max_rounds revisions."""
    max_rounds = get_settings().critic_max_rounds
    issues: list[Issue] = []
    for attempt in range(max_rounds + 1):
        det = deterministic_checks(draft, facts)   # deterministic first
        verdict = await llm_check(draft, facts)    # then the LLM entailment check
        issues = _merge(det, verdict)
        if not issues:
            return draft, [], True
        if attempt == max_rounds:
            break
        draft = await director.revise(draft, issues, facts)
    return draft, issues, False