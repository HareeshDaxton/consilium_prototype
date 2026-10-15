# CONSILIUM prototype

End-to-end demo of the CONSILIUM pipeline: role-isolated specialist agents (ophthalmologist,
optometrist, pharmacist) -> director -> adversarial critic -> screening-support report, behind a
Google-login web UI with PDF export.

## Setup

```bash
uv sync
cp .env.example .env     # then fill in the values (Windows: copy .env.example .env)
```

| Key | Meaning |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (agents use `gpt-4o-mini`; override with `CONSILIUM_MODEL`) |
| `SWINV2_AND_SEGFORMER_LINK` | Friend's FastAPI base URL (ngrok), no trailing `/docs` |
| `VISION_MODE` | `live` or `mock` (mock returns synthetic CAD results, no GPU needed) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (type: Web application) |
| `SESSION_SECRET` | Long random string used to sign the session cookie |

### Google OAuth
Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth client ID -> Web application.
Add `http://localhost:8000` under **Authorized JavaScript origins** (add your ngrok/deploy URL too if
you demo remotely).

## Run

```bash
uv run python main.py     # http://localhost:8000
uv run pytest             # unit tests
```

## Vision endpoint contract (what the GPU service must return)

```
POST {SWINV2_AND_SEGFORMER_LINK}/predict    multipart: file=<image>
200 {"glaucoma_probability": 0.91, "cdr": 0.62, "masks_available": true, "note": "gradable"}
```

If the shape differs, change only `app/services/vision_client.py` (`_parse`).

## Demo checklist

1. Landing page loads. 2. Google sign-in works. 3. Upload a fundus image plus the sample note:
   `68-year-old patient. IOP OD 22 mmHg. Prior dx: ocular hypertension. Medications: latanoprost. Intolerance: sulfa drugs.`
4. Report appears in about 30-60 s. 5. Export PDF. 6. Wrong file type or oversized note shows an error toast.

Screening support only: the system never states a definitive diagnosis.