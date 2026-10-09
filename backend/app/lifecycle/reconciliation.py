"""Reconciliation of SQLite, the vector index and the files on disk.

Detects and repairs: interrupted deletions, interrupted ingestions, vectors
without an active document, image files or directories nothing refers to,
image records whose file is gone, and stored PDFs without a document row.
"""
from pathlib import Path
from typing import Any, Dict, List

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import DELETING, FAILED, PROCESSING, QUEUED, READY, db, log_event
from backend.app.lifecycle import jobs
from backend.app.lifecycle.deletion import DeletionError, delete_document


def recover_interrupted_documents() -> Dict[str, List[str]]:
    """Run at startup: nothing can still be processing, so finish or fail what was left half-done."""
    outcome: Dict[str, List[str]] = {"marked_failed": [], "deletions_resumed": [], "deletions_still_failing": []}
    with db() as conn:
        stuck = [dict(r) for r in conn.execute(
            "SELECT id, filename, status FROM documents WHERE status IN (?, ?, ?, ?)",
            (PROCESSING, QUEUED, "Uploaded", DELETING),
        )]
    for doc in stuck:
        if jobs.is_active(doc["id"]):
            continue
        if doc["status"] == DELETING:
            try:
                delete_document(doc["id"])
                outcome["deletions_resumed"].append(doc["id"])
            except (DeletionError, KeyError):
                outcome["deletions_still_failing"].append(doc["id"])
        else:
            from backend.app.ingestion.pipeline import _discard_staged
            _discard_staged(doc["id"])
            with db() as conn:
                conn.execute(
                    "UPDATE documents SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (FAILED, "Ingestion was interrupted before it completed. Use Retry to run it again.", doc["id"]),
                )
                log_event(conn, doc["id"], "failed", "interrupted", doc["filename"])
            outcome["marked_failed"].append(doc["id"])
    return outcome


def reconcile() -> Dict[str, Any]:
    from backend.app.llm import embeddings

    report: Dict[str, Any] = {"status": "reconciliation_complete"}
    report.update(recover_interrupted_documents())

    with db() as conn:
        docs = {r["id"]: r["status"] for r in conn.execute("SELECT id, status FROM documents")}
        ready = {d for d, s in docs.items() if s == READY}
        in_flight = {d for d, s in docs.items() if s in (PROCESSING, QUEUED)}
        referenced_images = {r["image_path"] for r in conn.execute("SELECT image_path FROM images")}
        referenced_files = {str(Path(r["file_path"]).resolve()) for r in conn.execute("SELECT file_path FROM documents")}
    report["active_documents"] = sorted(ready)

    # 1. Vectors whose document is not an active source.
    removed_vectors = 0
    try:
        coll = embeddings.get_or_create_collection()
        data = coll.get(include=["metadatas"])
        orphans = [
            vid for vid, meta in zip(data.get("ids", []), data.get("metadatas", []) or [])
            if (meta or {}).get("document_id") not in ready and (meta or {}).get("document_id") not in in_flight
        ]
        if orphans:
            coll.delete(ids=orphans)
            removed_vectors = len(orphans)
        report["vector_index"] = embeddings.index_status()
    except Exception as exc:
        logger.error("Vector reconciliation failed: %s", exc)
        report["vector_index"] = {"error": "vector index could not be reconciled"}
    report["orphaned_vectors_removed"] = removed_vectors

    # 2. Image directories and files that no record refers to.
    orphan_dirs: List[str] = []
    orphan_files: List[str] = []
    image_root = settings.IMAGE_DIR
    if image_root.exists():
        import shutil
        for entry in image_root.iterdir():
            if entry.is_dir():
                if entry.name in in_flight:
                    continue
                if entry.name not in docs:
                    shutil.rmtree(entry, ignore_errors=True)
                    orphan_dirs.append(entry.name)
                    continue
                for file in entry.rglob("*"):
                    if file.is_file() and f"{entry.name}/{file.relative_to(entry).as_posix()}" not in referenced_images:
                        file.unlink(missing_ok=True)
                        orphan_files.append(f"{entry.name}/{file.name}")
            elif entry.is_file():
                entry.unlink(missing_ok=True)
                orphan_files.append(entry.name)
    report["orphaned_image_directories_cleaned"] = orphan_dirs
    report["orphaned_image_files_removed"] = len(orphan_files)

    # 3. Image records whose file no longer exists.
    missing: List[str] = []
    with db() as conn:
        for row in conn.execute("SELECT image_id, image_path, document_id FROM images").fetchall():
            if row["document_id"] in in_flight:
                continue
            if not (image_root / row["image_path"]).exists():
                conn.execute("DELETE FROM images WHERE image_id = ?", (row["image_id"],))
                missing.append(row["image_id"])
    report["image_records_without_file_removed"] = len(missing)

    # 4. Stored PDFs without a document row (for example an upload that failed before registration).
    orphan_uploads: List[str] = []
    if settings.UPLOAD_DIR.exists():
        for file in settings.UPLOAD_DIR.iterdir():
            if file.is_file() and str(file.resolve()) not in referenced_files:
                file.unlink(missing_ok=True)
                orphan_uploads.append(file.name)
    report["orphaned_upload_files_removed"] = orphan_uploads

    # 5. Report files of documents that no longer exist.
    stale_reports = 0
    if settings.REPORT_DIR.exists():
        for file in settings.REPORT_DIR.iterdir():
            doc_id = file.name.split("_ingestion_report")[0].split("_image_associations")[0].split("_review_rows")[0]
            if file.is_file() and doc_id not in docs and not file.name.startswith(("evaluation", "human_review")):
                file.unlink(missing_ok=True)
                stale_reports += 1
    report["stale_report_files_removed"] = stale_reports

    # 6. Documents whose vector count does not match their product count (repair with reindex).
    out_of_sync: List[str] = []
    if settings.EMBEDDINGS_ENABLED:
        with db() as conn:
            for row in conn.execute(
                "SELECT d.id, d.embedded_count, (SELECT count(*) FROM products p WHERE p.document_id = d.id) AS n "
                "FROM documents d WHERE d.status = ?", (READY,),
            ):
                try:
                    actual = embeddings.count_document_vectors(row["id"])
                except Exception:
                    actual = -1
                if actual != row["n"]:
                    out_of_sync.append(row["id"])
    report["documents_needing_reindex"] = out_of_sync
    return report
