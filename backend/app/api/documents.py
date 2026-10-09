import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import FAILED, QUEUED, db, log_event
from backend.app.ingestion.pipeline import DuplicateDocument, register_document, safe_display_name
from backend.app.lifecycle import jobs
from backend.app.lifecycle.deletion import DeletionError, DocumentBusy, delete_document, deletion_preview
from backend.app.retrieval import catalogue

router = APIRouter(prefix="/api/documents", tags=["documents"])

DOC_ID_RE = re.compile(r"^doc_[A-Za-z0-9]{1,40}$")
REPORT_FILES = {
    "report": ("_ingestion_report.json", "application/json"),
    "images": ("_image_associations.csv", "text/csv"),
    "review": ("_review_rows.csv", "text/csv"),
}
_LIST_SQL = """
SELECT d.id, d.filename, d.file_hash, d.file_size, d.page_count, d.status, d.error_message, d.is_builtin,
       d.embedding_model, d.embedded_count, d.created_at, d.updated_at,
       (SELECT count(*) FROM products p WHERE p.document_id = d.id) AS product_count,
       (SELECT count(*) FROM products p WHERE p.document_id = d.id AND p.validation_status != 'validated') AS review_count,
       (SELECT count(*) FROM images i WHERE i.document_id = d.id) AS image_count
FROM documents d
"""


def _check_id(doc_id: str) -> str:
    if not DOC_ID_RE.fullmatch(doc_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc_id


def _summary(row) -> Dict[str, Any]:
    doc = dict(row)
    # A document is searchable only while Ready; counts of a document in another state are staging data.
    doc["is_builtin"] = bool(doc["is_builtin"])
    return doc


@router.get("")
def list_documents() -> List[Dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(_LIST_SQL + " ORDER BY d.created_at DESC, d.id").fetchall()
    return [_summary(r) for r in rows]


@router.get("/{doc_id}")
def get_document(doc_id: str) -> Dict[str, Any]:
    _check_id(doc_id)
    with db() as conn:
        row = conn.execute(_LIST_SQL + " WHERE d.id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found.")
        report = conn.execute("SELECT ingestion_report FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
        events = [dict(e) for e in conn.execute(
            "SELECT event, detail, created_at FROM document_events WHERE document_id = ? ORDER BY id DESC LIMIT 30",
            (doc_id,),
        )]
    doc = _summary(row)
    try:
        full = json.loads(report) if report else None
    except ValueError:
        full = None
    if full:
        # The per-page table is large; it stays available through the report download.
        doc["ingestion_report"] = {k: v for k, v in full.items() if k not in ("source_pages",)}
    else:
        doc["ingestion_report"] = None
    doc["events"] = events
    return doc


@router.post("", status_code=202)
def upload_document(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Store the upload and queue ingestion. Poll GET /api/documents/{id} for the status."""
    display_name = safe_display_name(file.filename or "document.pdf")
    if Path(display_name).suffix.lower() not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    incoming = settings.DATA_DIR / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    temp = incoming / f"{uuid.uuid4().hex}.part"  # the client's file name is never part of a path
    size = 0
    try:
        with open(temp, "wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"The file is larger than {settings.MAX_UPLOAD_SIZE_MB} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        with open(temp, "rb") as fh:
            if b"%PDF-" not in fh.read(1024):
                raise HTTPException(status_code=400, detail="The file is not a PDF document.")
        try:
            doc_id = register_document(temp, display_name, move=True)
        except DuplicateDocument as dup:
            return JSONResponse(status_code=409, content={
                "detail": f"This PDF is already in the library as '{dup.filename}' (status: {dup.status}).",
                "existing_document_id": dup.existing_id,
            })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Upload could not be stored")
        raise HTTPException(status_code=500, detail="The upload could not be stored.")
    finally:
        temp.unlink(missing_ok=True)
    jobs.submit_ingestion(doc_id)
    return {"id": doc_id, "filename": display_name, "status": QUEUED, "file_size": size}


@router.get("/{doc_id}/deletion-preview")
def get_deletion_preview(doc_id: str) -> Dict[str, Any]:
    _check_id(doc_id)
    try:
        return deletion_preview(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found.")


@router.delete("/{doc_id}")
def remove_document(doc_id: str):
    _check_id(doc_id)
    if jobs.is_active(doc_id):
        raise HTTPException(status_code=409, detail="The document is being processed; wait for ingestion to finish.")
    try:
        report = delete_document(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found.")
    except DocumentBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DeletionError as exc:
        catalogue.invalidate()
        return JSONResponse(status_code=500, content={"detail": str(exc), "report": exc.report})
    catalogue.invalidate()
    return report


@router.post("/{doc_id}/retry", status_code=202)
def retry_document(doc_id: str) -> Dict[str, Any]:
    _check_id(doc_id)
    with db() as conn:
        row = conn.execute("SELECT status, filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found.")
        if row["status"] != FAILED or jobs.is_active(doc_id):
            raise HTTPException(status_code=409, detail=f"Only failed documents can be retried (status: {row['status']}).")
        conn.execute("UPDATE documents SET status = ?, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (QUEUED, doc_id))
        log_event(conn, doc_id, "retry_requested", "", row["filename"])
    jobs.submit_ingestion(doc_id)
    return {"id": doc_id, "status": QUEUED}


@router.get("/{doc_id}/report")
def download_report(doc_id: str, kind: str = "report"):
    """kind: report (JSON ingestion report), images (image association CSV), review (rows needing review CSV)."""
    _check_id(doc_id)
    if kind not in REPORT_FILES:
        raise HTTPException(status_code=400, detail="kind must be one of: report, images, review.")
    suffix, media_type = REPORT_FILES[kind]
    path = (settings.REPORT_DIR / f"{doc_id}{suffix}").resolve()
    if not path.is_relative_to(settings.REPORT_DIR.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="No report is available for this document.")
    return FileResponse(str(path), media_type=media_type, filename=path.name)
