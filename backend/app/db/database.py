"""SQLite access and versioned schema migrations.

Design decision (docs/DECISIONS.md): product records are source-specific. The
same part number found in two documents is stored as two rows, each owned by
its document, so deleting one document can never remove or alter the other
source's values or provenance. Results are merged per part number at query time.
"""
import sqlite3
from contextlib import contextmanager
from typing import Callable, Iterator, List, Tuple

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Statuses (FR-11)
UPLOADED, QUEUED, PROCESSING, READY, FAILED, DELETING = (
    "Uploaded", "Queued", "Processing", "Ready", "Failed", "Deleting",
)


def get_connection() -> sqlite3.Connection:
    settings.ensure_directories()
    conn = sqlite3.connect(str(settings.SQLITE_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """Connection that commits on success, rolls back on error and always closes."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migration_1(conn: sqlite3.Connection) -> None:
    # Tables written by the pre-migration prototype hold derived data only; they are
    # rebuilt from the source PDFs, so they are dropped rather than converted.
    for table in ("product_images", "products", "documents"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.executescript("""
    CREATE TABLE documents (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_hash TEXT NOT NULL UNIQUE,
        file_path TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        page_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL CHECK (status IN ('Uploaded','Queued','Processing','Ready','Failed','Deleting')),
        error_message TEXT,
        is_builtin INTEGER NOT NULL DEFAULT 0,
        embedding_model TEXT,
        embedded_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ingestion_report TEXT
    );

    CREATE TABLE products (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        manufacturer TEXT,
        part_number TEXT NOT NULL,
        alt_part_number TEXT,
        product_name TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL,
        stylus_type TEXT,
        thread TEXT,
        ball_material TEXT,
        ball_diameter_mm REAL,
        stem_material TEXT,
        stem_diameter_mm REAL,
        overall_length_mm REAL,
        effective_working_length_mm REAL,
        weight_g REAL,
        extra_attributes TEXT,
        raw_attributes TEXT,
        source_pdf TEXT NOT NULL,
        source_page INTEGER NOT NULL,
        source_table TEXT,
        source_section TEXT,
        extraction_confidence REAL NOT NULL DEFAULT 1.0,
        validation_status TEXT NOT NULL DEFAULT 'validated'
            CHECK (validation_status IN ('validated','needs_review','rejected')),
        review_reason TEXT
    );
    CREATE INDEX idx_products_part_number ON products (part_number);
    CREATE INDEX idx_products_alt_part_number ON products (alt_part_number);
    CREATE INDEX idx_products_thread ON products (thread);
    CREATE INDEX idx_products_category ON products (category);
    CREATE INDEX idx_products_document_id ON products (document_id);

    -- One row per stored image file.
    CREATE TABLE images (
        image_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL,
        image_path TEXT NOT NULL,
        image_type TEXT NOT NULL CHECK (image_type IN ('photograph','drawing','diagram','unknown')),
        image_hash TEXT NOT NULL,
        extraction_metadata TEXT
    );
    CREATE INDEX idx_images_document_id ON images (document_id);

    -- Many-to-many product <-> image associations with their verification status.
    CREATE TABLE product_images (
        image_id TEXT NOT NULL REFERENCES images (image_id) ON DELETE CASCADE,
        product_id TEXT NOT NULL REFERENCES products (id) ON DELETE CASCADE,
        document_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        part_number TEXT NOT NULL,
        association_status TEXT NOT NULL CHECK (association_status IN ('verified','unverified','rejected')),
        association_basis TEXT,
        PRIMARY KEY (image_id, product_id)
    );
    CREATE INDEX idx_product_images_part_number ON product_images (part_number);
    CREATE INDEX idx_product_images_document_id ON product_images (document_id);

    -- Traceable lifecycle log (ingestion and deletion steps).
    CREATE TABLE document_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL,
        filename TEXT,
        event TEXT NOT NULL,
        detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_document_events_document_id ON document_events (document_id);

    -- Runtime settings changed through the API.
    CREATE TABLE app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)


MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "source-specific products, image/link split, lifecycle log, persisted settings", _migration_1),
]


def init_db() -> None:
    """Apply any pending schema migrations. Safe to call repeatedly."""
    conn = get_connection()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for version, description, migrate in MIGRATIONS:
            if version in applied:
                continue
            logger.info("Applying schema migration %d: %s", version, description)
            migrate(conn)
            conn.execute("INSERT INTO schema_migrations (version, description) VALUES (?, ?)", (version, description))
            conn.commit()
    finally:
        conn.close()


def schema_version() -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return row[0] or 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def log_event(conn: sqlite3.Connection, document_id: str, event: str, detail: str = "", filename: str = "") -> None:
    conn.execute(
        "INSERT INTO document_events (document_id, filename, event, detail) VALUES (?, ?, ?, ?)",
        (document_id, filename, event, detail),
    )


if __name__ == "__main__":
    init_db()
