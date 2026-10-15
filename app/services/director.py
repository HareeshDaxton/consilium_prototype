from app.schemas import Draft, Issue, SubReport
from app.services.llm import generate_json, load_prompt, render_facts


def _subreports_block(subreports: list[SubReport]) -> str:
    parts = []
    for s in subreports:
        parts.append(
            f"[{s.role}]\n"
            f"observations: {s.observations}\n"
            f"recommendations: {s.recommendations}\n"
            f"uncertainties: {s.uncertainties or '(none stated)'}"
        )
    return "\n\n".join(parts)


async def draft(subreports: list[SubReport], cad_facts: dict[str, str]) -> Draft:
    block = (
        "FACTS:\n" + render_facts(cad_facts)
        + "\n\nSUB-REPORTS:\n" + _subreports_block(subreports)
    )
    d = await generate_json(load_prompt("director"), block, Draft)
    d.revision = 0
    return d


async def revise(current: Draft, issues: list[Issue], facts: dict[str, str]) -> Draft:
    numbered = "\n".join(f"{i}. [{iss.kind}] {iss.detail}" for i, iss in enumerate(issues, 1))
    block = (
        "FACTS:\n" + render_facts(facts)
        + "\n\nCURRENT DRAFT (JSON):\n" + current.model_dump_json(indent=2)
        + "\n\nCRITIC ISSUES:\n" + numbered
    )
    d = await generate_json(load_prompt("director_revise"), block, Draft)
    d.revision = current.revision + 1
    return d