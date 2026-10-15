# CONSILIUM — Prototype Build Specification (`consilium_prototype`)

**Status:** Deadline build · **Goal:** a working end-to-end demo, not production. **Target builder:** Claude Code / Antigravity (free tier).

> **Read first:** This is a *prototype* of the CONSILIUM paper pipeline. The full production design lives in `ARCHITECTURE.md` / `AGENTS.md` — **ignore those files for this build**. Do not add guardrails (NeMo), Langfuse, OpenTelemetry, Postgres, Docker, or anything not listed here. Build exactly what this file says, in the order of §8.

---

## 1. What the prototype does (user-visible flow)

```
1. User opens site → Landing page with "Sign in with Google"
2. Google sign-in → verified by backend → session cookie
3. Main page → user uploads a fundus image + optional medical note → clicks "Generate Report"
4. Backend pipeline (§2) runs → structured report returned
5. Report rendered on page → "Export PDF" button downloads it
```

If the friend's vision endpoint is unreachable, the app must still demo: a `VISION_MODE=mock` env switch returns synthetic CAD results so every other stage is exercisable.

---

## 2. Pipeline (exactly this, nothing more)

```
Fundus image ──┐
               ├── friend's vision FastAPI (via ngrok URL in .env)
Medical note ──┘        returns: glaucoma probability + disc/cup masks
        │
   CAD CONTEXT (backend computes: probability grade, CDR, quality note)
        │
  CONTEXT ROUTER (hardcoded role→facts dict)
     ↙        ↓         ↘
Ophthalmologist   Optometrist   Pharmacist        ← gpt-4o-mini, parallel, isolated sub-contexts
     └────────┬────────┘
        DIRECTOR (gpt-4o-mini)                     ← unified draft
             │
  ADVERSARIAL CRITIC (gpt-4o-mini)                 ← deterministic checks FIRST, then LLM check
             │   ↺ reject → Director revises (max 3 rounds)
        FINAL REPORT (Markdown + structured JSON)
```

Model: `gpt-4o-mini` for all four agent roles (one env var, configurable). JSON-mode structured outputs, Pydantic-validated, ONE repair retry per agent, then fail with a visible error.

---

## 3. Environment / setup (already partly present)

Existing files in `consilium_prototype/`: `.venv/`, `.env`, `.gitignore`, `.python-version`, `main.py`, `pyproject.toml`, `README.md`.

`.env` (fill in; add `.env.example` with the same keys and empty values):

```bash
OPENAI_API_KEY=sk-...                 # already present
SWINV2_AND_SEGFORMER_LINK=https://pasta-hankyanky-grunt.ngrok-free.dev   # friend's FastAPI base URL (no trailing /docs)
VISION_MODE=live                      # live | mock
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com   # Google OAuth client (Web app type)
SESSION_SECRET=any-long-random-string
```

Python ≥3.11, manage with `uv` (`.venv` already exists). Required deps to add to `pyproject.toml`: `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx`, `openai`, `pydantic`, `pydantic-settings`, `google-auth`, `itsdangerous`, `python-dotenv`. **No torch, no GPU, no DB.**

---

## 4. Full project file structure (build exactly this)

```
consilium_prototype/
├── .env                        # exists — keys above
├── .env.example                # same keys, empty values
├── .gitignore                  # exists — ensure .env and .venv are ignored
├── .python-version             # exists
├── pyproject.toml              # exists — add deps from §3
├── README.md                   # exists — update with run instructions (§7)
├── main.py                     # EXISTS — replace with thin entry (§6, file 1)
├── app/
│   ├── __init__.py             # empty
│   ├── config.py               # Settings (pydantic-settings) — reads .env
│   ├── main.py                 # FastAPI app: mount static, include routers, CORS not needed
│   ├── auth.py                 # Google ID-token verify + signed session cookie (itsdangerous)
│   ├── schemas.py              # all Pydantic models (§5)
│   ├── deps.py                 # singletons: OpenAI client, vision client, settings
│   ├── routers/
│   │   ├── __init__.py         # empty
│   │   ├── auth_routes.py      # POST /api/auth/google, POST /api/auth/logout, GET /api/me
│   │   └── case_routes.py      # POST /api/cases, GET /api/cases/{case_id}
│   ├── services/
│   │   ├── __init__.py         # empty
│   │   ├── vision_client.py    # VisionClient protocol + HttpVisionClient + MockVisionClient
│   │   ├── cad.py              # CAD context builder: grade mapping, CDR from masks, context dict
│   │   ├── router.py           # context router: role → allowed facts (hardcoded dict)
│   │   ├── llm.py              # gpt-4o-mini JSON-mode wrapper, 1 repair retry, Pydantic parse
│   │   ├── specialists.py      # 3 specialist agents (parallel via asyncio.gather)
│   │   ├── director.py         # draft + revise
│   │   ├── critic.py           # deterministic checks + LLM critic + merge + loop (max 3)
│   │   └── report.py           # final report assembly (Markdown + JSON), case store (in-memory)
│   └── prompts/
│       ├── ophthalmologist.txt
│       ├── optometrist.txt
│       ├── pharmacist.txt
│       ├── director.txt
│       ├── director_revise.txt
│       └── critic.txt
├── static/
│   ├── index.html              # SPA: landing view + login view + app view (one file, sections toggled)
│   ├── css/style.css
│   └── js/app.js               # Google sign-in, upload, poll, render report, export PDF (html2pdf.js CDN)
└── tests/
    ├── test_cad.py             # CDR math on synthetic masks
    └── test_router.py          # router isolation (facts not allowed don't appear)
```

That's **24 files**. Nothing outside this tree.

---

## 5. Contracts (Pydantic models in `app/schemas.py`)

```python
class CADResult(BaseModel):            # built in services/cad.py
    p_glaucoma: float                  # 0..1 from vision endpoint (raw)
    grade: str                         # "no glaucoma" | "possible glaucoma" | "likely glaucoma" | "glaucoma detected"
    cdr: float | None                  # cup-to-disc ratio from masks; None if masks unusable
    quality_note: str                  # short note, e.g. "image gradable" or flags
    laterality: str = "UNKNOWN"        # "OD" | "OS" | "UNKNOWN"

class RawVisionOutput(BaseModel):      # wire format from friend's endpoint (adapt in vision_client)
    glaucoma_probability: float
    disc_mask_b64: str | None = None   # base64 PNG or RLE — pick ONE, document it
    cup_mask_b64: str | None = None
    note: str | None = None

class SubReport(BaseModel):
    role: str                          # ophthalmologist | optometrist | pharmacist
    observations: str                  # prose, ≤ 250 words, role-scoped
    recommendations: str               # prose, role-scoped
    uncertainties: str = ""

class Draft(BaseModel):
    impression: str
    findings: list[str]
    recommendations: list[str]
    disagreements: list[str] = []      # preserved dissent — do NOT smooth over
    caveats: list[str]                 # must echo quality_note + any disagreements
    revision: int = 0

class Issue(BaseModel):
    kind: str                          # numeric_mismatch | unsupported | omission | unsafe_language
    detail: str

class Verdict(BaseModel):
    approved: bool
    issues: list[Issue] = []

class FinalReport(BaseModel):
    case_id: str
    status: str                        # "verified" | "unverified_after_3_rounds"
    report_markdown: str
    draft: Draft
    cad: CADResult
    open_issues: list[Issue] = []      # empty when verified
```

---

## 6. Per-file build notes (what each file must contain)

**1. `main.py` (root, replace existing) — thin entry only:**
```python
import uvicorn
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

**2. `app/config.py`** — `Settings(BaseSettings)`: `openai_api_key`, `vision_link` (env `SWINV2_AND_SEGFORMER_LINK`), `vision_mode: Literal["live","mock"]`, `google_client_id`, `session_secret`, `model: str = "gpt-4o-mini"`, `critic_max_rounds: int = 3`. Env file `.env`.

**3. `app/main.py`** — `app = FastAPI()`, `app.mount("/static", StaticFiles(directory="static"), name="static")`, `@app.get("/")` → `FileResponse("static/index.html")`, include both routers, `@app.middleware` that enforces session on `/api/cases*` (else 401 JSON).

**4. `app/auth.py`** — `verify_google_token(id_token: str) -> dict` using `google.oauth2.id_token.verify_oauth2_token(id_token, requests, GOOGLE_CLIENT_ID)`; raises on failure. Session = itsdangerous `URLSafeSerializer` cookie `consilium_session` holding `{email, name, picture}`; 24h expiry.

**5. `app/schemas.py`** — models from §5 verbatim.

**6. `app/deps.py`** — lazily-built singletons: `get_settings()`, `get_openai()`, `get_vision()` (returns `MockVisionClient` when `vision_mode=="mock"`).

**7. `app/routers/auth_routes.py`** —
- `POST /api/auth/google` body `{id_token}` → verify → set cookie → `{email, name, picture}`.
- `POST /api/auth/logout` → clear cookie.
- `GET /api/me` → session payload or 401.

**8. `app/routers/case_routes.py`** —
- `POST /api/cases` — multipart: `image` (file), `note` (text, optional), `laterality` (form field, optional). Validates image (JPEG/PNG, ≤ 20MB), note length cap 4000 chars. Creates `case_id = uuid4()`, runs the pipeline **synchronously** (prototype: fine for demo, one case at a time), returns `FinalReport`. Store in the in-memory case store so `GET` can refetch.
- `GET /api/cases/{case_id}` → stored `FinalReport` (404 otherwise).
- Wrap pipeline exceptions → `500` with a clean JSON error (never leak stack traces or the API key).

**9. `app/services/vision_client.py` —**
```python
class VisionClient(Protocol):
    async def predict(self, image_bytes: bytes) -> RawVisionOutput: ...

class HttpVisionClient:      # POST f"{settings.vision_link}/predict" multipart image
                             # timeout 120s; on connection error/5xx raise VisionUnavailable
class MockVisionClient:      # deterministic fake: p=0.82, synthetic masks (concentric circles,
                             # CDR 0.62), note "MOCK vision output"
```
Keep the HTTP payload parsing tolerant: accept the documented fields; if the friend's shape differs, adjust **only** this file. Masks: agree ONE format with the friend — recommended base64 PNG at fixed 512×512 (simplest to decode with Pillow... *no* — keep zero extra deps: ask friend for **RLE arrays** or **CDR precomputed + mask PNGs base64**; decode with `PIL` only if `pillow` added; simplest contract: ask friend to also return `cdr` directly).

**📌 Vision endpoint contract to send your friend (ask them to make their FastAPI return exactly this):**
```json
POST {SWINV2_AND_SEGFORMER_LINK}/predict      (multipart: file=<image>)
200 {
  "glaucoma_probability": 0.91,
  "cdr": 0.62,                ← computed server-side on his GPU; saves us mask decoding
  "masks_available": true,
  "note": "gradable"
}
```
Then `cad.py` uses `cdr` directly; masks stay optional (nice for overlay later, not required).

**10. `app/services/cad.py`** —
- `grade(p)` mapping (paper §B): `p<0.2 → "no glaucoma"`, `0.2–0.5 → "possible glaucoma"`, `0.5–0.9 → "likely glaucoma"`, `≥0.9 → "glaucoma detected"`.
- `build_cad_context(raw: RawVisionOutput) -> CADResult` + a `facts: dict[str, str]` view, e.g. `{"glaucoma_probability": "0.91", "grade": "...", "cdr": "0.62", "quality": "...", "laterality": "..."}`.

**11. `app/services/router.py`** — hardcoded dict (the paper's Table):
```python
ROLE_FACTS = {
 "ophthalmologist": ["glaucoma_probability", "grade", "cdr", "quality", "laterality",
                     "iop", "exam_findings", "prior_dx", "age", "note_free_text"],
 "optometrist":     ["glaucoma_probability", "grade", "cdr", "quality", "laterality",
                     "iop", "exam_findings", "prior_dx", "age", "note_free_text"],
 "pharmacist":      ["grade", "laterality", "age", "iop", "prior_dx",
                     "medications", "intolerances", "comorbidities"],
}
def route(cad_facts, note_facts) -> dict[str, dict[str, str]]   # deny-by-default projection
```
Note facts: parsed **without an LLM** for the prototype — simple regex extraction in `cad.py` (`IOP[:=]?\s*(\d+(?:\.\d+)?)`, plus pass medications/intolerations lines as raw strings if present). Keep the note optional end-to-end.

**12. `app/services/llm.py`** —
```python
async def generate_json(system: str, data_block: str, response_model: type[T]) -> T
```
- `client.chat.completions.create(model=settings.model, temperature=0.2, response_format={"type":"json_object"}, messages=[system, user])`
- Parse with `response_model.model_validate_json`; on ValidationError: ONE retry with the error message appended; then raise AgentError.
- System prompts always declare: "You are one role on a screening panel. Use ONLY the facts in the data block. Screening-support language only — never state a definitive diagnosis, never give doses or drug regimens."

**13. `app/services/specialists.py`** — builds each role's data block from `route()` output (rendered as `key = value` lines); runs 3 `generate_json` calls with `asyncio.gather`; one failure → retry that role once → else raise (API returns clean 500).

**14. `app/services/director.py`** — `draft(subreports, cad_facts) -> Draft` using `prompts/director.txt` (must: preserve disagreements in `disagreements`, echo caveats, screening wording). `revise(draft, issues) -> Draft` via `director_revise.txt` (address each issue by number or justify no-change).

**15. `app/services/critic.py`** —
- `deterministic_checks(draft, cad_facts) -> list[Issue]`: (a) every number in the draft's impression/findings appears in CAD facts (±0.01 tolerance); (b) forbidden phrases: "patient has glaucoma", "diagnosed", dose pattern `\d+\s?(mg|mcg|%)`; (c) caveats non-empty and quality_note echoed; (d) CDR/grade in findings match CAD.
- `llm_check(draft, cad_facts) -> Verdict` via `prompts/critic.txt` (entailment check per finding).
- `audit_loop(draft, cad_facts)`: deterministic first → LLM → merge; reject → `director.revise`; stop at `critic_max_rounds`; return `(draft, issues, verified: bool)`.

**16. `app/services/report.py`** — `assemble(case_id, draft, cad, issues, verified) -> FinalReport`: renders `report_markdown` with sections (Impression / Findings / Recommendations / Disagreements / Caveats / CAD Summary table) + a header line when `verified == false`: `> ⚠️ UNVERIFIED — critic did not approve after 3 rounds; unresolved issues listed below.`; footer: `Screening support only — requires clinician review.` Also holds the in-memory `CASES: dict[str, FinalReport]`.

**17. Prompts (`app/prompts/*.txt`)** — one file per role; keep each < 1 page. Non-negotiable content per prompt: scope, exclusions, "use only provided facts", screening-support wording rule, output JSON schema instruction matching §5.

**18. `static/index.html`** — single-file SPA with three `<section>`s toggled by JS:
- **Landing:** project title, one-paragraph pitch, "Sign in with Google" button (Google Identity Services script, your `GOOGLE_CLIENT_ID`), footer credit.
- **App:** left column = upload card (drag-drop image preview, laterality select OD/OS/unknown, note textarea, "Generate Report" button with spinner); right column = report panel (empty state → rendered report).
- Google button calls `google.accounts.id.prompt()` → on credential → `POST /api/auth/google` → on success show app section.

**19. `static/js/app.js`** — token handling, `fetch` wrappers, `FormData` upload to `/api/cases`, render `report_markdown` via `marked.js` CDN (or minimal own renderer), **Export PDF button**: `html2pdf.js` (CDN) on the report div — zero backend PDF deps. Disable export until a report exists.

**20. `static/css/style.css`** — clean medical look (dark navbar, cards, monospace CAD table); no framework, ~150 lines.

**21–22. `tests/`** — `test_cad.py`: grade boundaries (0.19/0.2/0.49/0.5/0.89/0.9) + CDR passthrough; `test_router.py`: pharmacist context contains no `cdr` key; optometrist contains no `medications`. Run with `pytest` (add `pytest`, `pytest-asyncio` as dev deps).

---

## 7. Run & demo script

```bash
uv sync                      # or: uv pip install -r requirements via pyproject
uv run python main.py        # serves http://localhost:8000
```

Demo checklist: (1) landing loads; (2) Google sign-in works; (3) upload any fundus image + sample note → report in ~30–60s (4 GPT calls ≈ cheap); (4) PDF exports; (5) with `VISION_MODE=mock` the whole flow works without the friend's GPU; (6) wrong file type / oversized note → clean error toast.

**Sample note to demo with:** `"68-year-old patient. IOP OD 22 mmHg. Prior dx: ocular hypertension. Medications: latanoprost. Intolerance: sulfa drugs."`

---

## 8. Build order (hand this whole file to the agent; it must follow this sequence)

1. **Skeleton (30 min):** root `main.py`, `app/` package, `config.py`, `main.py`, static mount, empty routers — server boots, landing HTML shows.
2. **Auth (45 min):** Google sign-in end-to-end (button → verify → cookie → `/api/me`).
3. **Vision client + mock (30 min):** `vision_client.py`, `cad.py`, `router.py` + unit tests green.
4. **Agents (90 min):** `llm.py`, 5 prompt files, specialists → director → critic loop (mock vision, fake or real key).
5. **Report + API (60 min):** `report.py`, `case_routes.py`, wire frontend upload → render → export PDF.
6. **Polish (30 min):** error toasts, spinner, README run instructions, `.env.example`.

**Definition of done:** demo checklist §7 passes with `VISION_MODE=mock`, and passes with `live` once the friend's `/predict` returns the §6 contract. Nothing outside the §4 file tree. No extra services. No TODOs in code paths used by the demo.
