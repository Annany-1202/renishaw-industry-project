"""Deterministic validation of extracted records before they are persisted."""
import json
import re
from typing import Any, Dict, List

from backend.app.ingestion.models import NEEDS_REVIEW, VALIDATED
from backend.app.ingestion.normalizer import CATEGORIES

PART_NUMBER_OK = re.compile(r"^[A-Z0-9]{1,8}(-[A-Z0-9]{2,8}){1,3}$")

# (field, lower bound exclusive, upper bound inclusive, unit)
RANGES = [
    ("ball_diameter_mm", 0.0, 150.0, "mm"),
    ("stem_diameter_mm", 0.0, 150.0, "mm"),
    ("overall_length_mm", 0.0, 2000.0, "mm"),
    ("effective_working_length_mm", 0.0, 2000.0, "mm"),
    ("weight_g", 0.0, 100000.0, "g"),
]


def validate_product(product: Dict[str, Any]) -> List[str]:
    """Return the validation problems of a record (empty list means it passes)."""
    problems: List[str] = []
    if not PART_NUMBER_OK.match(product.get("part_number") or ""):
        problems.append(f"part number '{product.get('part_number')}' has an unexpected format")
    if product.get("category") not in CATEGORIES:
        problems.append(f"unknown category '{product.get('category')}'")
    for field, low, high, unit in RANGES:
        value = product.get(field)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or value != value:
            problems.append(f"{field} is not a number")
        elif not (low < value <= high):
            problems.append(f"{field} = {value:g} {unit} is outside the plausible range ({low:g}, {high:g}]")
    try:
        json.loads(product.get("raw_attributes") or "{}")
        json.loads(product.get("extra_attributes") or "{}")
    except ValueError:
        problems.append("attribute JSON is malformed")
    return problems


def apply_validation(products: List[Dict[str, Any]], report: Dict[str, Any]) -> None:
    """Downgrade records that fail validation to needs_review and record why."""
    for product in products:
        problems = validate_product(product)
        if not problems:
            continue
        if product["validation_status"] == VALIDATED:
            report["rows_validated"] -= 1
            report["rows_needs_review"] += 1
        product["validation_status"] = NEEDS_REVIEW
        product["extraction_confidence"] = min(product.get("extraction_confidence", 1.0), 0.5)
        product["review_reason"] = "; ".join(filter(None, [product.get("review_reason")] + problems))
        report["review_rows"].append({
            "part_number": product["part_number"], "page": product["source_page"], "reasons": problems,
        })
