import fitz
from pathlib import Path

from service.document_processing import OCRUnavailable, validate_document
from service.document_store import DocumentStore
from service.document_worker import DocumentWorker


def make_pdf(page_count=1):
    pdf = fitz.open()
    for index in range(page_count):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    return pdf.tobytes()


def create_queued_document(tmp_path, content):
    media_type, page_count = validate_document(content)
    source = tmp_path / "original.pdf"
    source.write_bytes(content)
    store = DocumentStore(tmp_path / "documents.sqlite3")
    document, _, _ = store.create_document(
        filename="resume.pdf", media_type=media_type, size_bytes=len(content),
        original_path=str(source), metadata={}, fingerprint="fixture",
        idempotency_key=None, page_count=page_count,
    )
    return store, document, source


def test_worker_completes_document_and_preserves_original(tmp_path, monkeypatch):
    original = make_pdf()
    store, document, source = create_queued_document(tmp_path, original)
    stages = []
    update_job = store.update_job

    def record_stage(document_id, **changes):
        stages.append(changes.get("stage"))
        update_job(document_id, **changes)

    monkeypatch.setattr(store, "update_job", record_stage)

    def fake_ocr(_image, document_id, page_number, preprocessed=False):
        block = {"id": f"blk_{document_id}_{page_number}", "text": "John Smith Python",
                 "bbox": {"x": 1, "y": 2, "width": 30, "height": 10}, "confidence": 0.8}
        return {"blocks": [block], "text": block["text"], "width": 300, "height": 200}

    monkeypatch.setattr("service.document_worker.ocr_page", fake_ocr)
    DocumentWorker(store)._process(document["id"])

    assert store.get_document(document["id"])["status"] == "COMPLETED"
    assert store.get_job(document["id"])["status"] == "COMPLETED"
    assert store.get_pages(document["id"])[0]["blocks"][0]["confidence"] == 0.8
    assert store.get_entities(document["id"])
    assert source.read_bytes() == original
    assert {"VALIDATION", "PREPROCESSING", "OCR", "ENTITY_EXTRACTION", "INDEXING", "COMPLETED"} <= set(stages)


def test_worker_retains_successful_pages_after_partial_ocr_failure(tmp_path, monkeypatch):
    store, document, _ = create_queued_document(tmp_path, make_pdf(page_count=2))

    def fake_ocr(_image, document_id, page_number, preprocessed=False):
        if page_number == 2:
            raise OCRUnavailable("OCR failed")
        block = {"id": "blk_success", "text": "Python", "bbox": None, "confidence": None}
        return {"blocks": [block], "text": block["text"], "width": 300, "height": 200}

    monkeypatch.setattr("service.document_worker.ocr_page", fake_ocr)
    DocumentWorker(store)._process(document["id"])

    assert store.get_document(document["id"])["status"] == "PARTIAL"
    pages = store.get_pages(document["id"])
    assert [page["status"] for page in pages] == ["COMPLETED", "FAILED"]
    assert pages[0]["text"] == "Python"
    assert store.get_errors(document["id"])[0]["page"] == 2
    assert any(error["code"] == "OCR_PARTIAL" for error in store.get_errors(document["id"]))


def test_retryable_ocr_timeout_is_requeued_and_eventually_completes(tmp_path, monkeypatch):
    store, document, _ = create_queued_document(tmp_path, make_pdf(page_count=2))
    attempts = 0

    def flaky_ocr(_image, document_id, page_number, preprocessed=False):
        nonlocal attempts
        if page_number == 2 and attempts == 0:
            attempts += 1
            raise OCRUnavailable("OCR timed out", retryable=True)
        block = {"id": f"blk_retry_{page_number}", "text": "Python", "bbox": None, "confidence": None}
        return {"blocks": [block], "text": "Python", "width": 300, "height": 200}

    monkeypatch.setattr("service.document_worker.ocr_page", flaky_ocr)
    monkeypatch.setattr("service.document_worker.DOCUMENT_RETRY_BASE_SECONDS", 0)
    worker = DocumentWorker(store)
    worker._active.add(document["id"])
    worker._process(document["id"])
    assert store.get_job(document["id"])["status"] == "QUEUED"
    assert worker._queue.get_nowait() == document["id"]
    worker._process(document["id"])

    assert attempts == 1
    assert store.get_job(document["id"])["status"] == "COMPLETED"
    assert store.get_errors(document["id"]) == []


def test_fixture_upload_to_search_and_source_evidence(tmp_path, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "sample_resume.pdf"
    original = fixture.read_bytes()
    store, document, source = create_queued_document(tmp_path, original)
    recognized_lines = [
        "Jordan Sample",
        "jordan.sample@example.test | https://portfolio.example.test",
        "Company: Northstar Robotics",
        "Location: Calgary, Canada",
        "Skills: Python, SQL, Docker",
        "2024-01-01",
    ]

    def fake_ocr(_image, document_id, page_number, preprocessed=False):
        blocks = [{"id": f"blk_{document_id}_{index}", "text": text,
                   "bbox": {"x": 12, "y": index * 20, "width": 200, "height": 16},
                   "confidence": None}
                  for index, text in enumerate(recognized_lines)]
        return {"blocks": blocks, "text": "\n".join(recognized_lines),
                "width": 600, "height": 800}

    monkeypatch.setattr("service.document_worker.ocr_page", fake_ocr)
    DocumentWorker(store)._process(document["id"])

    entities = store.get_entities(document["id"])
    types = {entity["type"] for entity in entities}
    assert {"PERSON", "ORGANIZATION", "LOCATION", "DATE", "EMAIL", "URL", "SKILL"} <= types
    assert all(entity["evidence"]["page"] == 1 for entity in entities)
    results, next_cursor = store.search("Python")
    assert results[0]["document_id"] == document["id"]
    assert next_cursor is None
    assert source.read_bytes() == original