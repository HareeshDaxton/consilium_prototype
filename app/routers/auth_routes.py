from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_cookie,
    read_session,
    verify_google_token,
)
from app.deps import get_settings
from app.schemas import GoogleLoginRequest

router = APIRouter(prefix="/api")


@router.get("/config")
async def public_config():
    s = get_settings()
    return {"google_client_id": s.google_client_id, "vision_mode": s.vision_mode}


@router.post("/auth/google")
async def google_login(body: GoogleLoginRequest, request: Request):
    try:
        user = await run_in_threadpool(verify_google_token, body.id_token)
    except Exception:
        return JSONResponse({"error": "Google sign-in could not be verified."}, status_code=401)
    resp = JSONResponse(user)
    resp.set_cookie(
        COOKIE_NAME,
        create_session_cookie(user),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return resp


@router.post("/auth/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/me")
async def me(request: Request):
    session = read_session(request.cookies.get(COOKIE_NAME))
    if session is None:
        return JSONResponse({"error": "Not authenticated."}, status_code=401)
    return session