"""Recoverable cascading document deletion (FR-10, FR-18, spec section 13.3).

State machine: mark Deleting -> (searches exclude it immediately) -> remove
vectors -> remove image files -> remove records -> remove the stored PDF ->
verify -> remove the document row. If a step fails the document stays in
`Deleting` with the failed step recorded; nothing is reported as deleted, and
calling delete again (or running reconciliation) resumes from the start, which
is safe because every step is idempotent.
"""
import shutil
from pathlib import Path
from typing import Any, Dict, List

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import DELETING, PROCESSING, db, log_event


class DeletionError(Exception):
    def __init__(self, message: str, report: Dict[str, Any]):
        super().__init__(message)
        self.report = report


class DocumentBusy(Exception):
    pass


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def deletion_preview(doc_id: str) -> Dict[str, Any]:
    """What a delete would remove (shown in the confirmation dialog)."""
    with db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise KeyError(doc_id)
        counts = {
            "products": conn.execute("SELECT count(*) FROM products WHERE document_id = ?", (doc_id,)).fetchone()[0],
            "images": conn.execute("SELECT count(*) FROM images WHERE document_id = ?", (doc_id,)).fetchone()[0],
            "product_image_links": conn.execute("SELECT count(*) FROM product_images WHERE document_id = ?", (doc_id,)).fetchone()[0],
            "shared_part_numbers_kept_in_other_documents": conn.execute(
                "SELECT count(DISTINCT p.part_number) FROM products p WHERE p.document_id = ? AND EXISTS "
                "(SELECT 1 FROM products o WHERE o.part_number = p.part_number AND o.document_id != p.document_id)",
                (doc_id,),
            ).fetchone()[0],
        }
    counts["embeddings"] = doc["embedded_count"]
    counts["source_file"] = 1
    return {"document_id": doc_id, "filename": doc["filename"], "will_remove": counts}


def delete_document(doc_id: str) -> Dict[str, Any]:
    """Delete a document and everything it owns. Returns a verified report; raises DeletionError otherwise."""
    from backend.app.llm import embeddings

    with db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise KeyError(doc_id)
        if doc["status"] == PROCESSING:
            raise DocumentBusy("The document is being processed; wait for ingestion to finish before deleting it.")
        # Step 1: from this commit on, no search treats the document as an active source.
        conn.execute(
            "UPDATE documents SET status = ?, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (DELETING, doc_id),
        )
        log_event(conn, doc_id, "deleting", "", doc["filename"])

    report: Dict[str, Any] = {
        "document_id": doc_id, "filename": doc["filename"], "status": "in_progress",
        "steps": [], "removed": {}, "verification": {},
    }
    step = "start"
    try:
        step = "remove vector-index entries"
        report["removed"]["embeddings"] = embeddings.delete_document_vectors(doc_id)
        report["steps"].append(step)

        step = "remove extracted image files"
        image_dir = settings.IMAGE_DIR / doc_id
        file_count = sum(1 for p in image_dir.rglob("*") if p.is_file()) if image_dir.exists() else 0
        if image_dir.exists():
            shutil.rmtree(image_dir)
        report["removed"]["image_files"] = file_count
        report["steps"].append(step)

        step = "remove product, image and association records"
        with db() as conn:
            for table, key in (("product_images", "product_image_links"), ("images", "images"), ("products", "products")):
                cur = conn.execute(f"DELETE FROM {table} WHERE document_id = ?", (doc_id,))
                report["removed"][key] = cur.rowcount
        report["steps"].append(step)

        step = "remove stored PDF and generated reports"
        source = Path(doc["file_path"])
        removed_source = False
        if _is_inside(source, settings.UPLOAD_DIR) and source.exists():
            try:
                source.unlink()
            except PermissionError:
                # Windows: a PDF handle that is only waiting for garbage collection still locks the file.
                import gc
                gc.collect()
                source.unlink()
            removed_source = True
        report["removed"]["source_file"] = removed_source
        for leftover in settings.REPORT_DIR.glob(f"{doc_id}_*"):
            leftover.unlink()
        report["steps"].append(step)

        step = "verify cleanup"
        with db() as conn:
            remaining = {
                t: conn.execute(f"SELECT count(*) FROM {t} WHERE document_id = ?", (doc_id,)).fetchone()[0]
                for t in ("products", "images", "product_images")
            }
        remaining["embeddings"] = embeddings.count_document_vectors(doc_id)
        remaining["image_directory_exists"] = image_dir.exists()
        remaining["source_file_exists"] = _is_inside(source, settings.UPLOAD_DIR) and source.exists()
        report["verification"] = remaining
        problems: List[str] = [k for k, v in remaining.items() if v]
        if problems:
            raise RuntimeError("artifacts remain after cleanup: " + ", ".join(problems))
        report["steps"].append(step)

        step = "remove document record"
        with db() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            log_event(conn, doc_id, "deleted", str(report["removed"]), doc["filename"])
        report["steps"].append(step)
        report["status"] = "success"
        report["verification"]["verified"] = True
        from backend.app.retrieval import catalogue
        catalogue.invalidate()
        logger.info("Deleted document %s: %s", doc_id, report["removed"])
        return report
    except Exception as exc:
        logger.error("Deletion of %s failed at step '%s': %s", doc_id, step, exc, exc_info=True)
        message = f"Deletion failed at step '{step}'. The document is excluded from search; run reconciliation or delete again to finish cleanup."
        report["status"] = "failed"
        report["failed_step"] = step
        with db() as conn:
            conn.execute(
                "UPDATE documents SET error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (message, doc_id),
            )
            log_event(conn, doc_id, "delete_failed", f"step={step}; {type(exc).__name__}", doc["filename"])
        raise DeletionError(message, report) from exc
