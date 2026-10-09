"""Local vector index (ChromaDB, telemetry off) over product descriptions.

Embedding similarity is a candidate-generation signal only: every semantic hit
is re-read from SQLite (Ready documents only) and must pass the deterministic
checks before it can be shown. A vector whose document is not Ready can
therefore never surface, even before reconciliation removes it.
"""
import os
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

import chromadb  # noqa: E402
from chromadb.config import Settings as ChromaSettings  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.core.logging import logger  # noqa: E402
from backend.app.db.database import READY, db  # noqa: E402
from backend.app.llm.ollama_client import ollama_client  # noqa: E402

COLLECTION_NAME = "renishaw_products"
_clients: Dict[str, Any] = {}


def get_chroma_client():
    path = str(settings.CHROMA_DIR)
    if path not in _clients:
        settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _clients[path] = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
    return _clients[path]


def get_or_create_collection():
    return get_chroma_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_model": settings.EMBEDDING_MODEL},
    )


def collection_model() -> Optional[str]:
    return (get_or_create_collection().metadata or {}).get("embedding_model")


def product_text(row: Dict[str, Any]) -> str:
    """Text embedded for a product: catalogue wording only (treated as data, never as instructions)."""
    parts = [
        f"{row.get('category') or ''} {row.get('stylus_type') or ''}".strip(),
        row.get("source_section") or "",
        row.get("description") or "",
        f"thread {row['thread']}" if row.get("thread") else "",
        f"{row['ball_material']} ball {row['ball_diameter_mm']:g} mm" if row.get("ball_material") and row.get("ball_diameter_mm") is not None else "",
        f"{row['stem_material']} stem" if row.get("stem_material") else "",
        f"length {row['overall_length_mm']:g} mm" if row.get("overall_length_mm") is not None else "",
    ]
    return ". ".join(p for p in parts if p)[:500]


def embed_products(rows: List[Dict[str, Any]]) -> Optional[List[List[float]]]:
    """Embed product rows in batches. None means the embedding model is unavailable."""
    vectors: List[List[float]] = []
    texts = [product_text(r) for r in rows]
    for i in range(0, len(texts), settings.EMBEDDING_BATCH_SIZE):
        batch = ollama_client.embed(texts[i:i + settings.EMBEDDING_BATCH_SIZE])
        if batch is None:
            return None
        vectors.extend(batch)
    return vectors


def upsert_document_vectors(doc_id: str, rows: List[Dict[str, Any]], vectors: List[List[float]]) -> int:
    coll = get_or_create_collection()
    for i in range(0, len(rows), 200):
        chunk = rows[i:i + 200]
        coll.upsert(
            ids=[r["id"] for r in chunk],
            embeddings=vectors[i:i + 200],
            documents=[product_text(r) for r in chunk],
            metadatas=[{"document_id": doc_id, "part_number": r["part_number"]} for r in chunk],
        )
    return len(rows)


def delete_document_vectors(doc_id: str) -> int:
    """Remove every vector owned by a document. Raises on failure so deletion is never reported falsely."""
    coll = get_or_create_collection()
    ids = coll.get(where={"document_id": doc_id}, include=[]).get("ids", [])
    if ids:
        coll.delete(ids=ids)
    return len(ids)


def count_document_vectors(doc_id: str) -> int:
    coll = get_or_create_collection()
    return len(coll.get(where={"document_id": doc_id}, include=[]).get("ids", []))


def semantic_search(query_text: str, limit: Optional[int] = None) -> List[Tuple[str, float]]:
    """Return [(product_id, cosine similarity)] for the query, best first. Empty when unavailable."""
    if not settings.EMBEDDINGS_ENABLED:
        return []
    try:
        coll = get_or_create_collection()
        if coll.count() == 0:
            return []
        vectors = ollama_client.embed([query_text[:500]])
        if not vectors:
            return []
        res = coll.query(query_embeddings=vectors, n_results=min(limit or settings.SEMANTIC_CANDIDATE_LIMIT, coll.count()))
        ids = (res.get("ids") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        return [(pid, round(1.0 - float(d), 4)) for pid, d in zip(ids, distances)]
    except Exception as exc:
        logger.warning("Semantic search unavailable: %s", type(exc).__name__)
        return []


def reindex_all() -> Dict[str, Any]:
    """Rebuild the whole index from Ready documents with the configured embedding model."""
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    summary: Dict[str, Any] = {"embedding_model": settings.EMBEDDING_MODEL, "documents": {}, "indexed_items": 0}
    with db() as conn:
        docs = [r["id"] for r in conn.execute("SELECT id FROM documents WHERE status = ?", (READY,))]
    for doc_id in docs:
        with db() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM products WHERE document_id = ?", (doc_id,))]
        vectors = embed_products(rows) if rows else []
        if vectors is None:
            summary["documents"][doc_id] = "embedding model unavailable"
            count = 0
        else:
            count = upsert_document_vectors(doc_id, rows, vectors) if rows else 0
            summary["documents"][doc_id] = count
        with db() as conn:
            conn.execute(
                "UPDATE documents SET embedded_count = ?, embedding_model = ? WHERE id = ?",
                (count, settings.EMBEDDING_MODEL if count else None, doc_id),
            )
        summary["indexed_items"] += count
    return summary


def index_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {"ready": False, "item_count": 0, "expected_count": 0, "in_sync": False}
    try:
        coll = get_or_create_collection()
        status["ready"] = True
        status["item_count"] = coll.count()
        status["embedding_model"] = (coll.metadata or {}).get("embedding_model")
        with db() as conn:
            status["expected_count"] = conn.execute(
                "SELECT count(*) FROM products p JOIN documents d ON d.id = p.document_id WHERE d.status = ?", (READY,)
            ).fetchone()[0]
        status["model_matches_config"] = status["embedding_model"] == settings.EMBEDDING_MODEL
        status["in_sync"] = status["item_count"] == status["expected_count"] and status["model_matches_config"]
    except Exception as exc:
        status["error"] = "Vector index could not be opened."
        logger.warning("Vector index status failed: %s", exc)
    return status
