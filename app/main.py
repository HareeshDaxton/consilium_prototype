import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth import COOKIE_NAME, read_session
from app.routers import auth_routes, case_routes

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="CONSILIUM prototype")


@app.middleware("http")
async def require_session(request: Request, call_next):
    if request.url.path.startswith("/api/cases"):
        if read_session(request.cookies.get(COOKIE_NAME)) is None:
            return JSONResponse({"error": "Not authenticated."}, status_code=401)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(auth_routes.router)
app.include_router(case_routes.router)


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")