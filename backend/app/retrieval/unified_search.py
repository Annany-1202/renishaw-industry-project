"""Search entry point: interpret (rules, optional local LLM) then run the deterministic engine."""
import time
from typing import Any, Dict, Optional

from backend.app.core.logging import logger
from backend.app.ingestion.normalizer import normalize_material, normalize_thread
from backend.app.llm.query_interpreter import FIELD_LABELS, finalise, interpret_query, refine_query
from backend.app.matching.engine import execute_deterministic_search
from backend.app.matching.schemas import (
    ALLOWED_CATEGORIES, HARD_CAPABLE, NUMERIC_ATTRIBUTES, ParsedQuery, RequestedAttribute, SearchResponse,
)

MAX_QUERY_CHARS = 1000
EDITABLE = set(HARD_CAPABLE)


class InvalidOverride(ValueError):
    pass


def apply_overrides(previous: Optional[Dict[str, Any]], overrides: Dict[str, Any], query_text: str) -> ParsedQuery:
    """Apply attribute edits made in the UI to the earlier interpretation.

    Only attribute values and the hard/flexible lists can be edited; every value
    is validated again. Scope, conflict and clarification flags cannot be set
    from outside.
    """
    try:
        base = ParsedQuery(**(previous or {"original_query": query_text}))
    except Exception:
        base = ParsedQuery(original_query=query_text)
    unknown = set(overrides) - EDITABLE - {"hard_constraints", "flexible_preferences"}
    if unknown:
        raise InvalidOverride(f"These fields cannot be edited: {', '.join(sorted(unknown))}")
    data = base.model_dump()
    for field in EDITABLE & set(overrides):
        value = overrides[field]
        if value in ("", None):
            value = None
        elif field in NUMERIC_ATTRIBUTES:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise InvalidOverride(f"{FIELD_LABELS[field]} must be a number in millimetres.")
        elif field in ("thread", "secondary_thread"):
            value = normalize_thread(str(value))
            if value is None:
                raise InvalidOverride("Thread must look like M2, M3, M4 or M5.")
        elif field == "category":
            value = str(value).strip().lower()
            if value not in ALLOWED_CATEGORIES:
                raise InvalidOverride(f"Product type must be one of: {', '.join(ALLOWED_CATEGORIES)}.")
        elif field in ("ball_material", "stem_material"):
            value = normalize_material(str(value)) or str(value).strip()[:60]
        else:
            value = str(value).strip().lower()[:40]
        data[field] = value
        data["inch_inputs"].pop(field, None)
        data["requested_attributes"] = [a for a in data["requested_attributes"] if a["name"] != field]
        if value is not None:
            data["requested_attributes"].append(RequestedAttribute(
                name=field, value=value, unit="mm" if field in NUMERIC_ATTRIBUTES else None, source="manual",
            ).model_dump())
    for key in ("hard_constraints", "flexible_preferences"):
        if key in overrides:
            if not isinstance(overrides[key], list) or not all(isinstance(x, str) for x in overrides[key]):
                raise InvalidOverride(f"{key} must be a list of attribute names.")
            data[key] = overrides[key]
    data["hard_constraints"] = [f for f in data["hard_constraints"] if data.get(f) is not None]
    data["flexible_preferences"] = [f for f in data["flexible_preferences"]
                                    if data.get(f) is not None and f not in data["hard_constraints"]]
    for attr in data["requested_attributes"]:
        attr["is_hard_constraint"] = attr["name"] in data["hard_constraints"]
    data.update(has_conflicting_constraints=False, conflict_description=None, clarification_needed=False,
                clarification_type=None, clarification_question=None, suggested_options=[],
                is_irrelevant=base.is_irrelevant, interpreter="manual")
    try:
        edited = ParsedQuery(**data)
    except Exception:
        raise InvalidOverride("One of the edited values is out of range.")
    if "Attributes were edited manually." not in edited.assumptions:
        edited.assumptions.append("Attributes were edited manually.")
    edited.unspecified_attributes = [f for f in FIELD_LABELS if getattr(edited, f, None) is None]
    return finalise(edited, asked_before=base.clarification_type)


def search_products(query_text: str, clarification_answer: Optional[str] = None,
                    previous_query: Optional[Dict[str, Any]] = None,
                    manual_overrides: Optional[Dict[str, Any]] = None) -> SearchResponse:
    started = time.perf_counter()
    query_text = (query_text or "").strip()[:MAX_QUERY_CHARS]
    if manual_overrides:
        parsed = apply_overrides(previous_query, manual_overrides, query_text)
    elif clarification_answer and previous_query:
        parsed = refine_query(previous_query, clarification_answer.strip()[:MAX_QUERY_CHARS])
    else:
        parsed = interpret_query(query_text)
    raw = parsed.original_query or query_text
    interpreted_ms = (time.perf_counter() - started) * 1000
    response = execute_deterministic_search(parsed, raw_query_text=raw)
    response.diagnostics["interpretation_ms"] = round(interpreted_ms, 2)
    response.diagnostics["retrieval_ranking_ms"] = response.execution_time_ms
    response.diagnostics["interpreter"] = parsed.interpreter
    response.execution_time_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info("search id=%s outcome=%s results=%d llm=%s %.0f ms", response.search_id, response.outcome,
                len(response.results), parsed.llm_used, response.execution_time_ms)
    return response
