import fitz
import yaml
from fastapi.testclient import TestClient
from pathlib import Path

from service.app import app
from service import document_api
from service.document_store import DocumentStore


class StubWorker:
    def start(self):
        pass

    def enqueue(self, _document_id):
        pass


def pdf_bytes(text="John Smith"):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    return pdf.tobytes()


def setup_api(tmp_path, monkeypatch):
    monkeypatch.setattr(document_api, "DOCUMENT_API_KEY", "test-key")
    monkeypatch.setattr(document_api, "IS_SERVERLESS", False)
    monkeypatch.setattr(document_api, "DOCUMENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(document_api, "STORE", DocumentStore(tmp_path / "documents.sqlite3"))
    monkeypatch.setattr(document_api, "WORKER", StubWorker())
    return TestClient(app)


def auth_headers():
    return {"Authorization": "Bearer test-key"}


def test_upload_returns_document_and_queued_job_without_waiting(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    content = pdf_bytes()
    response = client.post(
        "/api/v1/documents", headers=auth_headers(),
        files={"file": ("resume.pdf", content, "text/plain")},
        data={"metadata": '{"source":"user_upload"}'},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["status"] == "PROCESSING"
    assert body["document"]["media_type"] == "application/pdf"
    assert body["job"]["status"] == "QUEUED"
    assert body["document"]["id"].startswith("doc_")
    assert "original_path" not in body["document"]
    assert body["document"]["created_at"].endswith("Z")

    persisted = document_api.STORE.get_document(body["document"]["id"])
    with open(persisted["original_path"], "rb") as original:
        assert original.read() == content


def test_idempotency_and_mismatch_use_existing_job_or_common_error(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    key_headers = {**auth_headers(), "Idempotency-Key": "upload-once"}
    content = pdf_bytes()
    first = client.post("/api/v1/documents", headers=key_headers,
                        files={"file": ("resume.pdf", content, "application/pdf")})
    replay = client.post("/api/v1/documents", headers=key_headers,
                         files={"file": ("resume.pdf", content, "application/pdf")})
    changed = client.post("/api/v1/documents", headers=key_headers,
                          files={"file": ("other.pdf", pdf_bytes("Different"), "application/pdf")})

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["document"]["id"] == first.json()["document"]["id"]
    assert replay.json()["job"]["id"] == first.json()["job"]["id"]
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "INVALID_REQUEST"


def test_document_results_search_and_missing_resource_contract(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    uploaded = client.post("/api/v1/documents", headers=auth_headers(),
                           files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")})
    document_id = uploaded.json()["document"]["id"]
    document_api.STORE.update_document(document_id, status="COMPLETED")
    document_api.STORE.update_job(document_id, status="COMPLETED", stage="COMPLETED",
                                  progress_percent=100)
    document_api.STORE.save_page(
        document_id, 1, status="COMPLETED", text="John Smith uses Python",
        blocks=[{"id": "blk_fixture", "text": "John Smith uses Python",
                 "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}, "confidence": None}],
        width=600, height=800,
    )
    document_api.STORE.replace_entities(document_id, [{
        "id": "ent_fixture", "text": "Python", "type": "SKILL", "confidence": None,
        "evidence": {"page": 1, "text": "John Smith uses Python", "bbox": None},
    }])

    pages = client.get(f"/api/v1/documents/{document_id}/pages", headers=auth_headers())
    entities = client.get(f"/api/v1/documents/{document_id}/entities", headers=auth_headers())
    status = client.get(f"/api/v1/documents/{document_id}/status", headers=auth_headers())
    entity_id = entities.json()["entities"][0]["id"]
    entity = client.get(f"/api/v1/entities/{entity_id}", headers=auth_headers())
    search = client.get("/api/v1/search?q=Python", headers=auth_headers())
    empty = client.get("/api/v1/search?q=%20%20", headers=auth_headers())
    missing = client.get("/api/v1/documents/doc_missing", headers=auth_headers())

    assert pages.status_code == 200 and pages.json()["pages"][0]["width"] == 600
    assert entities.status_code == 200 and entities.json()["entities"][0]["type"] == "SKILL"
    assert status.json()["job"]["status"] == "COMPLETED"
    assert status.json()["progress"]["percent"] == 100
    assert entity.json()["entity"]["evidence"]["page"] == 1
    assert search.status_code == 200 and search.json()["results"][0]["document_id"] == document_id
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "EMPTY_QUERY"
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_upload_requires_configured_bearer_key_and_errors_are_enveloped(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    unauthorized = client.get("/api/v1/search?q=Python")
    invalid_query = client.get("/api/v1/search", headers=auth_headers())

    assert unauthorized.status_code == 401
    assert set(unauthorized.json()) == {"error"}
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"
    assert invalid_query.status_code == 400
    assert invalid_query.json()["error"]["code"] == "INVALID_REQUEST"


def test_checked_in_openapi_covers_document_routes_and_contract():
    spec_path = Path(__file__).resolve().parents[1] / "openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    route_map = app.openapi()["paths"]
    for path, methods in spec["paths"].items():
        for method in methods:
            if path.startswith("/api/v1/documents") or path.startswith("/api/v1/entities") or path == "/api/v1/search":
                assert method in route_map[path]
    assert "multipart/form-data" in spec["paths"]["/api/v1/documents"]["post"]["requestBody"]["content"]
    assert spec["components"]["schemas"]["JobStatus"]["enum"] == [
        "QUEUED", "PROCESSING", "COMPLETED", "PARTIAL", "FAILED"
    ]
    assert spec["components"]["parameters"]["Limit"]["schema"]["maximum"] == 100


def test_document_workbench_and_openapi_yaml_are_served():
    client = TestClient(app)
    assert "Document Workbench" in client.get("/documents").text
    contract = client.get("/openapi.yaml")
    assert contract.status_code == 200
    assert "createDocument" in contract.text


def test_upload_rejects_empty_unsupported_corrupt_large_and_bad_metadata(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    base = {"headers": auth_headers()}
    empty = client.post("/api/v1/documents", **base,
                        files={"file": ("empty.pdf", b"", "application/pdf")})
    unsupported = client.post("/api/v1/documents", **base,
                              files={"file": ("note.txt", b"not a document", "text/plain")})
    corrupt = client.post("/api/v1/documents", **base,
                          files={"file": ("broken.pdf", b"%PDF-invalid", "application/pdf")})
    metadata = client.post("/api/v1/documents", **base,
                           files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")},
                           data={"metadata": "not-json"})
    monkeypatch.setattr(document_api, "DOCUMENT_MAX_UPLOAD_SIZE_BYTES", 10)
    oversized = client.post("/api/v1/documents", **base,
                            files={"file": ("resume.pdf", pdf_bytes(), "application/pdf")})

    assert (empty.status_code, empty.json()["error"]["code"]) == (400, "EMPTY_FILE")
    assert (unsupported.status_code, unsupported.json()["error"]["code"]) == (415, "UNSUPPORTED_FILE_TYPE")
    assert (corrupt.status_code, corrupt.json()["error"]["code"]) == (422, "CORRUPTED_DOCUMENT")
    assert (metadata.status_code, metadata.json()["error"]["code"]) == (400, "INVALID_REQUEST")
    assert (oversized.status_code, oversized.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


def test_serverless_document_api_is_disabled(tmp_path, monkeypatch):
    client = setup_api(tmp_path, monkeypatch)
    monkeypatch.setattr(document_api, "IS_SERVERLESS", True)
    response = client.get("/api/v1/search?q=Python", headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DOCUMENT_API_DISABLED"


def test_search_and_database_failures_have_safe_common_errors(tmp_path, monkeypatch):
    import sqlite3

    client = setup_api(tmp_path, monkeypatch)

    def fail_search(*_args):
        raise RuntimeError("private filesystem path must not escape")

    monkeypatch.setattr(document_api.STORE, "search", fail_search)
    search_error = client.get("/api/v1/search?q=Python", headers=auth_headers())
    monkeypatch.setattr(document_api.STORE, "search",
                        lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError("private path")))
    database_error = client.get("/api/v1/search?q=Python", headers=auth_headers())

    assert search_error.status_code == 500
    assert search_error.json()["error"]["code"] == "SEARCH_FAILED"
    assert "private filesystem path" not in search_error.text
    assert database_error.status_code == 500
    assert database_error.json()["error"]["code"] == "DATABASE_ERROR"