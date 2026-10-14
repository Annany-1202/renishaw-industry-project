"""Relevance gate (specification 9.7).

A request is searched only when BOTH hold:
  1. it has a plausible product-category interpretation (a recognised product
     noun, a part number, a probe/stylus context, or nothing but stylus
     attributes), and names no product from outside the catalogues; and
  2. at least one candidate meets the ranking policy (enforced by the engine:
     hard constraints, minimum score, dimensions within the deviation scale).
Embedding similarity is never used to admit a request.
"""
import re
from typing import Optional, Tuple

from backend.app.matching import domain
from backend.app.matching.schemas import ParsedQuery


NOT_RELATED = "This request is not related to the uploaded catalogues."
CATEGORY_PLURALS = {
    "stylus": "styli", "extension": "stylus extensions", "adaptor": "thread adaptors", "knuckle": "knuckles",
    "cube": "stylus cubes", "holder": "stylus holders", "kit": "stylus kits", "tool": "stylus tools",
    "accessory": "accessories",
}


def out_of_scope_message(detail: Optional[str] = None) -> str:
    """The answer to a request outside the catalogues: says so plainly and states what can be searched."""
    try:
        from backend.app.retrieval import catalogue
        names, counts = catalogue.document_names(), catalogue.category_counts()
    except Exception:
        names, counts = [], {}
    parts = [NOT_RELATED]
    if detail:
        parts.append(detail)
    if names:
        covered = [CATEGORY_PLURALS.get(c, c) for c in CATEGORY_PLURALS if counts.get(c)]
        parts.append(f"The indexed catalogues ({', '.join(names)}) cover {', '.join(covered) or 'CMM styli'}.")
    else:
        parts.append("No catalogue is indexed yet.")
    parts.append("Describe a catalogue product to search, for example 'M3 stylus with 2 mm ruby ball'.")
    return " ".join(parts)


def check_relevance(query_text: str, parsed: ParsedQuery) -> Tuple[bool, Optional[str]]:
    words = re.findall(r"[a-z]+", (query_text or "").lower())
    foreign = next((w for w in words if w in domain.FOREIGN_TERMS), None)
    if foreign:
        return False, out_of_scope_message(f"It asks about '{foreign}', which is not a product in them.")
    if parsed.is_irrelevant:
        return False, out_of_scope_message(parsed.irrelevance_reason)
    return True, None


def check_conflicting_constraints(query: ParsedQuery, raw_text: str = "") -> Tuple[bool, Optional[str]]:
    if query.has_conflicting_constraints:
        return True, query.conflict_description or "The request contains requirements that contradict each other."
    return False, None
