"""Shared test setup.

The suite never touches the application's real data directory: before any
application module is imported, RENISHAW_DATA_DIR is pointed at a temporary
directory. Both supplied catalogues are ingested there once per session with
the real extraction pipeline.

No test needs Ollama: the LLM is off (tests that exercise the LLM path inject
its answer) and the embedding model is replaced by a deterministic local
stand-in so the vector-index lifecycle is still exercised. A socket guard
fails any test that tries to reach a non-loopback address.
"""
import hashlib
import os
import shutil
import socket
import tempfile
import time
from pathlib import Path

_DATA_DIR = Path(tempfile.mkdtemp(prefix="renishaw_tests_"))
os.environ["RENISHAW_DATA_DIR"] = str(_DATA_DIR)
os.environ["RENISHAW_LLM_MODE"] = "off"
os.environ["RENISHAW_EMBEDDINGS_ENABLED"] = "true"
os.environ["RENISHAW_AUTO_INGEST_SOURCE_PDFS"] = "false"

import pytest  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.evaluation.sample_pdf import make_catalogue_pdf  # noqa: E402
from backend.app.llm.ollama_client import ollama_client  # noqa: E402

ZEISS = "doc_zeiss"
H1000 = "doc_h1000"


def fake_embed(texts):
    """Deterministic 16-dimensional stand-in for the embedding model (no network, no model)."""
    vectors = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vectors.append([(b - 127.5) / 127.5 for b in digest[:16]])
    return vectors


_real_connect = socket.socket.connect


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, (bytes, bytearray)):
        host = host.decode()
    if self.family in (socket.AF_INET, socket.AF_INET6) and str(host) not in ("127.0.0.1", "::1", "localhost"):
        raise AssertionError(f"Test tried to open an external network connection to {host}")
    return _real_connect(self, address)


@pytest.fixture(scope="session", autouse=True)
def offline_and_isolated():
    assert settings.DATA_DIR == _DATA_DIR, "tests must not run against the real data directory"
    socket.socket.connect = _guarded_connect
    ollama_client.embed = fake_embed
    yield
    socket.socket.connect = _real_connect
    shutil.rmtree(_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def catalogue_reports(offline_and_isolated):
    """Ingest both supplied catalogues once with the real pipeline."""
    from backend.app.ingestion.pipeline import ingest_initial_catalogues
    reports = ingest_initial_catalogues()
    assert set(reports) == {ZEISS, H1000}, reports
    for doc_id, report in reports.items():
        assert "error" not in report, (doc_id, report)
    return reports


@pytest.fixture(scope="session")
def client(catalogue_reports):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def bare_client(offline_and_isolated):
    """API client that does not need the supplied catalogues; tests using it upload their own PDFs."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def search(client):
    def run(query, **extra):
        response = client.post("/api/search", json={"query": query, **extra})
        assert response.status_code == 200, response.text
        return response.json()
    return run


def wait_for_status(client, doc_id, wanted=("Ready", "Failed"), timeout=120.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/documents/{doc_id}")
        if response.status_code == 200 and response.json()["status"] in wanted:
            return response.json()
        time.sleep(0.2)
    raise AssertionError(f"{doc_id} did not reach {wanted} in {timeout}s")


@pytest.fixture()
def pdf_factory(tmp_path):
    def build(rows, name="upload.pdf", **kwargs):
        return make_catalogue_pdf(tmp_path / name, rows, **kwargs)
    return build
