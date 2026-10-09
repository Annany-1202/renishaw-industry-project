"""Deterministic attribute comparison and scoring.

S(p, q) = 100 * sum(w_i * s_i) / sum(w_i) over the attributes the request
names and that apply to the product type. Numeric attributes use
s_i = max(0, 1 - |x - y| / tau_i); categorical attributes need exact agreement.
An attribute the catalogue record does not state is UNKNOWN and scores 0: it
is never counted as a confirmed match.
"""
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.config import settings
from backend.app.ingestion.normalizer import MM_PER_INCH
from backend.app.matching.schemas import AttributeComparison, ParsedQuery

LABELS = {
    "thread": "Thread", "secondary_thread": "Second thread", "category": "Product type", "stylus_type": "Type", "descriptor": "Described as",
    "ball_material": "Ball/tip material", "ball_diameter_mm": "Ball/tip diameter",
    "stem_material": "Stem/body material", "stem_diameter_mm": "Stem diameter",
    "overall_length_mm": "Overall length", "effective_working_length_mm": "Effective working length",
}
NUMERIC = {
    # field: (weight attribute, tolerance attribute)
    "ball_diameter_mm": ("ball_diameter", "ball_diameter"),
    "overall_length_mm": ("overall_length", "overall_length"),
    "stem_diameter_mm": ("other_dimensions", "stem_diameter"),
    "effective_working_length_mm": ("other_dimensions", "effective_working_length"),
}
EPSILON = 5e-4  # mm; absorbs float noise only


def deviation_scale(field: str, requested: float) -> float:
    """tau for a numeric attribute: the larger of the absolute and the relative scale."""
    name = NUMERIC[field][1]
    tol = settings.TOLERANCES
    return max(getattr(tol, name), getattr(tol, f"{name}_rel") * abs(requested))


def numeric_equal(requested_mm: float, product_mm: float, inch_input: Optional[Dict[str, float]]) -> Tuple[bool, Optional[str]]:
    """Whether a catalogue value equals the requested one.

    Millimetre requests must agree exactly. A request typed in inches matches a
    catalogue millimetre value only if both are the same number at the
    precision the user typed (0.08 in <-> 2.0 mm, which the catalogue itself
    prints as '2.0 (0.08)') and the two differ by less than the configured
    relative amount, so rounding cannot merge materially different sizes.
    """
    if abs(requested_mm - product_mm) <= EPSILON:
        return True, None
    if inch_input:
        decimals = int(inch_input.get("decimals", 2))
        inches = float(inch_input["inches"])
        same_at_precision = round(product_mm / MM_PER_INCH, decimals) == round(inches, decimals)
        close = abs(product_mm - requested_mm) <= settings.INCH_INPUT_REL_TOL * requested_mm
        if same_at_precision and close:
            return True, (
                f"{inches:g} in = {requested_mm:g} mm; the catalogue value {product_mm:g} mm is "
                f"{product_mm / MM_PER_INCH:.{decimals}f} in at the precision you typed"
            )
    return False, None


def _product_threads(product: Dict[str, Any]) -> List[str]:
    threads = []
    if product.get("thread"):
        threads.append(str(product["thread"]).upper())
    for t in (product.get("extra_attributes") or {}).get("threads", []) or []:
        if str(t).upper() not in threads:
            threads.append(str(t).upper())
    return threads


def compare(query: ParsedQuery, product: Dict[str, Any]) -> Tuple[float, List[AttributeComparison], List[str]]:
    """Return (score 0-100, per-attribute comparisons, hard-constraint violations)."""
    rows: List[AttributeComparison] = []
    weights = settings.WEIGHTS
    hard = set(query.hard_constraints)
    ignored = set(query.ignored_attributes)

    def add(name: str, requested: Any, value: Any, status: str, weight: float, score: float,
            unit: Optional[str] = None, diff: Optional[str] = None, note: Optional[str] = None) -> None:
        rows.append(AttributeComparison(
            attribute_name=name, label=LABELS.get(name, name), requested_value=requested, product_value=value,
            unit=unit, status=status, is_hard=name in hard, weight=round(weight, 3), score=round(score, 4),
            difference_description=diff, note=note,
        ))

    # Thread / mounting interface (a thread adaptor request names two threads; both must be present)
    wanted_threads = [(n, getattr(query, n)) for n in ("thread", "secondary_thread") if getattr(query, n)]
    for name, wanted in wanted_threads:
        weight = weights.thread / len(wanted_threads)
        threads = _product_threads(product)
        shown = "/".join(threads) if threads else None
        if not threads:
            add(name, wanted, None, "UNKNOWN", weight, 0.0,
                diff="The catalogue record does not state a mounting thread, so compatibility cannot be verified.")
        elif wanted.upper() in threads:
            add(name, wanted, shown, "MATCH", weight, 1.0)
        else:
            add(name, wanted, shown, "DIFFERS", weight, 0.0, diff=f"Thread is {shown}, not {wanted}.")

    # Product type and application suitability (category, type, descriptive terms)
    type_parts: List[Tuple[str, Any, Any, bool, Optional[str]]] = []
    if query.category:
        ok = (product.get("category") or "").lower() == query.category.lower()
        type_parts.append(("category", query.category, product.get("category"), ok,
                           None if ok else f"Catalogue lists this as {product.get('category')}, not {query.category}."))
    if query.stylus_type:
        ok = (product.get("stylus_type") or "").lower() == query.stylus_type.lower()
        type_parts.append(("stylus_type", query.stylus_type, product.get("stylus_type"), ok,
                           None if ok else f"Type is {product.get('stylus_type')}, not {query.stylus_type}."))
    if query.descriptor_terms:
        tokens = product.get("_tokens") or set()
        found = [t for t in query.descriptor_terms if t in tokens]
        missing = [t for t in query.descriptor_terms if t not in tokens]
        type_parts.append(("descriptor", ", ".join(query.descriptor_terms), ", ".join(found) or None, not missing,
                           None if not missing else f"Catalogue description does not mention: {', '.join(missing)}."))
    for name, requested, value, ok, diff in type_parts:
        share = weights.category / len(type_parts)
        if name == "descriptor" and not ok:
            fraction = len([t for t in query.descriptor_terms if t in (product.get("_tokens") or set())]) / len(query.descriptor_terms)
            add(name, requested, value, "DIFFERS", share, fraction, diff=diff)
        else:
            add(name, requested, value, "MATCH" if ok else "DIFFERS", share, 1.0 if ok else 0.0, diff=diff)

    # Numeric dimensions
    for field, (weight_name, _) in NUMERIC.items():
        requested = getattr(query, field)
        if requested is None or field in ignored:
            continue
        weight = getattr(weights, weight_name)
        value = product.get(field)
        if value is None:
            add(field, requested, None, "UNKNOWN", weight, 0.0, unit="mm",
                diff=f"{LABELS[field]} is not stated in the catalogue record.")
            continue
        equal, note = numeric_equal(requested, value, query.inch_inputs.get(field))
        if equal:
            add(field, requested, value, "MATCH", weight, 1.0, unit="mm", note=note)
        else:
            tau = deviation_scale(field, requested)
            diff = value - requested
            add(field, requested, value, "DIFFERS", weight, max(0.0, 1.0 - abs(diff) / tau), unit="mm",
                diff=f"{LABELS[field]} is {value:g} mm, {abs(diff):g} mm {'more' if diff > 0 else 'less'} than the {requested:g} mm requested.")

    # Materials: exact agreement (no substitution rule is approved)
    for field, weight in (("stem_material", weights.stem_material), ("ball_material", weights.ball_material)):
        requested = getattr(query, field)
        if not requested or field in ignored:
            continue
        value = product.get(field)
        if not value:
            add(field, requested, None, "UNKNOWN", weight, 0.0,
                diff=f"{LABELS[field]} is not stated in the catalogue record.")
        elif value.strip().lower() == requested.strip().lower():
            add(field, requested, value, "MATCH", weight, 1.0)
        else:
            add(field, requested, value, "DIFFERS", weight, 0.0, diff=f"{LABELS[field]} is {value}, not {requested}.")

    total = sum(r.weight for r in rows)
    score = 100.0 * sum(r.weight * r.score for r in rows) / total if total > 0 else 100.0
    violations = [
        f"{r.label}: requested {r.requested_value}, catalogue "
        f"{'does not state it' if r.status == 'UNKNOWN' else 'has ' + str(r.product_value)}"
        for r in rows if r.is_hard and r.status != "MATCH"
    ]
    return round(score, 2), rows, violations


def within_deviation_scale(rows: List[AttributeComparison]) -> bool:
    """False when a requested dimension differs by the full deviation scale or more."""
    return not any(r.attribute_name in NUMERIC and r.status == "DIFFERS" and r.score <= 0.0 for r in rows)


# Backwards-compatible name used by older callers/tests.
def compute_attribute_score_and_diffs(query: ParsedQuery, product: Dict[str, Any]):
    score, rows, _ = compare(query, product)
    matching = [f"{r.label}: {r.product_value}" for r in rows if r.status == "MATCH"]
    differing = [r.difference_description or r.label for r in rows if r.status == "DIFFERS"]
    missing = [r.difference_description or r.label for r in rows if r.status == "UNKNOWN"]
    return score, rows, matching, differing, missing
