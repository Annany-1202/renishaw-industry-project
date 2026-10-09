from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import admin, documents, health, images, search
from backend.app.api import settings as settings_api
from backend.app.core import runtime_settings
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import db, init_db
from backend.app.ingestion.pipeline import register_builtin_catalogues
from backend.app.lifecycle import jobs
from backend.app.lifecycle.reconciliation import recover_interrupted_documents

_BOOTSTRAP_KEY = "builtin_catalogues_registered"


def bootstrap_catalogues() -> None:
    """Queue the two supplied catalogues the first time the application starts.

    Done once: a supplied catalogue the user deleted later is not brought back
    on restart (POST /api/admin/restore-defaults does that on request).
    """
    if not settings.AUTO_INGEST_SOURCE_PDFS:
        return
    with db() as conn:
        done = conn.execute("SELECT 1 FROM app_settings WHERE key = ?", (_BOOTSTRAP_KEY,)).fetchone()
    if done:
        return
    new_ids = register_builtin_catalogues()
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, '1')", (_BOOTSTRAP_KEY,))
    for doc_id in new_ids:
        jobs.submit_ingestion(doc_id)
    if new_ids:
        logger.info("Queued ingestion of the supplied catalogues: %s", ", ".join(new_ids))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    init_db()
    runtime_settings.load()
    recovered = recover_interrupted_documents()
    if any(recovered.values()):
        logger.info("Startup recovery: %s", recovered)
    bootstrap_catalogues()
    logger.info("%s v%s started.", settings.APP_NAME, settings.VERSION)
    yield
    logger.info("Application shutting down.")


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

# The UI is served from this same origin; CORS is only needed for the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Details go to the log; the client never receives paths, SQL or stack traces.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error. See the server log for details."})


app.include_router(health.router)
app.include_router(search.router)
app.include_router(documents.router)
app.include_router(images.router)
app.include_router(settings_api.router)
app.include_router(admin.router)

frontend_dist = (settings.BASE_DIR / "frontend" / "dist").resolve()
if (frontend_dist / "index.html").is_file():
    if (frontend_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = (frontend_dist / full_path).resolve()
        # Only files inside the built frontend are ever served; anything else gets the SPA shell.
        if full_path and candidate.is_relative_to(frontend_dist) and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(frontend_dist / "index.html"), headers={"Cache-Control": "no-cache"})
