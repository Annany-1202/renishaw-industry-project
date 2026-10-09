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


def check_relevance(query_text: str, parsed: ParsedQuery) -> Tuple[bool, Optional[str]]:
    words = re.findall(r"[a-z]+", (query_text or "").lower())
    foreign = next((w for w in words if w in domain.FOREIGN_TERMS), None)
    if foreign:
        return False, (
            f"The request is about '{foreign}', which is not a product in the indexed catalogues. "
            "The catalogues cover Renishaw styli, extensions, adaptors and accessories."
        )
    if parsed.is_irrelevant:
        return False, parsed.irrelevance_reason or (
            "The request does not describe a product covered by the indexed catalogues "
            "(Renishaw styli, extensions, adaptors and accessories)."
        )
    return True, None


def check_conflicting_constraints(query: ParsedQuery, raw_text: str = "") -> Tuple[bool, Optional[str]]:
    if query.has_conflicting_constraints:
        return True, query.conflict_description or "The request contains requirements that contradict each other."
    return False, None
