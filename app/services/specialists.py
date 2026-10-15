import asyncio

from app.schemas import SubReport
from app.services.llm import AgentError, generate_json, load_prompt, render_facts

ROLES = ("ophthalmologist", "optometrist", "pharmacist")


async def _run_role(role: str, facts: dict[str, str]) -> SubReport:
    system = load_prompt(role)
    block = render_facts(facts) or "(no facts provided)"
    last: AgentError | None = None
    for _ in range(2):  # one failure -> retry this role once -> else raise
        try:
            sub = await generate_json(system, block, SubReport)
            sub.role = role  # never trust the model for the role label
            return sub
        except AgentError as e:
            last = e
    raise AgentError(f"{role} agent failed twice: {last}")


async def run_specialists(routed: dict[str, dict[str, str]]) -> list[SubReport]:
    results = await asyncio.gather(*(_run_role(role, routed[role]) for role in ROLES))
    return list(results)