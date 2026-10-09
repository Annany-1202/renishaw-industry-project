"""Deterministic search engine.

Pipeline (specification 9.6): reject unsupported requests -> stop on
contradictions / needed clarifications -> evaluate every record of the active
catalogues -> drop hard-constraint violators -> exact matches, else eligible
alternatives -> merge the same part number across documents -> rank -> attach
verified images and grounded explanations. Nothing is ever padded: if no record
passes, the answer is "no suitable product".

The LLM takes no part in any step of this module.
"""
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.config import settings
from backend.app.matching.explainer import explain
from backend.app.matching.relevance_gate import check_conflicting_constraints, check_relevance
from backend.app.matching.schemas import (
    AttributeComparison, ImageInfo, ParsedQuery, ProductMatch, SearchResponse, SourceReference,
)
from backend.app.matching.scoring import compare, within_deviation_scale
from backend.app.retrieval import catalogue

EXACT, ALTERNATIVE, NO_MATCH = "EXACT_MATCH", "ALTERNATIVE", "NO_MATCH"
PRODUCT_FIELDS = (
    "manufacturer", "part_number", "alt_part_number", "product_name", "description", "category", "stylus_type",
    "thread", "ball_material", "ball_diameter_mm", "stem_material", "stem_diameter_mm", "overall_length_mm",
    "effective_working_length_mm", "weight_g", "source_page", "source_table", "validation_status", "review_reason",
)


def _response(query: ParsedQuery, raw: str, started: float, **kwargs: Any) -> SearchResponse:
    kwargs.setdefault("result_class", NO_MATCH)
    return SearchResponse(
        search_id=uuid.uuid4().hex[:12], query=raw, interpreted_query=query,
        execution_time_ms=round((time.perf_counter() - started) * 1000, 2), **kwargs,
    )


def _classify(query: ParsedQuery, product: Dict[str, Any]) -> Tuple[Optional[str], float, List[AttributeComparison], List[str]]:
    score, rows, violations = compare(query, product)
    if violations:
        return None, score, rows, violations
    if rows and all(r.status == "MATCH" for r in rows):
        return EXACT, 100.0, rows, []
    if score < settings.MIN_ALTERNATIVE_SCORE:
        return None, score, rows, []
    if settings.REQUIRE_DIMENSIONS_WITHIN_SCALE and not within_deviation_scale(rows):
        return None, score, rows, []
    # Agreeing on mandatory attributes alone does not make a product a related alternative.
    flexible = [r for r in rows if not r.is_hard]
    flexible_weight = sum(r.weight for r in flexible)
    if not flexible or flexible_weight <= 0:
        return None, score, rows, []
    if sum(r.weight * r.score for r in flexible) / flexible_weight < settings.MIN_FLEXIBLE_AGREEMENT:
        return None, score, rows, []
    return ALTERNATIVE, score, rows, []


def _images_for(part_number: str, match_class: str, images: Dict[str, List[Dict[str, Any]]]) -> List[ImageInfo]:
    out: List[ImageInfo] = []
    seen = set()
    for img in images.get(part_number, []):
        if img["image_hash"] in seen:  # the same picture stored by two documents is shown once
            continue
        seen.add(img["image_hash"])
        out.append(ImageInfo(
            image_id=img["image_id"], document_id=img["document_id"], source_pdf=img["filename"],
            page_number=img["page_number"], image_url=f"/api/images/{img['image_id']}",
            image_type=img["image_type"], association_status=img["association_status"],
            association_basis=img["association_basis"],
            description=f"{img['image_type'].capitalize()} from {img['filename']}, page {img['page_number']}",
            label="Alternative" if match_class == ALTERNATIVE else None,
        ))
    return out


def _build_match(query: ParsedQuery, entry: Dict[str, Any], images: Dict[str, List[Dict[str, Any]]]) -> ProductMatch:
    p, rows, match_class, score = entry["product"], entry["rows"], entry["match_class"], entry["score"]
    record = dict(p, source_pdf=p["doc_filename"])
    explanation, source = explain(match_class, record, rows, query, score)
    if entry["disagreeing_sources"]:
        explanation += (
            " Note: " + ", ".join(entry["disagreeing_sources"]) + " lists different values for this part number; "
            "the values shown are from the source named above."
        )
    gallery = _images_for(p["part_number"], match_class, images)
    return ProductMatch(
        id=p["id"], document_id=p["document_id"], source_pdf=p["doc_filename"],
        **{f: p.get(f) for f in PRODUCT_FIELDS},
        extra_attributes=p.get("extra_attributes") or {}, original_values=p.get("raw_attributes") or {},
        sources=[SourceReference(
            document_id=s["document_id"], source_pdf=s["doc_filename"], source_page=s["source_page"],
            source_table=s.get("source_table"), validation_status=s["validation_status"], record_id=s["id"],
        ) for s in entry["sources"]],
        match_class=match_class, score=score, attribute_comparisons=rows,
        matching_attributes=[f"{r.label}: {r.product_value}" for r in rows if r.status == "MATCH"],
        differing_attributes=[r.difference_description or r.label for r in rows if r.status == "DIFFERS"],
        missing_attributes=[r.difference_description or r.label for r in rows if r.status == "UNKNOWN"],
        explanation=explanation, explanation_source=source, images=gallery,
        image_note=None if gallery else "No verified image is associated with this product in the indexed documents.",
    )


def _part_number_lookup(query: ParsedQuery, raw: str, started: float) -> SearchResponse:
    records = catalogue.find_by_part_number(query.part_number)
    if not records:
        return _response(
            query, raw, started, outcome="no_match",
            message=f"Part number {query.part_number} is not in the indexed catalogues.",
            diagnostics={"reason": "part_number_not_found"},
        )
    probe = query.model_copy(update={"hard_constraints": []})
    grouped: Dict[str, Dict[str, Any]] = {}
    for p in records:
        _, rows, _ = compare(probe, p)
        rows.insert(0, AttributeComparison(
            attribute_name="part_number", label="Part number", requested_value=query.part_number,
            product_value=p["part_number"] if p["part_number"].upper() == query.part_number.upper()
            else f"{p['part_number']} (also listed as {query.part_number})",
            status="MATCH", is_hard=True, weight=0.0, score=1.0,
        ))
        entry = grouped.setdefault(p["part_number"], {
            "product": p, "rows": rows, "match_class": EXACT, "score": 100.0, "sources": [], "disagreeing_sources": [],
        })
        entry["sources"].append(p)
        if p["validation_status"] == "validated" and entry["product"]["validation_status"] != "validated":
            entry.update(product=p, rows=rows)
    images = catalogue.verified_images(list(grouped))
    results = [_build_match(query, e, images) for _, e in sorted(grouped.items())]
    differing = [r.label for r in results[0].attribute_comparisons if r.status == "DIFFERS"]
    message = f"Part number {query.part_number} found in the catalogue."
    if differing:
        message += " Note: the record differs from other attributes in your request (" + ", ".join(differing) + ")."
    return _response(
        query, raw, started, result_class=EXACT, outcome="exact", message=message, total_found=len(results),
        results=results, diagnostics={"lookup": "part_number", "records_evaluated": len(records)},
    )


def _semantic_order(query: ParsedQuery, raw: str, use_semantic: bool) -> Dict[str, float]:
    """Embedding similarity, used only to order otherwise equal results when the request has free wording."""
    if not use_semantic or not settings.EMBEDDINGS_ENABLED:
        return {}
    if not (query.descriptor_terms or any(t.isalpha() for t in query.unparsed_terms)):
        return {}
    from backend.app.llm.embeddings import semantic_search
    return dict(semantic_search(raw))


def execute_deterministic_search(query: ParsedQuery, raw_query_text: Optional[str] = None,
                                 use_semantic: bool = True) -> SearchResponse:
    started = time.perf_counter()
    raw = raw_query_text if raw_query_text is not None else query.original_query

    relevant, reason = check_relevance(raw, query)
    if not relevant:
        return _response(query, raw, started, outcome="irrelevant", message=reason,
                         diagnostics={"reason": "outside_catalogue_scope"})
    conflicting, description = check_conflicting_constraints(query, raw)
    if conflicting:
        return _response(
            query, raw, started, outcome="conflict", message=description,
            clarification={"type": "CONFLICTING_CONSTRAINTS", "question": description, "options": query.suggested_options},
        )
    if query.clarification_needed:
        return _response(
            query, raw, started, outcome="clarification", message=query.clarification_question,
            clarification={"type": query.clarification_type, "question": query.clarification_question,
                           "options": query.suggested_options},
        )

    products = catalogue.active_products()
    if not products:
        return _response(query, raw, started, outcome="no_match",
                         message="No catalogue is indexed yet. Upload a PDF catalogue on the Documents page.",
                         diagnostics={"reason": "empty_catalogue"})
    if query.part_number:
        return _part_number_lookup(query, raw, started)

    by_part: Dict[str, List[Dict[str, Any]]] = {}
    hard_failures: Dict[str, int] = {}
    unverifiable = 0
    for p in products:
        match_class, score, rows, violations = _classify(query, p)
        for row in rows:
            if row.is_hard and row.status != "MATCH":
                hard_failures[row.label] = hard_failures.get(row.label, 0) + 1
        if match_class is None:
            # Nothing contradicts the request, most of it is verified, but a requested attribute is not stated.
            total = sum(r.weight for r in rows)
            verified = sum(r.weight for r in rows if r.status == "MATCH")
            if (rows and all(r.status in ("MATCH", "UNKNOWN") for r in rows) and total > 0
                    and 100.0 * verified / total >= settings.MIN_ALTERNATIVE_SCORE):
                unverifiable += 1
            continue
        by_part.setdefault(p["part_number"], []).append(
            {"product": p, "rows": rows, "match_class": match_class, "score": score})

    # One result per part number: the best-supported source record represents it.
    entries: List[Dict[str, Any]] = []
    all_by_part: Dict[str, List[Dict[str, Any]]] = {}
    for p in products:
        if p["part_number"] in by_part:
            all_by_part.setdefault(p["part_number"], []).append(p)
    for part_number, candidates in by_part.items():
        candidates.sort(key=lambda c: (c["match_class"] != EXACT, c["product"]["validation_status"] != "validated",
                                       -c["score"], c["product"]["doc_filename"]))
        best = candidates[0]
        eligible_ids = {c["product"]["id"] for c in candidates if c["match_class"] == best["match_class"]}
        best["sources"] = all_by_part[part_number]
        best["disagreeing_sources"] = sorted({
            s["doc_filename"] for s in all_by_part[part_number] if s["id"] not in eligible_ids})
        entries.append(best)

    similarity = _semantic_order(query, raw, use_semantic) if entries else {}

    def unknowns(e: Dict[str, Any]) -> int:
        return sum(1 for r in e["rows"] if r.status == "UNKNOWN")

    def needs_review(e: Dict[str, Any]) -> bool:
        return e["product"]["validation_status"] != "validated"

    exact = [e for e in entries if e["match_class"] == EXACT]
    if exact:
        prefer_straight = query.stylus_type is None
        exact.sort(key=lambda e: (
            needs_review(e),
            prefer_straight and (e["product"].get("stylus_type") or "straight") != "straight",
            -similarity.get(e["product"]["id"], 0.0), e["product"]["part_number"],
        ))
        chosen, result_class, outcome = exact, EXACT, "exact"
        message = (f"{len(exact)} catalogue product{'s' if len(exact) != 1 else ''} match"
                   f"{'es' if len(exact) == 1 else ''} every requested attribute.")
    else:
        alternatives = [e for e in entries if e["match_class"] == ALTERNATIVE]
        alternatives.sort(key=lambda e: (
            -e["score"], needs_review(e), unknowns(e), -similarity.get(e["product"]["id"], 0.0),
            e["product"]["part_number"],
        ))
        chosen, result_class, outcome = alternatives, (ALTERNATIVE if alternatives else NO_MATCH), "alternative"
        message = ("No catalogue product matches every requested attribute. These are the closest products that "
                   "satisfy all mandatory requirements; each one differs from the request as shown.")

    diagnostics: Dict[str, Any] = {
        "records_evaluated": len(products), "eligible_products": len(chosen),
        "hard_constraints": list(query.hard_constraints), "hard_constraint_failures": hard_failures,
        "minimum_alternative_score": settings.MIN_ALTERNATIVE_SCORE,
        "semantic_tie_break_used": bool(similarity),
    }
    if not chosen:
        known_threads = catalogue.available_threads()
        if query.thread and "thread" in query.hard_constraints and query.thread not in known_threads:
            outcome = "no_match"
            message = (f"No suitable product was found: no indexed product has an {query.thread} thread "
                       f"(threads in the catalogues: {', '.join(known_threads)}).")
        elif unverifiable:
            outcome = "insufficient_evidence"
            one = unverifiable == 1
            message = (f"{unverifiable} catalogue record{'' if one else 's'} agree{'s' if one else ''} with the "
                       f"request as far as the catalogue states, but {'does' if one else 'do'} not state every "
                       "requested attribute, so no match can be verified. No product is recommended.")
        else:
            outcome = "no_match"
            blocking = max(hard_failures, key=hard_failures.get) if hard_failures else None
            message = "No suitable product was found in the indexed catalogues."
            if blocking and hard_failures[blocking] == len(products):
                message += f" No indexed product satisfies the mandatory requirement '{blocking}'."
            elif query.hard_constraints:
                wanted = ", ".join(f"{a.name.replace('_mm', '').replace('_', ' ')} {a.value}"
                                   for a in query.requested_attributes if a.name in query.hard_constraints)
                message += (f" No indexed product satisfies the mandatory requirements together ({wanted}) "
                            "closely enough to be offered as a related alternative.")
        return _response(query, raw, started, outcome=outcome, message=message, diagnostics=diagnostics)

    shown = chosen[:settings.MAX_RESULTS]
    images = catalogue.verified_images([e["product"]["part_number"] for e in shown])
    results = [_build_match(query, e, images) for e in shown]
    if len(chosen) > len(shown):
        message += f" Showing the first {len(shown)} of {len(chosen)}; add attributes to narrow the search."
    return _response(query, raw, started, result_class=result_class, outcome=outcome, message=message,
                     total_found=len(chosen), results=results, diagnostics=diagnostics)
