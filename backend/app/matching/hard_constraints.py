"""Hard-constraint evaluation.

A hard constraint is satisfied only by a verified MATCH. A catalogue record
that does not state the attribute cannot satisfy it: unknown is not a match.
No score can compensate for a violation.
"""
from typing import Any, Dict, List, Tuple

from backend.app.matching.schemas import ParsedQuery
from backend.app.matching.scoring import compare


def evaluate_hard_constraints(query: ParsedQuery, product: Dict[str, Any]) -> Tuple[bool, List[str]]:
    _, _, violations = compare(query, product)
    return (not violations), violations
