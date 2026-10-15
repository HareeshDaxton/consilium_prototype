import re

from app.schemas import CADResult, RawVisionOutput


def grade(p: float) -> str:
    """Paper §B mapping."""
    if p < 0.2:
        return "no glaucoma"
    if p < 0.5:
        return "possible glaucoma"
    if p < 0.9:
        return "likely glaucoma"
    return "glaucoma detected"


def build_cad_context(raw: RawVisionOutput, laterality: str = "UNKNOWN") -> CADResult:
    p = min(max(raw.glaucoma_probability, 0.0), 1.0)
    cdr = raw.cdr if raw.cdr is not None and 0.0 < raw.cdr <= 1.0 else None
    quality = (raw.note or "").strip() or "image gradable"
    if cdr is None:
        quality += "; CDR unavailable"
    return CADResult(
        p_glaucoma=p,
        grade=grade(p),
        cdr=cdr,
        quality_note=quality,
        laterality=laterality,
    )


def cad_facts(cad: CADResult) -> dict[str, str]:
    """Flat string view of the CAD context (what the router and critic consume)."""
    facts = {
        "glaucoma_probability": f"{cad.p_glaucoma:.2f}",
        "grade": cad.grade,
    }
    if cad.cdr is not None:
        facts["cdr"] = f"{cad.cdr:.2f}"
    facts["quality"] = cad.quality_note
    facts["laterality"] = cad.laterality
    return facts


# ---------------------------------------------------------------------------
# Medical note parsing (regex only, no LLM)
# ---------------------------------------------------------------------------
_IOP_RE = re.compile(r"\bIOP\s*(?:(OD|OS|OU)\s*)?[:=]?\s*(\d+(?:\.\d+)?)", re.I)
_AGE_RES = [
    re.compile(r"\b(\d{1,3})\s*[- ]?\s*(?:year|yr)s?[- ]?old\b", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:y/o|yo)\b", re.I),
    re.compile(r"\bage\s*[:=]?\s*(\d{1,3})\b", re.I),
]

_LABELS = {
    "medications": re.compile(r"^(?:medications?|meds)\s*[:=]\s*(.+)$", re.I),
    "intolerances": re.compile(
        r"^(?:intoleran(?:ce|ces)|drug allerg(?:y|ies)|allerg(?:y|ies))\s*[:=]\s*(.+)$", re.I
    ),
    "comorbidities": re.compile(
        r"^(?:comorbidit(?:y|ies)|pmh|past medical history)\s*[:=]\s*(.+)$", re.I
    ),
    "prior_dx": re.compile(
        r"^(?:prior dx|prior diagnos[ie]s|previous diagnos[ie]s)\s*[:=]\s*(.+)$", re.I
    ),
    "exam_findings": re.compile(r"^(?:exam(?:ination)? findings?|findings)\s*[:=]\s*(.+)$", re.I),
}
# Pharmacist-only material: stripped out of the free text so the other roles can't see it.
_PRIVATE_KEYS = {"medications", "intolerances", "comorbidities"}


def parse_note(note: str | None) -> dict[str, str]:
    """Extract structured facts from the optional note. Returns only keys that were found."""
    if not note or not note.strip():
        return {}
    note = note.strip()
    facts: dict[str, str] = {}

    m = _IOP_RE.search(note)
    if m:
        eye = f"{m.group(1).upper()} " if m.group(1) else ""
        facts["iop"] = f"{eye}{m.group(2)} mmHg"

    for rx in _AGE_RES:
        m = rx.search(note)
        if m:
            facts["age"] = m.group(1)
            break

    kept: list[str] = []
    for seg in re.split(r"(?<=[.;])\s+|\n+", note):
        seg = seg.strip()
        if not seg:
            continue
        matched_private = False
        for key, rx in _LABELS.items():
            m = rx.match(seg)
            if m:
                facts[key] = m.group(1).strip().rstrip(".;").strip()
                matched_private = key in _PRIVATE_KEYS
                break
        if not matched_private:
            kept.append(seg)

    free = " ".join(kept).strip()
    if free:
        facts["note_free_text"] = free

    order = ["iop", "age", "prior_dx", "exam_findings", "medications",
             "intolerances", "comorbidities", "note_free_text"]
    return {k: facts[k] for k in order if k in facts}