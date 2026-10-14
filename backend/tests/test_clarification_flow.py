"""Iterative clarification of vague catalogue requests, narrowing follow-ups, and out-of-scope answers.

Parser-level tests need no catalogue. The API tests upload a synthetic catalogue with an
M9 thread (used by no supplied catalogue) and remove it afterwards.
"""
import pytest

from backend.app.core.config import settings
from backend.app.evaluation.sample_pdf import make_catalogue_pdf
from backend.app.llm.query_interpreter import (
    MAX_CLARIFICATION_ROUNDS, interpret_query, refine_query, rule_based_query_parser,
)
from backend.app.matching import domain
from backend.app.matching.relevance_gate import NOT_RELATED
from backend.tests.conftest import wait_for_status

# --- vague but catalogue-related requests are clarified step by step ---------------------------

@pytest.mark.parametrize("text", [
    "I need something for my CMM", "what do you have for my renishaw probe", "show me the catalogue",
    "parts for a touch-trigger probe",
])
def test_vague_domain_request_asks_for_the_product_type(text):
    q = interpret_query(text)
    assert not q.is_irrelevant
    assert q.clarification_needed and q.clarification_type == "MISSING_PRODUCT_TYPE"
    assert q.suggested_options


@pytest.mark.parametrize("category,label", list(domain.CATEGORY_OPTION_LABELS.items()))
def test_every_product_type_option_reads_back_as_its_category(category, label):
    assert rule_based_query_parser(label, vocabulary=set()).category == category


def test_answers_are_applied_one_question_at_a_time():
    first = interpret_query("I need something for my CMM")
    second = refine_query(first.model_dump(), "Stylus")
    assert second.category == "stylus" and "category" in second.hard_constraints
    assert second.clarification_type == "MISSING_INTERFACE" and "the stylus" in second.clarification_question
    assert second.clarification_history == ["MISSING_PRODUCT_TYPE"]
    third = refine_query(second.model_dump(), "M3")
    assert not third.clarification_needed
    assert third.thread == "M3" and {"thread", "category"} <= set(third.hard_constraints)
    assert third.original_query == "I need something for my CMM"
    assert third.clarification_history == ["MISSING_PRODUCT_TYPE", "MISSING_INTERFACE"]


def test_unhelpful_answers_never_repeat_a_question_and_the_dialogue_ends():
    q = interpret_query("something for my probe")
    asked = []
    for _ in range(MAX_CLARIFICATION_ROUNDS + 2):
        if not q.clarification_needed:
            break
        assert q.clarification_type not in asked, "a question was asked twice"
        asked.append(q.clarification_type)
        q = refine_query(q.model_dump(), "not sure")
    assert not q.clarification_needed
    assert asked == ["MISSING_PRODUCT_TYPE", "MISSING_INTERFACE", "INSUFFICIENT_DETAILS"]


def test_specific_requests_are_not_questioned():
    assert not interpret_query("M2 stylus 2 mm ruby ball 20 mm long").clarification_needed
    assert not interpret_query("A-5000-3603").clarification_needed


def test_existing_questions_are_unchanged():
    assert interpret_query("stylus for my probe").clarification_type == "MISSING_INTERFACE"
    assert interpret_query("long thin stylus").clarification_type == "QUALITATIVE_TERMS"


def test_accessory_noun_does_not_override_a_stylus_request():
    assert rule_based_query_parser("probe accessories", vocabulary=set()).category == "accessory"
    assert rule_based_query_parser("renishaw styli and accessories", vocabulary=set()).category == "stylus"


# --- unrelated requests --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "what is the weather today", "hello", "tell me a joke", "gaming laptop with 2 mm ruby ball and M5 thread",
    "book me a flight to Mumbai", "asdf qwer zxcv",
])
def test_unrelated_requests_are_irrelevant_not_clarified(text):
    q = interpret_query(text)
    assert q.is_irrelevant and not q.clarification_needed


# --- API: follow-ups grounded in the catalogue, out-of-scope message ----------------------------

ROWS = [("T-9200-%04d" % (i + 1), "Narrowing stylus", "M9", "Ruby", str(ball), "Ceramic", str(length))
        for i, (ball, length) in enumerate([(1, 20), (1, 30), (2, 20), (2, 30), (2, 40), (3, 20), (3, 30), (4, 50)])]


@pytest.fixture(scope="module")
def narrowing_catalogue(bare_client, tmp_path_factory):
    assert len(ROWS) > settings.MAX_RESULTS
    path = make_catalogue_pdf(tmp_path_factory.mktemp("narrow") / "narrow.pdf", ROWS, title="Narrowing catalogue")
    with open(path, "rb") as fh:
        response = bare_client.post("/api/documents", files={"file": ("narrow.pdf", fh, "application/pdf")})
    assert response.status_code == 202, response.text
    doc = wait_for_status(bare_client, response.json()["id"])
    assert doc["status"] == "Ready", doc
    yield doc
    bare_client.delete(f"/api/documents/{doc['id']}")


def _search(client, query, **extra):
    r = client.post("/api/search", json={"query": query, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_broad_results_come_with_a_narrowing_question_from_catalogue_values(bare_client, narrowing_catalogue):
    r = _search(bare_client, "M9 stylus")
    assert r["outcome"] == "exact" and r["total_found"] == len(ROWS) and len(r["results"]) == settings.MAX_RESULTS
    assert r["clarification"] is None, "results are shown; the follow-up does not block them"
    follow = r["follow_up"]
    assert follow["type"] == "NARROW_RESULTS" and follow["attribute"] == "ball_diameter_mm"
    assert follow["options"] == ["1 mm ball", "2 mm ball", "3 mm ball", "4 mm ball"]
    assert follow["option_counts"] == [2, 3, 2, 1]
    assert "NARROW:ball_diameter_mm" in r["interpreted_query"]["clarification_history"]


def test_answering_the_follow_up_refines_the_same_search_and_keeps_hard_constraints(bare_client, narrowing_catalogue):
    first = _search(bare_client, "M9 stylus")
    second = _search(bare_client, "M9 stylus", clarification_answer="2 mm ball",
                     previous_query=first["interpreted_query"])
    assert second["outcome"] == "exact" and second["total_found"] == 3
    assert second["interpreted_query"]["original_query"] == "M9 stylus"
    assert "thread" in second["interpreted_query"]["hard_constraints"]
    for hit in second["results"]:
        assert (hit["thread"], hit["ball_diameter_mm"]) == ("M9", 2.0)
        assert hit["source_pdf"] == "narrow.pdf" and hit["source_page"] == 1 and hit["sources"]
    assert second["follow_up"] is None, "three results fit on one page; nothing left to narrow"


def test_no_follow_up_when_every_result_is_shown(bare_client, narrowing_catalogue):
    r = _search(bare_client, "M9 stylus 4 mm ruby ball 50 mm long")
    assert r["outcome"] == "exact" and r["follow_up"] is None


def test_unrelated_request_says_it_is_not_related_to_the_catalogues(bare_client, narrowing_catalogue):
    for text in ("what is the weather today", "recommend me a good espresso machine"):
        r = _search(bare_client, text)
        assert r["outcome"] == "irrelevant" and r["results"] == [] and r["follow_up"] is None
        assert r["message"].startswith(NOT_RELATED)
        assert "narrow.pdf" in r["message"], "the message names the indexed catalogues"


def test_exhausted_dialogue_without_details_says_so(bare_client, narrowing_catalogue):
    r = _search(bare_client, "something for my probe")
    for _ in range(MAX_CLARIFICATION_ROUNDS):
        if r["outcome"] != "clarification":
            break
        r = _search(bare_client, "something for my probe", clarification_answer="not sure",
                    previous_query=r["interpreted_query"])
    assert r["outcome"] == "no_match" and r["results"] == []
    assert r["diagnostics"]["reason"] == "insufficient_details"
