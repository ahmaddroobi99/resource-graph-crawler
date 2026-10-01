from service.document_store import DocumentStore, IdempotencyConflict
from service.document_processing import extract_entities, preprocess_image, validate_document
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor


def test_document_and_job_survive_store_restart(tmp_path):
    database = tmp_path / "documents.sqlite3"
    store = DocumentStore(database)
    document, job, created = store.create_document(
        filename="resume.pdf", media_type="application/pdf", size_bytes=10,
        original_path=str(tmp_path / "doc.pdf"), metadata={"source": "user_upload"},
        fingerprint="fingerprint", idempotency_key="request-1",
    )

    restarted = DocumentStore(database)
    assert created is True
    assert document["id"].startswith("doc_")
    assert job["status"] == "QUEUED"
    assert restarted.get_document(document["id"])["filename"] == "resume.pdf"
    assert restarted.get_job(document["id"])["id"] == job["id"]
    assert restarted.recover_jobs() == [document["id"]]


def test_recovery_fails_jobs_that_exhausted_attempt_limit(tmp_path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    document, _, _ = store.create_document(
        filename="resume.pdf", media_type="application/pdf", size_bytes=10,
        original_path=str(tmp_path / "doc.pdf"), metadata={}, fingerprint="x",
        idempotency_key=None, max_attempts=1,
    )
    store.update_job(document["id"], status="PROCESSING", stage="OCR", increment_attempt=True)

    assert store.recover_jobs() == []
    assert store.get_document(document["id"])["status"] == "FAILED"
    assert store.get_job(document["id"])["error_code"] == "TIMEOUT"
    assert store.get_errors(document["id"])[0]["retryable"] is False


def test_idempotency_returns_existing_job_and_rejects_different_payload(tmp_path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    arguments = dict(
        filename="resume.pdf", media_type="application/pdf", size_bytes=10,
        original_path=str(tmp_path / "doc.pdf"), metadata={},
        fingerprint="same", idempotency_key="request-1",
    )
    first_document, first_job, _ = store.create_document(**arguments)
    second_document, second_job, created = store.create_document(**arguments)

    assert created is False
    assert second_document["id"] == first_document["id"]
    assert second_job["id"] == first_job["id"]
    arguments["fingerprint"] = "different"
    try:
        store.create_document(**arguments)
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("Expected idempotency key reuse with different content to fail")


def test_concurrent_idempotent_creates_share_one_document_and_job(tmp_path):
    store = DocumentStore(tmp_path / "documents.sqlite3")
    arguments = dict(
        filename="resume.pdf", media_type="application/pdf", size_bytes=10,
        original_path=str(tmp_path / "doc.pdf"), metadata={},
        fingerprint="same", idempotency_key="concurrent-request",
    )
    with ThreadPoolExecutor(max_workers=6) as executor:
        created = list(executor.map(lambda _: store.create_document(**arguments), range(6)))

    document_ids = {document["id"] for document, _, _ in created}
    job_ids = {job["id"] for _, job, _ in created}
    assert len(document_ids) == len(job_ids) == 1
    assert sum(is_new for _, _, is_new in created) == 1


def test_full_text_search_indexes_page_and_entity_text_across_restart(tmp_path):
    database = tmp_path / "documents.sqlite3"
    store = DocumentStore(database)
    document_ids = []
    for name in ("Jordan Sample", "Taylor Example"):
        document, _, _ = store.create_document(
            filename=f"{name.split()[0]}.pdf", media_type="application/pdf", size_bytes=10,
            original_path=str(tmp_path / f"{name.split()[0]}.pdf"), metadata={},
            fingerprint=name, idempotency_key=None, page_count=1,
        )
        document_ids.append(document["id"])
        store.update_document(document["id"], status="COMPLETED")
        store.save_page(document["id"], 1, status="COMPLETED",
                        text=f"{name} builds Python systems", blocks=[])
        store.replace_entities(document["id"], [{
            "text": name, "type": "PERSON", "confidence": None,
            "evidence": {"page": 1, "text": name, "bbox": None},
        }])

    restarted = DocumentStore(database)
    first_page, next_cursor = restarted.search("Python", limit=1)
    second_page, final_cursor = restarted.search("Python", limit=1, cursor=next_cursor)
    by_entity, _ = restarted.search("Jordan")

    assert len(first_page) == len(second_page) == 1
    assert first_page[0]["document_id"] != second_page[0]["document_id"]
    assert final_cursor is None
    assert by_entity[0]["document_id"] == document_ids[0]
    assert by_entity[0]["matches"][0]["type"] == "ENTITY"


def test_upload_validation_uses_file_signature_and_parseability():
    image_bytes = io.BytesIO()
    Image.new("RGB", (80, 30), "white").save(image_bytes, format="PNG")
    assert validate_document(image_bytes.getvalue()) == ("image/png", 1)

    jpeg_bytes = io.BytesIO()
    Image.new("RGB", (80, 30), "white").save(jpeg_bytes, format="JPEG")
    assert validate_document(jpeg_bytes.getvalue()) == ("image/jpeg", 1)

    try:
        validate_document(b"%PDF-not-a-valid-pdf")
    except ValueError as error:
        assert getattr(error, "code", None) == "CORRUPTED_DOCUMENT"
    else:
        raise AssertionError("Expected corrupt PDF to be rejected")


def test_image_pixel_limit_is_enforced(monkeypatch):
    from service import document_processing

    image_bytes = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(image_bytes, format="PNG")
    monkeypatch.setattr(document_processing, "DOCUMENT_MAX_PIXELS", 100)
    try:
        validate_document(image_bytes.getvalue())
    except ValueError as error:
        assert getattr(error, "code", None) == "FILE_TOO_LARGE"
    else:
        raise AssertionError("Expected image pixel limit to be enforced")


def test_preprocessing_returns_image_and_entity_evidence_is_grounded():
    processed = preprocess_image(Image.new("RGB", (200, 80), "white"))
    assert processed.size[0] > 0 and processed.size[1] > 0

    block = {"id": "blk_fixture", "text": "John Smith | Python | john@example.com",
             "bbox": {"x": 1, "y": 2, "width": 30, "height": 10}, "confidence": None}
    entities = extract_entities([{"page": 1, "blocks": [block]}])
    assert {entity["type"] for entity in entities} >= {"PERSON", "SKILL", "EMAIL"}
    assert all(entity["evidence"]["text"] == block["text"] for entity in entities)