"""Image extraction, association and presentation (FR-13 to FR-17)."""
import pymupdf

from backend.app.core.config import settings
from backend.app.db.database import db
from backend.tests.conftest import H1000, ZEISS


def test_images_extracted_from_both_catalogues_with_provenance(catalogue_reports):
    with db() as conn:
        pages = dict(conn.execute("SELECT id, page_count FROM documents").fetchall())
        images = [dict(r) for r in conn.execute("SELECT * FROM images")]
    by_doc = {d: [i for i in images if i["document_id"] == d] for d in (ZEISS, H1000)}
    assert len(by_doc[ZEISS]) >= 100 and len(by_doc[H1000]) >= 400
    assert len({i["image_id"] for i in images}) == len(images)
    for image in images:
        assert 1 <= image["page_number"] <= pages[image["document_id"]]
        assert image["image_path"].startswith(image["document_id"] + "/")
        path = settings.IMAGE_DIR / image["image_path"]
        assert path.is_file() and path.stat().st_size > 200
        assert len(image["image_hash"]) == 64 and image["extraction_metadata"]


def test_image_files_are_real_non_blank_pictures(catalogue_reports):
    with db() as conn:
        sample = [r["image_path"] for r in conn.execute("SELECT image_path FROM images ORDER BY image_id LIMIT 60")]
    for rel in sample:
        pix = pymupdf.Pixmap(str(settings.IMAGE_DIR / rel))
        assert pix.width >= 30 and pix.height >= 30
        assert not pix.is_unicolor, f"{rel} is a blank crop"


def test_every_association_records_its_basis_and_owner(catalogue_reports):
    with db() as conn:
        links = conn.execute(
            "SELECT l.*, i.document_id AS image_doc, i.page_number, p.document_id AS product_doc, p.part_number AS pn "
            "FROM product_images l JOIN images i ON i.image_id = l.image_id JOIN products p ON p.id = l.product_id"
        ).fetchall()
    assert len(links) > 1200
    for link in links:
        assert link["association_basis"], "an association must say why it was made"
        assert link["document_id"] == link["image_doc"] == link["product_doc"], "links never cross documents"
        assert link["part_number"] == link["pn"]


def test_report_reconciles_image_coverage(catalogue_reports):
    """No claim of complete coverage: products without a verified image are counted in the report."""
    with db() as conn:
        for doc_id in (ZEISS, H1000):
            without = conn.execute(
                "SELECT count(*) FROM products p WHERE p.document_id = ? AND NOT EXISTS (SELECT 1 FROM product_images l "
                "WHERE l.product_id = p.id AND l.association_status = 'verified')", (doc_id,)).fetchone()[0]
            assert catalogue_reports[doc_id]["products_without_image"] == without


def test_h1000_illustration_is_under_the_parts_own_table_column(catalogue_reports):
    with db() as conn:
        rows = conn.execute(
            "SELECT i.page_number, p.source_page, l.association_basis FROM product_images l "
            "JOIN images i ON i.image_id = l.image_id JOIN products p ON p.id = l.product_id "
            "WHERE l.part_number = 'A-5000-3603' AND l.document_id = ?", (H1000,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["page_number"] == rows[0]["source_page"] == 20
    assert "column" in rows[0]["association_basis"]


def test_exact_match_shows_all_verified_images_from_every_source(search):
    hit = search("A-5003-3822")["results"][0]
    with db() as conn:
        expected = {r[0] for r in conn.execute(
            "SELECT image_id FROM product_images WHERE part_number = 'A-5003-3822' AND association_status = 'verified'")}
    assert {i["image_id"] for i in hit["images"]} == expected and len(expected) == 2
    assert {i["document_id"] for i in hit["images"]} == {ZEISS, H1000}
    for image in hit["images"]:
        assert image["association_status"] == "verified" and image["label"] is None
        assert image["source_pdf"].endswith(".pdf") and image["page_number"] > 0 and image["image_type"]


def test_image_source_is_the_images_own_document(search):
    """The old code captioned every image with the product's document."""
    hit = search("A-5003-3822")["results"][0]
    with db() as conn:
        names = dict(conn.execute("SELECT id, filename FROM documents").fetchall())
    for image in hit["images"]:
        assert image["source_pdf"] == names[image["document_id"]]


def test_image_endpoint_serves_png(client, search):
    image = search("A-5000-3603")["results"][0]["images"][0]
    response = client.get(image["image_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_alternative_images_are_verified_and_labelled(search):
    r = search("M2 stylus 2.2 mm ruby ball 20 mm long")
    assert r["outcome"] == "alternative"
    shown = [i for hit in r["results"] for i in hit["images"]]
    assert shown
    assert all(i["label"] == "Alternative" and i["association_status"] == "verified" for i in shown)


def test_product_without_image_is_still_returned(search):
    r = search("datum ball")
    assert r["outcome"] == "exact" and r["results"]
    without = [h for h in r["results"] if not h["images"]]
    assert without, "expected datum balls (H-1000-3200 p.104) to have no associated illustration"
    assert all("No verified image" in h["image_note"] for h in without)


def test_unverified_or_rejected_association_is_never_shown(search, catalogue_reports):
    part = "A-5000-3603"
    with db() as conn:
        link = conn.execute("SELECT image_id, product_id FROM product_images WHERE part_number = ?", (part,)).fetchone()
    try:
        for status in ("unverified", "rejected"):
            with db() as conn:
                conn.execute("UPDATE product_images SET association_status = ? WHERE image_id = ? AND product_id = ?",
                             (status, link["image_id"], link["product_id"]))
            hit = search(part)["results"][0]
            assert hit["images"] == [] and hit["image_note"]
    finally:
        with db() as conn:
            conn.execute("UPDATE product_images SET association_status = 'verified' WHERE image_id = ? AND product_id = ?",
                         (link["image_id"], link["product_id"]))
    assert len(search(part)["results"][0]["images"]) == 1
