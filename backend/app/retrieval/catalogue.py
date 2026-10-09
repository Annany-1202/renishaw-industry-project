"""Read access to the active catalogue (products of Ready documents only)."""
import json
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.db.database import READY, db
from backend.app.matching.domain import STOPWORDS

_lock = threading.Lock()
_cache: Dict[str, Any] = {"version": None, "products": [], "vocabulary": set(), "threads": []}


def _data_version(conn) -> Tuple:
    row = conn.execute(
        "SELECT count(*), coalesce(max(updated_at), ''), coalesce(sum(length(id)), 0) FROM documents WHERE status = ?",
        (READY,),
    ).fetchone()
    return tuple(row)


def _load() -> Dict[str, Any]:
    with db() as conn:
        version = _data_version(conn)
        with _lock:
            if _cache["version"] == version:
                return _cache
        rows = conn.execute(
            "SELECT p.*, d.filename AS doc_filename FROM products p JOIN documents d ON d.id = p.document_id "
            "WHERE d.status = ? ORDER BY p.part_number, p.document_id",
            (READY,),
        ).fetchall()
    products: List[Dict[str, Any]] = []
    vocabulary: Set[str] = set()
    threads: Set[str] = set()
    for row in rows:
        p = dict(row)
        for key in ("extra_attributes", "raw_attributes"):
            try:
                p[key] = json.loads(p[key]) if p[key] else {}
            except ValueError:
                p[key] = {}
        text = " ".join(str(v) for v in (
            p.get("description"), p.get("source_section"), p.get("stylus_type"),
            p["extra_attributes"].get("component"), p["extra_attributes"].get("notes"),
        ) if v).lower()
        p["_search_text"] = text
        p["_tokens"] = set(re.findall(r"[a-z][a-z0-9]{2,}", text.replace("_", " ")))
        # Descriptor vocabulary: real words only (catalogue codes such as 'd3r' or 'l30' are excluded).
        vocabulary |= {t for t in p["_tokens"] if t.isalpha() and len(t) >= 4 and t not in STOPWORDS}
        if p.get("thread") and re.fullmatch(r"M\d{1,2}", p["thread"]):
            threads.add(p["thread"])
        products.append(p)
    with _lock:
        _cache.update(version=version, products=products, vocabulary=vocabulary,
                      threads=sorted(threads, key=lambda t: int(t[1:])))
        return _cache


def active_products() -> List[Dict[str, Any]]:
    return _load()["products"]


def vocabulary() -> Set[str]:
    return _load()["vocabulary"]


def available_threads() -> List[str]:
    return _load()["threads"]


def invalidate() -> None:
    with _lock:
        _cache["version"] = None


def verified_images(part_numbers: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Verified images of the given part numbers across every Ready document."""
    if not part_numbers:
        return {}
    marks = ",".join("?" * len(part_numbers))
    with db() as conn:
        rows = conn.execute(
            f"SELECT l.part_number, l.association_status, l.association_basis, i.image_id, i.document_id, "
            f"i.page_number, i.image_type, i.image_hash, i.extraction_metadata, d.filename "
            f"FROM product_images l JOIN images i ON i.image_id = l.image_id "
            f"JOIN documents d ON d.id = i.document_id "
            f"WHERE l.part_number IN ({marks}) AND l.association_status = 'verified' AND d.status = ? "
            f"ORDER BY l.part_number, d.filename, i.page_number, i.image_id",
            (*part_numbers, READY),
        ).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["part_number"], []).append(dict(row))
    return out


def find_by_part_number(part_number: str) -> List[Dict[str, Any]]:
    wanted = part_number.upper()
    return [
        p for p in active_products()
        if p["part_number"].upper() == wanted
        or wanted in [a.strip().upper() for a in (p.get("alt_part_number") or "").split(",")]
    ]
