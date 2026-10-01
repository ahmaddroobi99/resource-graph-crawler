"""Restart-recoverable single-process worker for document processing jobs."""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

from config import (
    DOCUMENT_MAX_PROCESSING_SECONDS,
    DOCUMENT_RETRY_BASE_SECONDS,
    DOCUMENT_WORKER_POLL_SECONDS,
)
from service.document_processing import (
    OCRUnavailable,
    extract_entities,
    iter_document_pages,
    ocr_page,
    preprocess_image,
)
from service.document_store import DocumentStore, utc_now


LOGGER = logging.getLogger("rgc.documents.worker")


class DocumentWorker:
    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._pending: set[str] = set()
        self._active: set[str] = set()

    def start(self) -> None:
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            for document_id in self.store.recover_jobs():
                self.enqueue(document_id)
            self._thread = threading.Thread(target=self._run, name="document-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    def enqueue(self, document_id: str) -> None:
        with self._lock:
            if document_id in self._pending or document_id in self._active:
                return
            self._pending.add(document_id)
        self._queue.put(document_id)

    def _run(self) -> None:
        for document_id in self.store.queued_documents():
            self.enqueue(document_id)
        while not self._stop.is_set():
            try:
                document_id = self._queue.get(timeout=DOCUMENT_WORKER_POLL_SECONDS)
            except queue.Empty:
                continue
            if document_id is None:
                continue
            with self._lock:
                self._pending.discard(document_id)
                self._active.add(document_id)
            try:
                started = time.monotonic()
                self._process(document_id)
            except Exception:
                LOGGER.exception("Document processing failed for %s", document_id)
                self.store.add_error(document_id, code="INTERNAL_ERROR",
                                     message="Document processing failed.")
                pages = self.store.get_pages(document_id, limit=100, offset=0)
                terminal = "PARTIAL" if any(page["status"] == "COMPLETED" for page in pages) else "FAILED"
                self.store.update_document(document_id, status=terminal)
                self.store.update_job(document_id, status=terminal, stage=None,
                                     error_code="INTERNAL_ERROR", finished_at=utc_now())
            finally:
                job = self.store.get_job(document_id)
                LOGGER.info(
                    "request_id=%s document_id=%s operation=document_processing timestamp=%s "
                    "duration_ms=%d status=%s error_code=%s",
                    (job or {}).get("request_id") or "-", document_id, utc_now(),
                    int((time.monotonic() - started) * 1000),
                    (job or {}).get("status", "UNKNOWN"), (job or {}).get("error_code") or "-",
                )
                with self._lock:
                    self._active.discard(document_id)
                self._queue.task_done()

    def _process(self, document_id: str) -> None:
        document = self.store.get_document(document_id)
        job = self.store.get_job(document_id)
        if not document or not job or job["status"] not in {"QUEUED", "PROCESSING"}:
            return

        attempt = job["attempts"] + 1
        self.store.update_job(document_id, status="PROCESSING", stage="VALIDATION",
                             progress_percent=None, started_at=utc_now(), increment_attempt=True)
        content = Path(document["original_path"]).read_bytes()
        deadline = time.monotonic() + DOCUMENT_MAX_PROCESSING_SECONDS
        self.store.update_job(document_id, status="PROCESSING", stage="PREPROCESSING")

        pages = []
        failures: list[tuple[int, str, str, bool]] = []
        try:
            page_iter = iter_document_pages(content, document["media_type"])
            for page_number, image in page_iter:
                if time.monotonic() >= deadline:
                    failures.append((page_number, "TIMEOUT", "Document processing exceeded its time limit.", False))
                    self.store.save_page(document_id, page_number, status="FAILED",
                                         error_code="TIMEOUT", error_message="Page processing timed out.")
                    self.store.add_error(document_id, code="TIMEOUT",
                                         message="Document processing exceeded its time limit.",
                                         page=page_number)
                    continue
                self.store.update_job(document_id, status="PROCESSING", stage="PREPROCESSING")
                try:
                    prepared = preprocess_image(image)
                    self.store.update_job(document_id, status="PROCESSING", stage="OCR")
                    result = ocr_page(prepared, document_id, page_number, preprocessed=True)
                    page = {"page": page_number, **result}
                    self.store.save_page(
                        document_id, page_number, status="COMPLETED", blocks=result["blocks"],
                        text=result["text"], width=result["width"], height=result["height"],
                    )
                    pages.append(page)
                except OCRUnavailable as exc:
                    retryable = bool(getattr(exc, "retryable", False))
                    code = "TIMEOUT" if retryable else "OCR_FAILED"
                    message = "OCR timed out for this page." if retryable else "OCR failed for this page."
                    failures.append((page_number, code, message, retryable))
                    self.store.save_page(document_id, page_number, status="FAILED",
                                         error_code=code, error_message=message)
                    self.store.add_error(document_id, code=code, message=message,
                                         page=page_number, retryable=retryable)
                total = document["page_count"] or 1
                percent = min(90, int(page_number * 90 / total))
                self.store.update_job(document_id, status="PROCESSING", stage="OCR",
                                     progress_percent=percent)
        except Exception:
            LOGGER.exception("Could not render document %s", document_id)
            self.store.add_error(document_id, code="CORRUPTED_DOCUMENT",
                                 message="The stored document could not be processed.")
            saved_pages = self.store.get_pages(document_id, limit=100, offset=0)
            terminal = "PARTIAL" if any(page["status"] == "COMPLETED" for page in saved_pages) else "FAILED"
            self.store.update_document(document_id, status=terminal)
            self.store.update_job(document_id, status=terminal, stage=None,
                                 error_code="CORRUPTED_DOCUMENT", finished_at=utc_now())
            return

        if failures and any(retryable for _, _, _, retryable in failures):
            if attempt < job["max_attempts"]:
                self.store.update_job(document_id, status="QUEUED", stage="OCR",
                                     progress_percent=None, error_code="TIMEOUT")
                with self._lock:
                    self._active.discard(document_id)
                time.sleep(DOCUMENT_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
                self.enqueue(document_id)
                return

        self.store.update_job(document_id, status="PROCESSING", stage="ENTITY_EXTRACTION",
                             progress_percent=None)
        entity_error = False
        try:
            entities = extract_entities(pages)
            self.store.update_job(document_id, status="PROCESSING", stage="INDEXING",
                                 progress_percent=None)
            self.store.replace_entities(document_id, entities)
        except Exception:
            LOGGER.exception("Entity extraction failed for %s", document_id)
            self.store.add_error(document_id, code="ENTITY_EXTRACTION_FAILED",
                                 message="Entity extraction failed.")
            entity_error = True

        page_count = document["page_count"] or len(pages) + len(failures)
        successful = len(pages)
        if successful == page_count and not entity_error:
            terminal = "COMPLETED"
            code = None
            self.store.clear_retryable_errors(document_id)
        elif successful:
            terminal = "PARTIAL"
            code = "ENTITY_EXTRACTION_FAILED" if entity_error else "OCR_PARTIAL"
            if failures:
                self.store.add_error(document_id, code="OCR_PARTIAL",
                                     message="One or more document pages could not be processed.")
        else:
            terminal = "FAILED"
            code = failures[0][1] if failures else "OCR_FAILED"
        self.store.update_document(document_id, status=terminal, page_count=page_count)
        self.store.update_job(document_id, status=terminal, stage="COMPLETED" if terminal == "COMPLETED" else None,
                             progress_percent=100 if terminal == "COMPLETED" else None,
                             error_code=code, finished_at=utc_now())


DOCUMENT_WORKER: DocumentWorker | None = None