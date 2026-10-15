import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.deps import get_vision
from app.schemas import FinalReport
from app.services import critic, director, report as report_svc
from app.services.cad import build_cad_context, cad_facts, parse_note
from app.services.llm import AgentError
from app.services.router import route
from app.services.specialists import run_specialists
from app.services.vision_client import VisionUnavailable

log = logging.getLogger("consilium")
router = APIRouter(prefix="/api")

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_NOTE_FILE_BYTES = 10 * 1024 * 1024
MAX_NOTE_CHARS = 4000
LATERALITIES = {"OD", "OS", "UNKNOWN"}

# MIME types accepted for medical note file uploads
_NOTE_FILE_TYPES = {
    "image/png", "image/jpeg",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


async def _run_pipeline(case_id: str, image: bytes, content_type: str,
                        note: str, laterality: str) -> FinalReport:
    raw = await get_vision().predict(image, content_type)
    cad = build_cad_context(raw, laterality)
    facts_cad = cad_facts(cad)
    facts_note = parse_note(note)

    routed = route(facts_cad, facts_note)               # context router: role isolation
    subreports = await run_specialists(routed)          # 3 isolated specialists in parallel
    draft = await director.draft(subreports, facts_cad)  # merge, preserving dissent

    all_facts = {**facts_cad, **facts_note}             # the critic audits against everything
    draft, issues, verified = await critic.audit_loop(draft, all_facts)

    final = report_svc.assemble(case_id, draft, cad, issues, verified)
    report_svc.save(final)
    return final


@router.post("/cases")
async def create_case(
    image: UploadFile = File(...),
    note: str = Form(""),
    laterality: str = Form("UNKNOWN"),
    note_file: Optional[UploadFile] = File(None),
):
    # ---- validate fundus image ----
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return _err(413, "Image is larger than 20 MB.")
    content_type = _sniff_image(data)
    if content_type is None:
        return _err(415, "Unsupported file type. Please upload a JPEG or PNG fundus image.")

    # ---- validate optional medical note file ----
    # NOTE: In a production system, this is where you would integrate OCR
    # (e.g., Tesseract, Google Vision API) for images, or a PDF/DOCX text
    # extractor (e.g., PyMuPDF, python-docx) to convert the uploaded file
    # into text that gets appended to the `note` variable below.
    if note_file is not None and note_file.filename:
        nf_data = await note_file.read(MAX_NOTE_FILE_BYTES + 1)
        if len(nf_data) > MAX_NOTE_FILE_BYTES:
            return _err(413, "Medical note file is larger than 10 MB.")
        nf_type = note_file.content_type or ""
        if nf_type not in _NOTE_FILE_TYPES:
            return _err(415, "Unsupported note file type. Upload PNG, JPEG, PDF, or Word.")
        # TODO: extract text from uploaded note file and append to `note`
        log.info("received note file: %s (%s, %d bytes)", note_file.filename, nf_type, len(nf_data))

    note = (note or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        return _err(400, f"Medical note is too long (max {MAX_NOTE_CHARS} characters).")

    lat = (laterality or "UNKNOWN").strip().upper()
    if lat not in LATERALITIES:
        return _err(400, "Laterality must be OD, OS or UNKNOWN.")

    case_id = str(uuid.uuid4())
    try:
        return await _run_pipeline(case_id, data, content_type, note, lat)
    except VisionUnavailable as e:
        log.warning("vision unavailable: %s", e)
        return _err(503, f"Vision service unavailable: {e}")
    except AgentError as e:
        log.warning("agent error: %s", e)
        return _err(500, f"Report generation failed: {e}")
    except Exception:
        log.exception("unexpected pipeline failure")
        return _err(500, "Unexpected server error while generating the report.")


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    found = report_svc.CASES.get(case_id)
    if found is None:
        return _err(404, "Case not found.")
    return found