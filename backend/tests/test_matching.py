"""Scoring, hard constraints and classification on hand-built records (no catalogue needed)."""
import pytest

from backend.app.core.config import settings
from backend.app.matching.engine import ALTERNATIVE, EXACT, _classify
from backend.app.matching.explainer import generate_grounded_explanation, validate_explanation
from backend.app.matching.hard_constraints import evaluate_hard_constraints
from backend.app.matching.schemas import ParsedQuery
from backend.app.matching.scoring import compare, numeric_equal


def product(**overrides):
    base = dict(
        id="doc_x:A-0000-0001", document_id="doc_x", part_number="A-0000-0001", category="stylus",
        stylus_type="straight", thread="M2", ball_material="Ruby", ball_diameter_mm=2.0,
        stem_material="Tungsten carbide", stem_diameter_mm=1.0, overall_length_mm=20.0,
        effective_working_length_mm=14.0, extra_attributes={}, _tokens={"ball", "stylus"},
        validation_status="validated", source_pdf="x.pdf", source_page=1,
    )
    base.update(overrides)
    return base


def query(**fields):
    fields.setdefault("hard_constraints", [f for f in ("thread", "category") if f in fields])
    return ParsedQuery(original_query="test", **fields)


FULL = dict(category="stylus", thread="M2", ball_material="Ruby", ball_diameter_mm=2.0,
            stem_material="Tungsten carbide", overall_length_mm=20.0)


def test_exact_match_scores_100_and_all_rows_match():
    match_class, score, rows, violations = _classify(query(**FULL), product())
    assert (match_class, score, violations) == (EXACT, 100.0, [])
    assert {r.status for r in rows} == {"MATCH"}


def test_score_formula_matches_specification_weights():
    # Only the overall length differs, by 2 mm of a 5 mm deviation scale -> s = 0.6
    score, rows, _ = compare(query(**FULL), product(overall_length_mm=22.0))
    w = settings.WEIGHTS
    total = w.thread + w.category + w.ball_diameter + w.overall_length + w.stem_material + w.ball_material
    expected = 100 * (total - w.overall_length * 0.4) / total
    assert score == pytest.approx(expected, abs=0.01)
    length = next(r for r in rows if r.attribute_name == "overall_length_mm")
    assert length.status == "DIFFERS" and length.score == pytest.approx(0.6)
    assert "2 mm more" in length.difference_description


def test_wrong_thread_is_never_recommended_whatever_the_score():
    q = query(**FULL)
    match_class, score, _, violations = _classify(q, product(thread="M3"))
    assert match_class is None and violations
    ok, why = evaluate_hard_constraints(q, product(thread="M3"))
    assert not ok and "Thread" in why[0]


def test_unknown_is_not_a_match():
    """A record that does not state the thread cannot satisfy a thread requirement."""
    match_class, _, rows, violations = _classify(query(**FULL), product(thread=None))
    assert match_class is None and violations
    assert next(r for r in rows if r.attribute_name == "thread").status == "UNKNOWN"
    # A non-mandatory attribute that is not stated: not exact, shown as unknown, scored 0 for that attribute.
    match_class, score, rows, _ = _classify(query(**FULL), product(stem_material=None))
    assert match_class == ALTERNATIVE and score < 100
    assert next(r for r in rows if r.attribute_name == "stem_material").status == "UNKNOWN"


def test_explicit_hard_constraint_on_a_dimension():
    q = query(**FULL, hard_constraints=["thread", "category", "overall_length_mm"])
    assert _classify(q, product(overall_length_mm=21.0))[0] is None
    assert _classify(q, product())[0] == EXACT


def test_material_mismatch_is_an_alternative_not_exact():
    match_class, score, rows, _ = _classify(query(**FULL), product(ball_material="Zirconia"))
    assert match_class == ALTERNATIVE and score < 100
    assert "Zirconia, not Ruby" in next(r for r in rows if r.attribute_name == "ball_material").difference_description


def test_dimension_beyond_deviation_scale_is_not_an_alternative():
    assert _classify(query(**FULL), product(overall_length_mm=80.0))[0] is None
    assert _classify(query(**FULL), product(ball_diameter_mm=6.0))[0] is None


def test_low_score_is_not_an_alternative():
    q = query(category="stylus", thread="M2", ball_material="Zirconia", stem_material="Ceramic",
              ball_diameter_mm=2.4, overall_length_mm=24.0)
    match_class, score, _, _ = _classify(q, product())
    assert score < settings.MIN_ALTERNATIVE_SCORE and match_class is None


def test_mandatory_attributes_alone_do_not_make_an_alternative():
    q = query(category="stylus", thread="M2", ball_material="Zirconia", hard_constraints=["thread", "category"])
    assert _classify(q, product())[0] is None  # agrees on thread and type only: not a related alternative


def test_weak_agreement_on_optional_attributes_is_not_an_alternative():
    """Found by the evaluation: a 35 mm steel disc was offered for a '45 mm ruby ball' request."""
    q = query(category="stylus", thread="M3", ball_material="Ruby", ball_diameter_mm=45.0)
    disc = product(thread="M3", stylus_type="disc", ball_material="Silver steel", ball_diameter_mm=35.0)
    assert _classify(q, disc)[0] is None


def test_category_mismatch_is_a_violation_when_requested():
    assert _classify(query(category="extension", thread="M2"), product())[0] is None


def test_adaptor_needs_both_threads():
    q = query(category="adaptor", thread="M3", secondary_thread="M2",
              hard_constraints=["thread", "secondary_thread", "category"])
    both = product(category="adaptor", thread="M3", extra_attributes={"threads": ["M3", "M2"]})
    one = product(category="adaptor", thread="M3")
    assert _classify(q, both)[0] == EXACT
    assert _classify(q, one)[0] is None


@pytest.mark.parametrize("inches,decimals,catalogue_mm,expected", [
    (0.08, 2, 2.0, True),      # the catalogue itself prints 2.0 (0.08)
    (0.08, 2, 2.5, False),
    (0.12, 2, 3.0, True),
    (0.2, 1, 5.0, True),
    (0.2, 1, 4.0, False),      # 0.16 in rounds to 0.2 but is 21% away: must not match
    (0.25, 2, 6.35, True),
    (1.0, 0, 25.0, True),
    (1.0, 0, 30.0, False),
])
def test_inch_input_precision_rule(inches, decimals, catalogue_mm, expected):
    equal, note = numeric_equal(round(inches * 25.4, 4), catalogue_mm, {"inches": inches, "decimals": decimals})
    assert equal is expected
    if expected and abs(inches * 25.4 - catalogue_mm) > 1e-3:
        assert "precision you typed" in note


def test_millimetre_input_must_agree_exactly():
    assert numeric_equal(2.0, 2.0, None)[0]
    assert not numeric_equal(2.0, 2.03, None)[0]


def test_ranking_is_reproducible_and_ordered():
    q = query(**FULL)
    candidates = [product(part_number=f"A-0000-{i:04d}", overall_length_mm=20.0 + i) for i in range(1, 5)]
    first = [(_classify(q, p)[1], p["part_number"]) for p in candidates]
    for _ in range(20):
        assert [(_classify(q, p)[1], p["part_number"]) for p in candidates] == first
    scores = [s for s, _ in first]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) == len(scores)


def test_explanation_is_grounded_and_makes_no_suitability_claim():
    q = query(**FULL)
    p = product(overall_length_mm=22.0)
    _, score, rows, _ = _classify(q, p)
    text = generate_grounded_explanation("ALTERNATIVE", p["part_number"], rows, "x.pdf", 1, score=score)
    assert "not an exact match" in text and "x.pdf, page 1" in text and "22 mm" in text
    assert "not a measure of suitability" in text
    for word in ("safe", "guaranteed", "recommended for"):
        assert word not in text.lower()


def test_explanation_validator_rejects_invented_facts():
    q, p = query(**FULL), product()
    assert validate_explanation("A-0000-0001 has a 2 mm Ruby ball and M2 thread.", p, q)[0]
    assert not validate_explanation("A-9999-9999 has a 2 mm Ruby ball.", p, q)[0]
    assert not validate_explanation("A-0000-0001 has a 3.5 mm Ruby ball.", p, q)[0]
    assert not validate_explanation("A-0000-0001 has a Zirconia ball.", p, q)[0]
    assert not validate_explanation("A-0000-0001 is guaranteed safe for your machine.", p, q)[0]
