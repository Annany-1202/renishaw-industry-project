"""Browsing one document: all extracted images, and all extracted parts with specifications and images.

Uses a synthetic catalogue (uploaded through the API and removed afterwards), so these
tests do not depend on the supplied catalogues.
"""
import pytest

from backend.app.db.database import db
from backend.app.evaluation.sample_pdf import make_catalogue_pdf
from backend.tests.conftest import wait_for_status

ROWS = [
    # part number, description, thread, ball material, ball dia, stem material, length
    ("T-9100-0001", "Browse stylus", "M9", "Ruby", "1", "Ceramic", "20"),
    ("T-9100-0002", "Browse stylus", "M9", "Ruby", "2", "Ceramic", "20"),
    ("T-9100-0003", "Browse stylus", "M9", "Ruby", "3", "Ceramic", "30"),
    ("T-9100-0004", "Browse extension", "M9", "", "", "Titanium", "50"),
]


@pytest.fixture(scope="module")
def browse_doc(bare_client, tmp_path_factory):
    path = make_catalogue_pdf(tmp_path_factory.mktemp("browse") / "browse.pdf", ROWS, image_for="T-9100-0002")
    with open(path, "rb") as fh:
        response = bare_client.post("/api/documents", files={"file": ("browse.pdf", fh, "application/pdf")})
    assert response.status_code == 202, response.text
    doc = wait_for_status(bare_client, response.json()["id"])
    assert doc["status"] == "Ready", doc
    yield doc
    bare_client.delete(f"/api/documents/{doc['id']}")


def test_gallery_lists_every_extracted_image_with_details(bare_client, browse_doc):
    r = bare_client.get(f"/api/documents/{browse_doc['id']}/images")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "browse.pdf" and body["total"] == browse_doc["image_count"] == 1
    with db() as conn:
        stored = {row[0] for row in conn.execute("SELECT image_id FROM images WHERE document_id = ?", (browse_doc["id"],))}
    assert {i["image_id"] for i in body["images"]} == stored
    image = body["images"][0]
    assert image["page_number"] == 1 and image["source_pdf"] == "browse.pdf"
    assert image["image_type"] in ("photograph", "drawing", "diagram", "unknown")
    assert body["image_types"] == {image["image_type"]: 1} and body["linked_images"] == 1
    assert image["description"]
    [part] = image["associated_parts"]
    assert part["part_number"] == "T-9100-0002" and part["association_status"] == "verified"
    assert part["association_basis"] and part["product_id"]
    served = bare_client.get(image["image_url"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"


def test_all_parts_lists_specifications_provenance_and_images(bare_client, browse_doc):
    r = bare_client.get(f"/api/documents/{browse_doc['id']}/parts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == browse_doc["product_count"] == len(ROWS)
    assert sum(body["categories"].values()) == len(ROWS)
    by_number = {p["part_number"]: p for p in body["parts"]}
    assert set(by_number) == {row[0] for row in ROWS}
    stylus = by_number["T-9100-0002"]
    assert (stylus["thread"], stylus["ball_material"], stylus["ball_diameter_mm"], stylus["stem_material"],
            stylus["overall_length_mm"]) == ("M9", "Ruby", 2.0, "Ceramic", 20.0)
    assert stylus["source_pdf"] == "browse.pdf" and stylus["source_page"] == 1 and stylus["document_id"] == browse_doc["id"]
    assert stylus["validation_status"] and isinstance(stylus["original_values"], dict)
    assert [i["association_status"] for i in stylus["images"]] == ["verified"]
    assert stylus["images"][0]["page_number"] == 1 and stylus["images"][0]["image_url"].startswith("/api/images/")
    assert by_number["T-9100-0001"]["images"] == []
    assert by_number["T-9100-0004"]["ball_diameter_mm"] is None, "values the PDF does not state stay empty"


def test_parts_can_be_filtered_and_paged(bare_client, browse_doc):
    url = f"/api/documents/{browse_doc['id']}/parts"
    found = bare_client.get(url, params={"q": "t-9100-0003"}).json()
    assert found["total"] == 1 and found["parts"][0]["part_number"] == "T-9100-0003"
    category = next(iter(bare_client.get(url).json()["categories"]))
    filtered = bare_client.get(url, params={"category": category}).json()
    assert filtered["parts"] and all(p["category"] == category for p in filtered["parts"])
    first = bare_client.get(url, params={"limit": 2}).json()
    second = bare_client.get(url, params={"limit": 2, "offset": 2}).json()
    assert len(first["parts"]) == len(second["parts"]) == 2 and first["total"] == len(ROWS)
    assert not {p["id"] for p in first["parts"]} & {p["id"] for p in second["parts"]}
    # LIKE wildcards in the filter are literal characters.
    assert bare_client.get(url, params={"q": "%"}).json()["total"] == 0
    assert bare_client.get(url, params={"q": "_"}).json()["total"] == 0
    assert bare_client.get(url, params={"limit": 0}).status_code == 422


def test_unknown_and_malformed_documents_are_not_found(bare_client):
    for doc_id in ("doc_doesnotexist", "../etc", "doc_x;drop"):
        for kind in ("images", "parts"):
            assert bare_client.get(f"/api/documents/{doc_id}/{kind}").status_code == 404


def test_document_that_is_not_ready_is_not_browsable(bare_client):
    with db() as conn:
        conn.execute(
            "INSERT INTO documents (id, filename, file_hash, file_path, file_size, status) "
            "VALUES ('doc_notready', 'x.pdf', 'hash_notready', 'x.pdf', 1, 'Failed')")
    try:
        for kind in ("images", "parts"):
            r = bare_client.get(f"/api/documents/doc_notready/{kind}")
            assert r.status_code == 409 and "Ready" in r.json()["detail"]
    finally:
        with db() as conn:
            conn.execute("DELETE FROM documents WHERE id = 'doc_notready'")
