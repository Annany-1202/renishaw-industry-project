"""Document ingestion: register -> extract -> validate -> embed -> activate.

Ingestion is staged. Extracted records, images and vectors are written while
the document is `Processing`; searches only read documents that are `Ready`,
and the switch to `Ready` happens in the same SQLite transaction that inserts
the records. A failure at any point removes the staged artifacts and leaves
the document `Failed` with a user-safe message.
"""
import csv
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.database import FAILED, PROCESSING, QUEUED, READY, db, init_db, log_event
from backend.app.ingestion.generic_extractor import extract_generic_catalogue
from backend.app.ingestion.h1000_extractor import extract_h1000_catalogue
from backend.app.ingestion.models import ExtractionResult
from backend.app.ingestion.validation import apply_validation
from backend.app.ingestion.zeiss_extractor import extract_zeiss_catalogue

BUILTIN_CATALOGUES = [
    ("doc_zeiss", "Styli_for_ZEISS_applications_H-1000-3036_EN.pdf"),
    ("doc_h1000", "H-1000-3200_Styli_and_accessories_technical_specifications_guide_EN.pdf"),
]
PRODUCT_COLUMNS = [
    "id", "document_id", "manufacturer", "part_number", "alt_part_number", "product_name", "description",
    "category", "stylus_type", "thread", "ball_material", "ball_diameter_mm", "stem_material",
    "stem_diameter_mm", "overall_length_mm", "effective_working_length_mm", "weight_g",
    "extra_attributes", "raw_attributes", "source_pdf", "source_page", "source_table", "source_section",
    "extraction_confidence", "validation_status", "review_reason",
]
IMAGE_COLUMNS = ["image_id", "document_id", "page_number", "image_path", "image_type", "image_hash", "extraction_metadata"]
LINK_COLUMNS = ["image_id", "product_id", "document_id", "part_number", "association_status", "association_basis"]


class IngestionError(Exception):
    """An ingestion failure with a message that is safe to show to the user."""


class DuplicateDocument(Exception):
    def __init__(self, existing_id: str, filename: str, status: str):
        super().__init__(f"Document already indexed as {existing_id}")
        self.existing_id, self.filename, self.status = existing_id, filename, status


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1 << 16):
            sha.update(chunk)
    return sha.hexdigest()


def safe_display_name(filename: str) -> str:
    """Display name only (never used to build a path): strip directories and control characters."""
    name = Path(str(filename or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:180] or "document.pdf"


def register_document(source: Path, display_name: str, doc_id: Optional[str] = None,
                      is_builtin: bool = False, move: bool = False) -> str:
    """Store a PDF under the managed upload directory and create its document row (status Queued).

    Raises DuplicateDocument when a document with the same SHA-256 already exists.
    """
    init_db()
    file_hash = compute_sha256(source)
    with db() as conn:
        existing = conn.execute("SELECT id, filename, status FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
    if existing:
        raise DuplicateDocument(existing["id"], existing["filename"], existing["status"])
    doc_id = doc_id or f"doc_{uuid.uuid4().hex[:12]}"
    target = settings.UPLOAD_DIR / f"{doc_id}.pdf"
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(source), str(target))
    else:
        shutil.copyfile(source, target)
    name = safe_display_name(display_name)
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, file_hash, file_path, file_size, status, is_builtin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, name, file_hash, str(target), target.stat().st_size, QUEUED, int(is_builtin)),
            )
            log_event(conn, doc_id, "uploaded", f"sha256={file_hash}", name)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return doc_id


def _choose_extractor(pdf: "pymupdf.Document"):
    """Pick the extractor from the document's own content, not from its file name.

    The layout-specific extractors are used only for the two publications they were written
    for, recognised by the publication number on the cover pages and a matching size. Any
    other PDF, including one that merely mentions those numbers, gets the generic extractor.
    """
    if len(pdf) < 50:
        return extract_generic_catalogue
    sample = " ".join(pdf[i].get_text() for i in (0, 1, 2, len(pdf) - 1))
    if "H-1000-3036" in sample or "Styli for Zeiss applications" in sample:
        return extract_zeiss_catalogue
    if "H-1000-3200" in sample:
        return extract_h1000_catalogue
    return extract_generic_catalogue


def _apply_image_overrides(result: ExtractionResult) -> None:
    """Manual verification file: {"<image_id>|<part_number>": "verified" | "unverified" | "rejected"}."""
    path = settings.DATA_DIR / "image_overrides.json"
    if not path.exists():
        return
    try:
        overrides = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("image_overrides.json is not valid JSON; ignoring it")
        return
    for link in result.links:
        status = overrides.get(f"{link['image_id']}|{link['part_number']}") or overrides.get(link["image_id"])
        if status in ("verified", "unverified", "rejected"):
            link["association_status"] = status
            link["association_basis"] = f"manual override ({link['association_basis']})"


def _write_reports(doc_id: str, filename: str, result: ExtractionResult) -> None:
    settings.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (settings.REPORT_DIR / f"{doc_id}_ingestion_report.json").write_text(
        json.dumps({"document_id": doc_id, "filename": filename, **result.report}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pages = {img["image_id"]: img for img in result.images}
    with open(settings.REPORT_DIR / f"{doc_id}_image_associations.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["image_id", "image_file", "page", "image_type", "part_number", "association_status", "association_basis", "reviewer_decision"])
        for link in result.links:
            img = pages[link["image_id"]]
            writer.writerow([link["image_id"], img["image_path"], img["page_number"], img["image_type"],
                             link["part_number"], link["association_status"], link["association_basis"], ""])
    with open(settings.REPORT_DIR / f"{doc_id}_review_rows.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["part_number", "page", "reasons"])
        for row in result.report.get("review_rows", []):
            writer.writerow([row.get("part_number"), row.get("page"), " | ".join(row.get("reasons", []))])


def _discard_staged(doc_id: str) -> None:
    """Remove artifacts of an incomplete ingestion (rows, image files, vectors)."""
    try:
        with db() as conn:
            conn.execute("DELETE FROM product_images WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM images WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM products WHERE document_id = ?", (doc_id,))
    except Exception as exc:
        logger.error("Could not clear staged rows for %s: %s", doc_id, exc)
    shutil.rmtree(settings.IMAGE_DIR / doc_id, ignore_errors=True)
    try:
        from backend.app.llm.embeddings import delete_document_vectors
        delete_document_vectors(doc_id)
    except Exception as exc:
        logger.warning("Could not clear staged vectors for %s: %s", doc_id, type(exc).__name__)


def process_document(doc_id: str) -> Dict[str, Any]:
    """Run ingestion for a registered document. Returns the ingestion report; raises IngestionError on failure."""
    with db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise IngestionError("Document not found.")
        if doc["status"] not in (QUEUED, FAILED, "Uploaded"):
            raise IngestionError(f"Document is {doc['status']} and cannot be ingested now.")
        conn.execute(
            "UPDATE documents SET status = ?, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (PROCESSING, doc_id),
        )
        log_event(conn, doc_id, "processing_started", "", doc["filename"])
    pdf_path = Path(doc["file_path"])
    filename = doc["filename"]
    logger.info("Ingesting %s (%s)", filename, doc_id)
    _discard_staged(doc_id)

    try:
        if not pdf_path.exists():
            raise IngestionError("The stored PDF file is missing.")
        try:
            # Opened from memory so a file that fails to parse is never left locked on Windows.
            pdf = pymupdf.open(stream=pdf_path.read_bytes(), filetype="pdf")
        except Exception:
            raise IngestionError("The file could not be opened as a PDF (it may be corrupt).")
        try:
            if pdf.needs_pass:
                raise IngestionError("The PDF is password protected and cannot be read.")
            if len(pdf) == 0:
                raise IngestionError("The PDF has no pages.")
            if len(pdf) > settings.MAX_PDF_PAGES:
                raise IngestionError(f"The PDF has more than {settings.MAX_PDF_PAGES} pages.")
            extractor = _choose_extractor(pdf)
            page_count = len(pdf)
        finally:
            pdf.close()

        image_dir = settings.IMAGE_DIR / doc_id
        result = extractor(pdf_path, doc_id, image_dir)
        if not result.products and extractor is not extract_generic_catalogue:
            shutil.rmtree(image_dir, ignore_errors=True)
            result = extract_generic_catalogue(pdf_path, doc_id, image_dir)
        for product in result.products:
            product["source_pdf"] = filename
        apply_validation(result.products, result.report)
        _apply_image_overrides(result)
        report = result.report
        report["products_extracted"] = len(result.products)
        if not result.products:
            raise IngestionError(
                "No product records could be extracted: the PDF has no table with a recognisable part-number column."
            )

        # Embeddings are a candidate-generation aid. If the embedding model is unavailable the
        # document still becomes searchable through structured retrieval; the gap is reported
        # and repaired by POST /api/admin/reindex.
        embedded = 0
        report["embedding_model"] = None
        if settings.EMBEDDINGS_ENABLED and result.products:
            from backend.app.llm.embeddings import embed_products, upsert_document_vectors
            vectors = embed_products(result.products)
            if vectors is None:
                report["embeddings"] = "skipped: local embedding model unavailable (run reindex when Ollama is up)"
            else:
                embedded = upsert_document_vectors(doc_id, result.products, vectors)
                report["embeddings"] = f"{embedded} product vectors indexed"
                report["embedding_model"] = settings.EMBEDDING_MODEL
        else:
            report["embeddings"] = "disabled" if not settings.EMBEDDINGS_ENABLED else "no products to index"

        _write_reports(doc_id, filename, result)
        with db() as conn:
            conn.executemany(
                f"INSERT INTO products ({', '.join(PRODUCT_COLUMNS)}) VALUES ({', '.join('?' * len(PRODUCT_COLUMNS))})",
                [[p[c] for c in PRODUCT_COLUMNS] for p in result.products],
            )
            conn.executemany(
                f"INSERT INTO images ({', '.join(IMAGE_COLUMNS)}) VALUES ({', '.join('?' * len(IMAGE_COLUMNS))})",
                [[i[c] for c in IMAGE_COLUMNS] for i in result.images],
            )
            conn.executemany(
                f"INSERT INTO product_images ({', '.join(LINK_COLUMNS)}) VALUES ({', '.join('?' * len(LINK_COLUMNS))})",
                [[ln[c] for c in LINK_COLUMNS] for ln in result.links],
            )
            # Single atomic switch: the records and the Ready status commit together.
            conn.execute(
                "UPDATE documents SET status = ?, page_count = ?, ingestion_report = ?, embedded_count = ?, "
                "embedding_model = ?, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (READY, page_count, json.dumps(report, ensure_ascii=False), embedded, report["embedding_model"], doc_id),
            )
            log_event(conn, doc_id, "ready", f"{len(result.products)} products, {len(result.images)} images, {embedded} vectors", filename)
        from backend.app.retrieval import catalogue
        catalogue.invalidate()
        logger.info("Ingestion committed for %s: %d products, %d images, %d links, %d vectors",
                    doc_id, len(result.products), len(result.images), len(result.links), embedded)
        return report
    except Exception as exc:
        message = str(exc) if isinstance(exc, IngestionError) else f"Extraction failed unexpectedly ({type(exc).__name__})."
        logger.error("Ingestion failed for %s: %s", doc_id, exc, exc_info=not isinstance(exc, IngestionError))
        _discard_staged(doc_id)
        with db() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (FAILED, message, doc_id),
            )
            log_event(conn, doc_id, "failed", message, filename)
        raise IngestionError(message) from exc


def find_builtin_pdf(name: str) -> Optional[Path]:
    for folder in (settings.SOURCE_PDFS_DIR, settings.BASE_DIR / "provided_pdfs"):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return None


def register_builtin_catalogues() -> List[str]:
    """Register the two supplied catalogues that are not present yet. Returns the new document ids."""
    new_ids: List[str] = []
    with db() as conn:
        present = {r["id"] for r in conn.execute("SELECT id FROM documents")}
    for doc_id, name in BUILTIN_CATALOGUES:
        if doc_id in present:
            continue
        source = find_builtin_pdf(name)
        if source is None:
            logger.warning("Supplied catalogue not found: %s", name)
            continue
        try:
            new_ids.append(register_document(source, name, doc_id=doc_id, is_builtin=True))
        except DuplicateDocument as dup:
            logger.info("Catalogue %s is already indexed as %s", name, dup.existing_id)
    return new_ids


def ingest_initial_catalogues() -> Dict[str, Any]:
    """Register and ingest the supplied catalogues synchronously (used by scripts and tests)."""
    init_db()
    results: Dict[str, Any] = {}
    for doc_id in register_builtin_catalogues():
        try:
            results[doc_id] = {k: v for k, v in process_document(doc_id).items() if k not in ("source_pages", "review_rows", "rejected_rows")}
        except IngestionError as exc:
            results[doc_id] = {"error": str(exc)}
    return results


if __name__ == "__main__":
    print(json.dumps(ingest_initial_catalogues(), indent=2))
