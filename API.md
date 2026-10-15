# Glaucoma CAD API — Frontend Guide

Models: SwinV2-Tiny (glaucoma classification) + SegFormer-B3 (optic disc/cup → CDR).
Input must be a **raw retinal fundus photo** (JPEG/PNG). Masks, annotated illustrations,
and non-fundus images produce garbage — the API does not validate this.

## Base URLs

| Env   | Base URL |
|-------|----------|
| LAN   | `http://10.231.79.59:8000` (re-check with `hostname -I`, changes on reconnect) |
| Public| `https://pasta-hanky-grunt.ngrok-free.dev` (changes on ngrok restart, free tier) |

Interactive playground (upload from phone browser, no code): `<BASE>/docs`
Machine-readable spec for codegen: `<BASE>/openapi.json` (copy in `docs/openapi.json`)

All `POST` endpoints take `multipart/form-data` with a single field **`file`**
(the image bytes; the filename is ignored by the models). All responses are JSON.

## Endpoints

### GET /health
Liveness check. No body.
```json
{ "status": "ok", "device": "cuda" }
```

### POST /predict — SwinV2 classification only (~40ms)
```bash
curl -X POST <BASE>/predict -F "file=@fundus.jpg"
```
Response:
```json
{
  "label": "Glaucoma",        // string: "Glaucoma" | "Non-glaucoma"
  "p_glaucoma": 0.9985,       // number 0..1
  "p_non_glaucoma": 0.0015   // number 0..1
}
```

### POST /segment — SegFormer OD/OC measurements (~400ms at 512px)
```bash
curl -X POST <BASE>/segment -F "file=@fundus.jpg"
```
Response:
```json
{
  "cdr_area": 0.604,  // number 0..1, sqrt(cup_px)/sqrt(disc_px+cup_px); ≥0.6 = suspect
  "vcdr": 0.6106,     // number 0..1, vertical cup height / disc height (clinical standard)
  "disc_px": 58109,   // int, rim pixel count (label 1)
  "cup_px": 33380     // int, cup pixel count (label 2)
}
```

### POST /diagnose — both models fused (~450ms)
```bash
curl -X POST <BASE>/diagnose -F "file=@fundus.jpg"
```
Response:
```json
{
  "verdict": "GLAUCOMA SUSPECT",  // "GLAUCOMA SUSPECT" | "NON-GLAUCOMA"
  "label": "Glaucoma",
  "p_glaucoma": 0.9985,
  "cdr_area": 0.604,
  "vcdr": 0.6106
}
```
Rule: `SUSPECT` if `p_glaucoma >= 0.5` **or** `cdr_area >= 0.6`.

## Frontend example (fetch, single file input)

```js
async function diagnose(file, BASE = "https://pasta-hanky-grunt.ngrok-free.dev") {
  const form = new FormData();
  form.append("file", file); // File from <input type="file">
  const res = await fetch(`${BASE}/diagnose`, {
    method: "POST",
    headers: { "ngrok-skip-browser-warning": "true" }, // only needed for ngrok URL
    body: form,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json(); // { verdict, label, p_glaucoma, cdr_area, vcdr }
}

// render: (d.p_glaucoma*100).toFixed(1) + "%", verdict badge, CDR bars
```

CORS is wide open (`allow_origins=["*"]`) so any frontend origin can call the API directly.

## Errors

| Case | HTTP | Body |
|------|------|------|
| No `file` part | 422 | `{"detail":[...]}` (FastAPI validation) |
| Bytes aren't an image | 500 | exception text |
| GPU OOM (batch abuse — endpoints are single-image) | 500 | exception text |

## Performance / limits

* Single image per request. For folders, loop client-side (see `scripts/eval_train.py`).
* fp16 on CUDA; ~0.4–0.8GB VRAM per request. Concurrent requests serialize on the GPU.
* No auth — demo only, not for patient data.
* Validated accuracy on REFUGE Training400: 90.5% (sens 97.5%, spec 89.7%).
