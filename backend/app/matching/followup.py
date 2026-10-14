"""Follow-up questions that narrow a broad result set.

When more products are eligible than can be shown, the response still lists
them and also asks about the most decisive attribute the request leaves open.
The options are values the eligible products actually have (with how many
products have each), and an option is offered only if the query parser reads
it back as exactly that value, so every option leads to at least one product.
Answering goes through the normal clarification path: the earlier
interpretation, its hard constraints and the original request are kept.
"""
from collections import Counter
from typing import Any, Dict, List, Optional

from backend.app.matching import domain
from backend.app.matching.schemas import TIP_ATTRIBUTES, TIPLESS_CATEGORIES, ParsedQuery

MAX_OPTIONS = 8
# Most decisive first: the product type and the mounting interface before dimensions and materials.
FIELDS = [
    ("category", "product type"), ("thread", "mounting thread"), ("ball_diameter_mm", "ball diameter"),
    ("overall_length_mm", "overall length"), ("ball_material", "ball material"), ("stem_material", "stem material"),
]


def _option_text(field: str, value: Any) -> Optional[str]:
    if field == "category":
        return domain.CATEGORY_OPTION_LABELS.get(value)
    if field == "thread":
        return str(value)
    if field == "ball_diameter_mm":
        return f"{float(value):g} mm ball"
    if field == "overall_length_mm":
        return f"{float(value):g} mm long"
    if field == "ball_material":
        return f"{value} ball"
    if field == "stem_material":
        return f"{value} stem"
    return None


def _reads_back(field: str, text: str, value: Any) -> bool:
    from backend.app.llm.query_interpreter import rule_based_query_parser
    parsed = getattr(rule_based_query_parser(text, vocabulary=set()), field)
    if isinstance(value, float):
        return parsed is not None and abs(float(parsed) - value) < 1e-9
    return parsed is not None and str(parsed).lower() == str(value).lower()


def narrowing_question(query: ParsedQuery, products: List[Dict[str, Any]], shown: int) -> Optional[Dict[str, Any]]:
    """A question about one open attribute that splits the eligible products, or None."""
    total = len(products)
    if total <= shown:
        return None
    asked = set(query.clarification_history)
    for field, label in FIELDS:
        if getattr(query, field) is not None or f"NARROW:{field}" in asked:
            continue
        if field in TIP_ATTRIBUTES and query.category in TIPLESS_CATEGORIES:
            continue
        counts = Counter(p.get(field) for p in products if p.get(field) not in (None, ""))
        if len(counts) < 2:
            continue  # every eligible product has the same value: asking would not narrow anything
        common = counts.most_common(MAX_OPTIONS * 2)
        if field.endswith("_mm"):
            common = sorted(common[:MAX_OPTIONS], key=lambda vc: vc[0])
        options, option_counts = [], []
        for value, count in common:
            text = _option_text(field, value)
            if text and text not in options and _reads_back(field, text, value):
                options.append(text)
                option_counts.append(count)
            if len(options) == MAX_OPTIONS:
                break
        if len(options) < 2:
            continue
        unlisted = total - sum(counts.values())
        note = f" ({unlisted} do not state it)" if unlisted else ""
        return {
            "type": "NARROW_RESULTS",
            "attribute": field,
            "question": f"{total} products are eligible{note}. Which {label} do you need?",
            "options": options,
            "option_counts": option_counts,
        }
    return None
