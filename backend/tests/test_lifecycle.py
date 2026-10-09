"""Upload -> ingest -> search -> delete, failure handling and reconciliation (FR-09, FR-10, FR-11, FR-18)."""
import pytest

from backend.app.core.config import settings
from backend.app.db.database import db
from backend.app.llm import embeddings
from backend.tests.conftest import H1000, ZEISS, wait_for_status

ROWS = [
    # part number, description, thread, ball material, ball dia, stem material, length
    ("T-9000-0001", "Test stylus", "M6", "Ruby", "7.5", "Ceramic", "123"),
    ("T-9000-0002", "Test stylus", "M6", "Zirconia", "9.5", "Ceramic", "140"),
    ("A-5000-3603", "Stylus (also in H-1000-3200)", "M2", "Ruby", "2", "Stainless steel", "20"),
]


def upload(client, path, name=None):
    with open(path, "rb") as fh:
        return client.post("/api/documents", files={"file": (name or path.name, fh, "application/pdf")})


def artifacts(doc_id):
    with db() as conn:
        counts = {t: conn.execute(f"SELECT count(*) FROM {t} WHERE document_id = ?", (doc_id,)).fetchone()[0]
                  for t in ("products", "images", "product_images")}
        counts["document_row"] = conn.execute("SELECT count(*) FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
    counts["vectors"] = embeddings.count_document_vectors(doc_id)
    counts["image_dir"] = (settings.IMAGE_DIR / doc_id).exists()
    counts["pdf"] = (settings.UPLOAD_DIR / f"{doc_id}.pdf").exists()
    counts["reports"] = len(list(settings.REPORT_DIR.glob(f"{doc_id}_*")))
    return counts


@pytest.fixture()
def uploaded(client, pdf_factory):
    """A small uploaded catalogue that is removed again after the test."""
    path = pdf_factory(ROWS, image_for="T-9000-0001")
    response = upload(client, path)
    assert response.status_code == 202, response.text
    doc_id = response.json()["id"]
    doc = wait_for_status(client, doc_id)
    doc["_path"] = path
    yield doc
    if client.get(f"/api/documents/{doc_id}").status_code == 200:
        client.delete(f"/api/documents/{doc_id}")


def test_upload_is_ingested_and_searchable(client, search, uploaded):
    assert uploaded["status"] == "Ready", uploaded
    assert (uploaded["product_count"], uploaded["image_count"], uploaded["page_count"]) == (3, 1, 1)
    assert uploaded["embedded_count"] == 3
    assert uploaded["ingestion_report"]["extractor"] == "generic_tables"
    events = [e["event"] for e in uploaded["events"]]
    assert {"uploaded", "processing_started", "ready"} <= set(events)

    r = search("M6 stylus with 7.5 mm ruby ball 123 mm long")
    assert r["outcome"] == "exact" and [h["part_number"] for h in r["results"]] == ["T-9000-0001"]
    hit = r["results"][0]
    assert hit["source_pdf"] == "upload.pdf" and hit["source_page"] == 1 and hit["document_id"] == uploaded["id"]
    assert len(hit["images"]) == 1 and "caption" in hit["images"][0]["association_basis"]
    assert client.get(hit["images"][0]["image_url"]).status_code == 200
    # The part without a caption has no verified image and says so.
    other = search("T-9000-0002")["results"][0]
    assert other["images"] == [] and other["image_note"]


def test_uploaded_values_are_not_defaulted(search, uploaded):
    hit = search("T-9000-0002")["results"][0]
    assert (hit["thread"], hit["ball_material"], hit["ball_diameter_mm"], hit["stem_material"], hit["overall_length_mm"]) == \
        ("M6", "Zirconia", 9.5, "Ceramic", 140.0)


def test_delete_removes_everything_it_owns_and_nothing_else(client, search, uploaded):
    doc_id = uploaded["id"]
    before_builtin = {d: artifacts(d) for d in (ZEISS, H1000)}
    shared = search("A-5000-3603")["results"][0]
    assert {s["document_id"] for s in shared["sources"]} == {H1000, doc_id}

    preview = client.get(f"/api/documents/{doc_id}/deletion-preview").json()
    assert preview["will_remove"]["products"] == 3
    assert preview["will_remove"]["shared_part_numbers_kept_in_other_documents"] == 1

    response = client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["status"] == "success" and report["verification"]["verified"] is True
    assert report["removed"] == {"embeddings": 3, "image_files": 1, "product_image_links": 1, "images": 1,
                                 "products": 3, "source_file": True}
    assert artifacts(doc_id) == {"products": 0, "images": 0, "product_images": 0, "document_row": 0, "vectors": 0,
                                 "image_dir": False, "pdf": False, "reports": 0}
    assert client.get(f"/api/documents/{doc_id}").status_code == 404

    # The deleted document is no longer a source of any answer...
    assert search("M6 stylus with 7.5 mm ruby ball 123 mm long")["results"] == []
    assert search("T-9000-0001")["outcome"] == "no_match"
    # ...and the surviving sources are untouched, including the shared part number and its image.
    assert {d: artifacts(d) for d in (ZEISS, H1000)} == before_builtin
    kept = search("A-5000-3603")["results"][0]
    assert [s["document_id"] for s in kept["sources"]] == [H1000] and len(kept["images"]) == 1


def test_duplicate_upload_is_rejected(client, uploaded):
    """Same bytes under another file name: detected by SHA-256, nothing is stored twice."""
    response = upload(client, uploaded["_path"], name="renamed-copy.pdf")
    assert response.status_code == 409
    assert response.json()["existing_document_id"] == uploaded["id"]
    with db() as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 3
    assert not list((settings.DATA_DIR / "incoming").glob("*"))


def test_supplied_catalogue_reupload_is_a_duplicate(client):
    source = settings.SOURCE_PDFS_DIR / "Styli_for_ZEISS_applications_H-1000-3036_EN.pdf"
    response = upload(client, source)
    assert response.status_code == 409 and response.json()["existing_document_id"] == ZEISS


@pytest.mark.parametrize("name,content,status", [
    ("notes.txt", b"%PDF-1.4 hello", 400),
    ("fake.pdf", b"MZ\x90\x00 this is not a pdf", 400),
    ("empty.pdf", b"", 400),
])
def test_invalid_uploads_are_rejected(client, name, content, status):
    response = client.post("/api/documents", files={"file": (name, content, "application/pdf")})
    assert response.status_code == status
    assert not list((settings.DATA_DIR / "incoming").glob("*")), "no temporary file may be left behind"


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    response = client.post("/api/documents", files={"file": ("big.pdf", b"%PDF-1.4\n" + b"0" * (2 << 20), "application/pdf")})
    assert response.status_code == 413
    assert not list((settings.DATA_DIR / "incoming").glob("*"))


def test_upload_filename_cannot_escape_the_upload_directory(client, pdf_factory):
    path = pdf_factory([("T-9100-0001", "Test stylus", "M6", "Ruby", "3", "Ceramic", "33")], name="evil.pdf")
    response = upload(client, path, name="..\\..\\..\\evil/../../x.pdf")
    assert response.status_code == 202
    doc_id = response.json()["id"]
    doc = wait_for_status(client, doc_id)
    try:
        assert doc["filename"] == "x.pdf"
        stored = [p for p in settings.UPLOAD_DIR.iterdir()]
        assert all(p.parent == settings.UPLOAD_DIR and p.name.startswith("doc_") for p in stored)
    finally:
        assert client.delete(f"/api/documents/{doc_id}").status_code == 200


def test_corrupt_pdf_fails_cleanly_and_can_be_retried(client, monkeypatch):
    response = client.post("/api/documents", files={"file": ("broken.pdf", b"%PDF-1.7\n" + b"\x00garbage" * 200, "application/pdf")})
    assert response.status_code == 202
    doc_id = response.json()["id"]
    doc = wait_for_status(client, doc_id)
    try:
        assert doc["status"] == "Failed" and doc["error_message"]
        assert "Traceback" not in doc["error_message"] and str(settings.DATA_DIR) not in doc["error_message"]
        left = artifacts(doc_id)
        assert (left["products"], left["images"], left["vectors"], left["image_dir"]) == (0, 0, 0, False)
        retry = client.post(f"/api/documents/{doc_id}/retry")
        assert retry.status_code == 202
        assert wait_for_status(client, doc_id)["status"] == "Failed"
        assert client.post(f"/api/documents/{ZEISS}/retry").status_code == 409  # only failed documents
    finally:
        assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    assert artifacts(doc_id)["document_row"] == 0 and not artifacts(doc_id)["pdf"]


def test_failure_midway_leaves_no_partial_data(client, pdf_factory, monkeypatch):
    """Extraction succeeds but the vector write fails: nothing of the document may become searchable."""
    def broken(*args, **kwargs):
        raise RuntimeError("vector store unavailable")
    monkeypatch.setattr(embeddings, "upsert_document_vectors", broken)
    path = pdf_factory([("T-9200-0001", "Test stylus", "M6", "Ruby", "4.5", "Ceramic", "44")], name="midway.pdf",
                       image_for="T-9200-0001")
    doc_id = upload(client, path).json()["id"]
    doc = wait_for_status(client, doc_id)
    try:
        assert doc["status"] == "Failed"
        left = artifacts(doc_id)
        assert (left["products"], left["images"], left["product_images"], left["vectors"], left["image_dir"]) == (0, 0, 0, 0, False)
        response = client.post("/api/search", json={"query": "T-9200-0001"}).json()
        assert response["outcome"] == "no_match"
        monkeypatch.undo()
        client.post(f"/api/documents/{doc_id}/retry")
        assert wait_for_status(client, doc_id)["status"] == "Ready"
        assert client.post("/api/search", json={"query": "T-9200-0001"}).json()["outcome"] == "exact"
    finally:
        monkeypatch.undo()
        assert client.delete(f"/api/documents/{doc_id}").status_code == 200


def test_failed_deletion_is_not_reported_as_success_and_is_recoverable(client, search, pdf_factory, monkeypatch):
    path = pdf_factory([("T-9300-0001", "Test stylus", "M6", "Ruby", "5.5", "Ceramic", "55")], name="stuck.pdf")
    doc_id = upload(client, path).json()["id"]
    assert wait_for_status(client, doc_id)["status"] == "Ready"
    assert search("T-9300-0001")["outcome"] == "exact"

    def broken(doc):
        raise RuntimeError("vector store unavailable")
    monkeypatch.setattr(embeddings, "delete_document_vectors", broken)
    response = client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 500
    body = response.json()
    assert body["report"]["status"] == "failed" and body["report"]["failed_step"] == "remove vector-index entries"
    assert "RuntimeError" not in body["detail"] and "vector store unavailable" not in body["detail"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "Deleting" and doc["error_message"]
    # Excluded from search immediately, even though cleanup has not finished.
    assert search("T-9300-0001")["outcome"] == "no_match"
    assert embeddings.count_document_vectors(doc_id) == 1

    monkeypatch.undo()
    report = client.post("/api/admin/reconcile").json()
    assert doc_id in report["deletions_resumed"]
    assert artifacts(doc_id) == {"products": 0, "images": 0, "product_images": 0, "document_row": 0, "vectors": 0,
                                 "image_dir": False, "pdf": False, "reports": 0}


def test_reconcile_removes_orphans(client):
    coll = embeddings.get_or_create_collection()
    coll.upsert(ids=["doc_ghost:X-1"], embeddings=[[0.1] * 16], metadatas=[{"document_id": "doc_ghost", "part_number": "X-1"}])
    ghost_dir = settings.IMAGE_DIR / "doc_ghost"
    ghost_dir.mkdir()
    (ghost_dir / "p001.png").write_bytes(b"x")
    stray_image = settings.IMAGE_DIR / ZEISS / "stray.png"
    stray_image.write_bytes(b"x")
    stray_pdf = settings.UPLOAD_DIR / "doc_ghost.pdf"
    stray_pdf.write_bytes(b"%PDF-1.4")
    report = client.post("/api/admin/reconcile").json()
    assert report["orphaned_vectors_removed"] == 1
    assert report["orphaned_image_directories_cleaned"] == ["doc_ghost"]
    assert report["orphaned_image_files_removed"] == 1
    assert report["orphaned_upload_files_removed"] == ["doc_ghost.pdf"]
    assert not ghost_dir.exists() and not stray_image.exists() and not stray_pdf.exists()
    assert report["documents_needing_reindex"] == []
    assert set(report["active_documents"]) == {ZEISS, H1000}


def test_vector_index_is_in_sync_and_reindex_rebuilds_it(client):
    status = embeddings.index_status()
    assert status["in_sync"] and status["item_count"] == status["expected_count"] > 1400
    summary = embeddings.reindex_all()
    assert summary["indexed_items"] == status["expected_count"]
    assert embeddings.index_status()["in_sync"]
    with db() as conn:
        for row in conn.execute("SELECT id, embedded_count FROM documents"):
            assert row["embedded_count"] == embeddings.count_document_vectors(row["id"])


def test_stale_vector_can_never_surface(search):
    """A vector whose document is not Ready is ignored: results are always re-read from Ready documents."""
    coll = embeddings.get_or_create_collection()
    coll.upsert(ids=["doc_gone:Z-1"], embeddings=embeddings.ollama_client.embed(["swivel stylus M2"]),
                metadatas=[{"document_id": "doc_gone", "part_number": "Z-1"}])
    try:
        r = search("M2 swivel stylus")
        assert all(h["document_id"] in (ZEISS, H1000) for h in r["results"])
    finally:
        coll.delete(ids=["doc_gone:Z-1"])


def test_interrupted_ingestion_is_recovered_at_startup(client):
    from backend.app.lifecycle.reconciliation import recover_interrupted_documents
    stored = settings.UPLOAD_DIR / "doc_interrupted.pdf"
    stored.write_bytes(b"%PDF-1.4")
    with db() as conn:
        conn.execute("INSERT INTO documents (id, filename, file_hash, file_path, file_size, status) VALUES "
                     "('doc_interrupted', 'i.pdf', 'hash-i', ?, 8, 'Processing')", (str(stored),))
    try:
        outcome = recover_interrupted_documents()
        assert outcome["marked_failed"] == ["doc_interrupted"]
        doc = client.get("/api/documents/doc_interrupted").json()
        assert doc["status"] == "Failed" and "interrupted" in doc["error_message"]
    finally:
        assert client.delete("/api/documents/doc_interrupted").status_code == 200


def test_document_list_and_report_download(client):
    docs = {d["id"]: d for d in client.get("/api/documents").json()}
    assert docs[ZEISS]["status"] == docs[H1000]["status"] == "Ready"
    assert docs[ZEISS]["product_count"] > 600 and docs[H1000]["image_count"] > 400
    assert "file_path" not in docs[ZEISS], "server paths are not exposed"
    report = client.get(f"/api/documents/{H1000}/report")
    assert report.status_code == 200 and report.json()["products_extracted"] == docs[H1000]["product_count"]
    assert client.get(f"/api/documents/{H1000}/report?kind=images").text.startswith("image_id,")
    assert client.get(f"/api/documents/{H1000}/report?kind=../../renishaw.db").status_code == 400
    assert client.get("/api/documents/doc_missing").status_code == 404
    assert client.delete("/api/documents/doc_missing").status_code == 404
