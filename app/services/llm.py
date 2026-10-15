import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from openai import OpenAIError
from pydantic import BaseModel, ValidationError

from app.deps import get_openai, get_settings

T = TypeVar("T", bound=BaseModel)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

COMMON_RULES = (
    "You are one role on a screening panel. Use ONLY the facts in the data block. "
    "Screening-support language only — never state a definitive diagnosis, never give doses "
    "or drug regimens. Never use the word 'diagnosed' (write 'documented history of' instead) "
    "and never write a number followed by mg, mcg or %. Express probabilities as decimals "
    "(e.g. 0.82)."
)


class AgentError(Exception):
    """An agent call failed (API error or invalid output after the repair retry)."""


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def render_facts(facts: dict[str, str]) -> str:
    return "\n".join(f"{k} = {v}" for k, v in facts.items())


def _summarise(err: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or '(root)'}: {e['msg']}" for e in err.errors())


async def generate_json(system: str, data_block: str, response_model: type[T]) -> T:
    settings = get_settings()
    try:
        client = get_openai()
    except RuntimeError as e:
        raise AgentError(str(e)) from e

    schema = json.dumps(response_model.model_json_schema())
    full_system = (
        f"{COMMON_RULES}\n\n{system}\n\n"
        f"Respond with a single JSON object that conforms to this JSON schema "
        f"(no markdown, no commentary):\n{schema}"
    )
    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": data_block},
    ]

    for attempt in range(2):  # first try + ONE repair retry
        try:
            resp = await client.chat.completions.create(
                model=settings.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except OpenAIError as e:
            raise AgentError(f"LLM request failed ({type(e).__name__})") from e

        raw = resp.choices[0].message.content or ""
        try:
            return response_model.model_validate_json(raw)
        except ValidationError as e:
            messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Your previous JSON failed validation: {_summarise(e)}. "
                        "Return the corrected JSON object only."
                    ),
                },
            ]
    raise AgentError(f"{response_model.__name__} output was invalid after one repair retry")