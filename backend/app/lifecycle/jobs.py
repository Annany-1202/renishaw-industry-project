"""Background ingestion jobs.

One worker thread processes documents in order, so two ingestions never write
to SQLite or the vector index at the same time. Progress is observed by
polling the document status (Queued -> Processing -> Ready / Failed).
"""
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict

from backend.app.core.logging import logger
from backend.app.ingestion.pipeline import IngestionError, process_document

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
_lock = threading.Lock()
_active: Dict[str, Future] = {}


def _run(doc_id: str) -> None:
    try:
        process_document(doc_id)
    except IngestionError:
        pass  # already recorded on the document row
    except Exception:
        logger.exception("Unexpected ingestion job failure for %s", doc_id)
    finally:
        with _lock:
            _active.pop(doc_id, None)


def submit_ingestion(doc_id: str) -> None:
    with _lock:
        if doc_id in _active:
            return
        _active[doc_id] = _executor.submit(_run, doc_id)


def is_active(doc_id: str) -> bool:
    with _lock:
        return doc_id in _active


def wait_for(doc_id: str, timeout: float = 600.0) -> None:
    """Block until a queued job finishes (used by scripts and tests)."""
    with _lock:
        future = _active.get(doc_id)
    if future is not None:
        future.result(timeout=timeout)
