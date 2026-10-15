from datetime import datetime, timezone

from app.deps import get_settings
from app.schemas import CADResult, Draft, FinalReport, Issue

CASES: dict[str, FinalReport] = {}   # in-memory case store (prototype)


def _bullets(items: list[str], empty: str = "None identified.") -> str:
    cleaned = [i.strip() for i in items if i and i.strip()]
    return "\n".join(f"- {i}" for i in cleaned) if cleaned else empty


def _cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")


def assemble(case_id: str, draft: Draft, cad: CADResult, issues: list[Issue], verified: bool) -> FinalReport:
    rounds = get_settings().critic_max_rounds
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = ["# CONSILIUM — Glaucoma Screening Report", ""]
    if not verified:
        lines += [
            f"> ⚠️ UNVERIFIED — critic did not approve after {rounds} rounds; "
            "unresolved issues listed below.",
            "",
        ]
    status_text = "Verified by adversarial critic" if verified else "Unverified — see unresolved issues"
    lines += [
        f"**Case:** `{case_id}` · **Laterality:** {cad.laterality} · **Generated:** {stamp}",
        "",
        f"**Status:** {status_text}",
        "",
        "## Impression",
        draft.impression.strip(),
        "",
        "## Findings",
        _bullets(draft.findings),
        "",
        "## Recommendations",
        _bullets(draft.recommendations),
        "",
        "## Disagreements",
        _bullets(draft.disagreements),
        "",
        "## Caveats",
        _bullets(draft.caveats),
        "",
        "## CAD Summary",
        "| Metric | Value |",
        "|---|---|",
        f"| Glaucoma probability (model output) | {cad.p_glaucoma:.2f} |",
        f"| Screening grade | {_cell(cad.grade)} |",
        f"| Cup-to-disc ratio (CDR) | {f'{cad.cdr:.2f}' if cad.cdr is not None else 'unavailable'} |",
        f"| Image quality | {_cell(cad.quality_note)} |",
        f"| Laterality | {cad.laterality} |",
        "",
    ]
    if not verified and issues:
        lines += [
            "## Unresolved Critic Issues",
            "\n".join(f"- **{i.kind}**: {i.detail}" for i in issues),
            "",
        ]
    lines += ["---", "*Screening support only — requires clinician review.*"]

    return FinalReport(
        case_id=case_id,
        status="verified" if verified else "unverified_after_3_rounds",
        report_markdown="\n".join(lines),
        draft=draft,
        cad=cad,
        open_issues=[] if verified else issues,
    )


def save(report: FinalReport) -> None:
    CASES[report.case_id] = report