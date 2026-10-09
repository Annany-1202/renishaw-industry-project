import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.app.core.logging import logger
from backend.app.ingestion.pipeline import register_builtin_catalogues
from backend.app.lifecycle import jobs
from backend.app.lifecycle.reconciliation import reconcile
from backend.app.llm import embeddings
from backend.app.llm.ollama_client import ollama_client
from backend.app.retrieval import catalogue

router = APIRouter(prefix="/api/admin", tags=["admin"])
_maintenance = threading.Lock()


@router.post("/reconcile")
def reconcile_state() -> Dict[str, Any]:
    """Bring SQLite, the vector index and the files on disk back in line (safe to run at any time)."""
    if not _maintenance.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A maintenance task is already running.")
    try:
        report = reconcile()
        catalogue.invalidate()
        return report
    except Exception:
        logger.exception("Reconciliation failed")
        raise HTTPException(status_code=500, detail="Reconciliation failed; see the server log.")
    finally:
        _maintenance.release()


@router.post("/reindex")
def trigger_reindex() -> Dict[str, Any]:
    """Rebuild the vector index from the Ready documents with the configured embedding model."""
    health = ollama_client.check_health()
    if not health["ollama_reachable"] or not health["embedding_model_available"]:
        raise HTTPException(
            status_code=503,
            detail="The local embedding model is not available, so the index was left unchanged. "
                   "Start Ollama and make sure the embedding model is installed.",
        )
    if not _maintenance.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A maintenance task is already running.")
    try:
        summary = embeddings.reindex_all()
        return {"status": "reindex_complete", **summary, "vector_index": embeddings.index_status()}
    except Exception:
        logger.exception("Reindex failed")
        raise HTTPException(status_code=500, detail="Reindexing failed; see the server log.")
    finally:
        _maintenance.release()


@router.post("/restore-defaults")
def restore_default_catalogues() -> Dict[str, Any]:
    """Re-add the two supplied catalogues if they were deleted."""
    new_ids = register_builtin_catalogues()
    for doc_id in new_ids:
        jobs.submit_ingestion(doc_id)
    return {"queued": new_ids}
