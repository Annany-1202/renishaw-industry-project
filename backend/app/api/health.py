from typing import Any, Dict

from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import READY, db, schema_version
from backend.app.llm import embeddings
from backend.app.llm.ollama_client import ollama_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def get_health() -> Dict[str, Any]:
    ollama_status = ollama_client.check_health()

    db_status: Dict[str, Any] = {"connected": False, "product_count": 0, "document_count": 0}
    try:
        with db() as conn:
            db_status["connected"] = True
            db_status["schema_version"] = schema_version()
            db_status["document_count"] = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
            db_status["ready_document_count"] = conn.execute(
                "SELECT count(*) FROM documents WHERE status = ?", (READY,)).fetchone()[0]
            db_status["product_count"] = conn.execute(
                "SELECT count(*) FROM products p JOIN documents d ON d.id = p.document_id WHERE d.status = ?",
                (READY,)).fetchone()[0]
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        db_status["error"] = "The database could not be opened."

    vector_status = embeddings.index_status() if settings.EMBEDDINGS_ENABLED else {
        "ready": False, "item_count": 0, "disabled": True}

    # Structured search works without Ollama; the LLM and embeddings only add interpretation help.
    search_ok = db_status["connected"]
    full = (search_ok and ollama_status["ollama_reachable"] and ollama_status["llm_model_available"]
            and ollama_status["embedding_model_available"]
            and (vector_status.get("in_sync") or not settings.EMBEDDINGS_ENABLED))
    notes = []
    if not ollama_status["ollama_reachable"]:
        notes.append("Ollama is not running: queries are interpreted by rules only.")
    elif not ollama_status["llm_model_available"]:
        notes.append(f"LLM model {settings.LLM_MODEL} is not installed: queries are interpreted by rules only.")
    if ollama_status["ollama_reachable"] and not ollama_status["embedding_model_available"]:
        notes.append(f"Embedding model {settings.EMBEDDING_MODEL} is not installed.")
    if settings.EMBEDDINGS_ENABLED and vector_status.get("ready") and not vector_status.get("in_sync"):
        notes.append("The vector index is out of sync with the catalogue; run Reindex.")
    return {
        "status": "healthy" if full else ("degraded" if search_ok else "unavailable"),
        "search_available": search_ok,
        "notes": notes,
        "app_version": settings.VERSION,
        "llm_mode": settings.LLM_MODE,
        "ollama": ollama_status,
        "database": db_status,
        "vector_index": vector_status,
    }
