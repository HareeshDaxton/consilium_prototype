import re
from typing import Protocol

import httpx

from app.schemas import RawVisionOutput


class VisionUnavailable(Exception):
    """The vision endpoint is unreachable or returned something unusable."""


class VisionClient(Protocol):
    async def predict(self, image_bytes: bytes, content_type: str = "image/jpeg") -> RawVisionOutput: ...


def _parse(data: dict) -> RawVisionOutput:
    """Tolerant parsing. If your friend's JSON shape differs, adjust ONLY this function."""
    p = data.get("glaucoma_probability", data.get("probability", data.get("p_glaucoma")))
    if p is None:
        raise VisionUnavailable("vision response is missing 'glaucoma_probability'")
    try:
        p = float(p)
    except (TypeError, ValueError):
        raise VisionUnavailable("vision 'glaucoma_probability' is not a number")
    if 1.0 < p <= 100.0:  # tolerate a percentage
        p /= 100.0
    cdr = data.get("cdr")
    try:
        cdr = float(cdr) if cdr is not None else None
    except (TypeError, ValueError):
        cdr = None
    return RawVisionOutput(
        glaucoma_probability=p,
        cdr=cdr,
        masks_available=data.get("masks_available"),
        disc_mask_b64=data.get("disc_mask_b64"),
        cup_mask_b64=data.get("cup_mask_b64"),
        note=data.get("note"),
    )


class HttpVisionClient:
    """POST {SWINV2_AND_SEGFORMER_LINK}/predict  (multipart: file=<image>)."""

    def __init__(self, base_url: str, timeout: float = 120.0):
        base = (base_url or "").strip().rstrip("/")
        base = re.sub(r"/docs/?$", "", base)  # in case the Swagger URL was pasted
        self._base = base
        self._timeout = timeout

    async def predict(self, image_bytes: bytes, content_type: str = "image/jpeg") -> RawVisionOutput:
        if not self._base:
            raise VisionUnavailable("SWINV2_AND_SEGFORMER_LINK is not set")
        ext = "png" if content_type == "image/png" else "jpg"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base}/predict",
                    files={"file": (f"fundus.{ext}", image_bytes, content_type)},
                    headers={"ngrok-skip-browser-warning": "true"},
                )
        except httpx.TransportError as e:
            raise VisionUnavailable(f"cannot reach vision endpoint ({type(e).__name__})") from e
        if resp.status_code >= 400:
            raise VisionUnavailable(f"vision endpoint returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise VisionUnavailable("vision endpoint returned non-JSON") from e
        return _parse(data)


class MockVisionClient:
    """Deterministic fake so every other stage is demoable without the GPU."""

    async def predict(self, image_bytes: bytes, content_type: str = "image/jpeg") -> RawVisionOutput:
        return RawVisionOutput(
            glaucoma_probability=0.82,
            cdr=0.62,
            masks_available=False,
            note="MOCK vision output",
        )