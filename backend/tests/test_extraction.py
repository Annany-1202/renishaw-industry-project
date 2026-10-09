"""Extraction regression tests against values read directly from the supplied PDFs.

The expected values below were copied from the part-number listings printed in
the catalogues (H-1000-3200 pp. 106-119, H-1000-3036 pp. 69-87), not from the
extractor's output.
"""
import json

import pytest

from backend.app.core.config import settings
from backend.app.db.database import db
from backend.app.ingestion.normalizer import (
    inches_to_mm, normalize_material, normalize_thread, parse_number,
)
from backend.tests.conftest import H1000, ZEISS

# (document, part number, expected field values, printed listing page)
GROUND_TRUTH = [
    (H1000, "A-5000-3603", dict(category="stylus", thread="M2", ball_diameter_mm=2.0, ball_material="Ruby",
                                overall_length_mm=20.0, stem_material="Stainless steel",
                                effective_working_length_mm=14.0, weight_g=0.4), 106),
    (H1000, "A-5003-3822", dict(category="stylus", thread="M2", ball_diameter_mm=2.0, ball_material="Ruby",
                                overall_length_mm=20.0, stem_material="Tungsten carbide",
                                effective_working_length_mm=14.0, weight_g=0.48), 109),
    (H1000, "A-5000-3709", dict(category="stylus", thread="M4", ball_diameter_mm=6.0, ball_material="Ruby",
                                overall_length_mm=50.0, stem_material="Ceramic",
                                effective_working_length_mm=38.5, weight_g=4.8), 107),
    (H1000, "A-5000-3626", dict(category="stylus", stylus_type="star", thread="M2", ball_diameter_mm=2.0,
                                overall_length_mm=19.2, stem_material="Stainless steel"), 107),
    (H1000, "A-5003-0075", dict(category="extension", thread="M3", ball_diameter_mm=None, ball_material=None,
                                overall_length_mm=50.0, stem_material="Ceramic", weight_g=2.95), 109),
    (H1000, "A-5003-5278", dict(category="knuckle", thread="M5", ball_diameter_mm=None, ball_material=None,
                                overall_length_mm=36.5, stem_material="Stainless steel", weight_g=16.5), 111),
    (ZEISS, "A-5555-3790", dict(category="stylus", thread="M5", ball_diameter_mm=5.0, overall_length_mm=30.0,
                                source_page=10), 84),
    (ZEISS, "A-5555-1065", dict(category="stylus", ball_diameter_mm=5.0, overall_length_mm=100.0,
                                alt_part_number="626105-0511-100", source_page=13), 79),
    (ZEISS, "A-5003-3822", dict(category="stylus", ball_diameter_mm=2.0, overall_length_mm=21.0,
                                alt_part_number="602030-8005-000", source_page=61), 69),
    (ZEISS, "A-5004-0002", dict(category="extension", ball_diameter_mm=None, ball_material=None,
                                overall_length_mm=50.0, source_page=48), 69),
    (ZEISS, "A-5555-0218", dict(category="knuckle", ball_diameter_mm=None, overall_length_mm=30.0,
                                source_page=27), 76),
    (ZEISS, "A-5004-7592", dict(category="adaptor", thread="M3", overall_length_mm=5.0, source_page=59), 71),
]


def _product(doc_id, part_number):
    with db() as conn:
        row = conn.execute("SELECT * FROM products WHERE document_id = ? AND part_number = ?",
                           (doc_id, part_number)).fetchone()
    return dict(row) if row else None


@pytest.mark.parametrize("doc_id,part_number,expected,listing_page", GROUND_TRUTH,
                         ids=[f"{d}:{p}" for d, p, _, _ in GROUND_TRUTH])
def test_record_matches_printed_catalogue(catalogue_reports, doc_id, part_number, expected, listing_page):
    product = _product(doc_id, part_number)
    assert product is not None, f"{part_number} was not extracted from {doc_id}"
    for field, value in expected.items():
        assert product[field] == value, f"{part_number}.{field}: extracted {product[field]!r}, catalogue prints {value!r}"


def test_extraction_counts(catalogue_reports):
    with db() as conn:
        counts = dict(conn.execute("SELECT document_id, count(*) FROM products GROUP BY document_id").fetchall())
    # Regression guard: the listings print 655 (ZEISS) and 738 (H-1000-3200) part rows.
    assert counts[ZEISS] >= 650
    assert counts[H1000] >= 738
    for doc_id in (ZEISS, H1000):
        report = catalogue_reports[doc_id]
        assert report["rows_rejected"] == 0
        assert report["exceptions"] == []
        assert report["products_extracted"] == counts[doc_id]


def test_adaptor_lists_both_threads(catalogue_reports):
    product = _product(ZEISS, "A-5004-7592")
    assert json.loads(product["extra_attributes"])["threads"] == ["M3", "M2"]


def test_nothing_is_defaulted(catalogue_reports):
    """Tip-less components must not carry an invented ball; the old pipeline forced Ruby/M5 on everything."""
    with db() as conn:
        with_ball = conn.execute(
            "SELECT count(*) FROM products WHERE category IN ('extension','knuckle','adaptor','cube') "
            "AND ball_material IS NOT NULL").fetchone()[0]
        threads = {r[0] for r in conn.execute("SELECT DISTINCT thread FROM products WHERE document_id = ?", (ZEISS,))}
        zeiss_materials = {r[0] for r in conn.execute(
            "SELECT DISTINCT ball_material FROM products WHERE document_id = ? AND category = 'stylus'", (ZEISS,))}
    assert with_ball == 0
    assert {"M2", "M3", "M5"} <= threads
    assert {"Ruby", "Silicon nitride"} <= zeiss_materials


def test_provenance_and_keys(catalogue_reports):
    with db() as conn:
        pages = dict(conn.execute("SELECT id, page_count FROM documents").fetchall())
        rows = conn.execute("SELECT id, document_id, part_number, source_page, source_pdf, validation_status, "
                            "review_reason FROM products").fetchall()
        duplicates = conn.execute("SELECT count(*) FROM (SELECT 1 FROM products GROUP BY document_id, part_number "
                                  "HAVING count(*) > 1)").fetchone()[0]
        filenames = dict(conn.execute("SELECT id, filename FROM documents").fetchall())
    assert duplicates == 0
    assert pages == {ZEISS: 88, H1000: 120}
    for row in rows:
        assert row["id"] == f"{row['document_id']}:{row['part_number']}"
        assert 1 <= row["source_page"] <= pages[row["document_id"]]
        assert row["source_pdf"] == filenames[row["document_id"]]
        if row["validation_status"] == "needs_review":
            assert row["review_reason"], f"{row['part_number']} is flagged without a reason"


def test_same_part_number_kept_per_source(catalogue_reports):
    """A part listed in both catalogues is stored once per document (the old INSERT OR REPLACE lost rows)."""
    with db() as conn:
        shared = conn.execute("SELECT count(*) FROM (SELECT part_number FROM products GROUP BY part_number "
                              "HAVING count(DISTINCT document_id) = 2)").fetchone()[0]
    assert shared >= 50
    assert _product(ZEISS, "A-5003-3822") and _product(H1000, "A-5003-3822")


def test_reports_written(catalogue_reports):
    for doc_id in (ZEISS, H1000):
        report = json.loads((settings.REPORT_DIR / f"{doc_id}_ingestion_report.json").read_text(encoding="utf-8"))
        assert report["products_extracted"] > 0
        assert (settings.REPORT_DIR / f"{doc_id}_image_associations.csv").stat().st_size > 100
        assert (settings.REPORT_DIR / f"{doc_id}_review_rows.csv").exists()


def test_normalisation_helpers():
    assert parse_number("2.0 (0.08)") == 2.0
    assert parse_number("-") is None and parse_number("") is None
    assert inches_to_mm(1) == 25.4
    assert normalize_thread("m5") == "M5" and normalize_thread("thread M2") == "M2"
    assert normalize_thread("ruby") is None
    assert normalize_material("TC") == "Tungsten carbide"
    assert normalize_material("stainless steel") == "Stainless steel"
    assert normalize_material("-") is None
