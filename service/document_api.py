"""Versioned HTTP API for private, user-submitted document processing."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile

from config import (
    DOCUMENT_API_KEY,
    DOCUMENT_DB_PATH,
    DOCUMENT_MAX_ATTEMPTS,
    DOCUMENT_MAX_UPLOAD_SIZE_BYTES,
    DOCUMENT_UPLOAD_DIR,
    IS_SERVERLESS,
)
from service.document_store import DocumentStore, IdempotencyConflict, opaque_id


router = APIRouter(prefix="/api/v1")
DOCUMENT_ENABLED = not IS_SERVERLESS and bool(DOCUMENT_API_KEY)
STORE = DocumentStore(DOCUMENT_DB_PATH) if DOCUMENT_ENABLED else None
WORKER = None


def start_worker() -> None:
    global WORKER
    if STORE is None:
        return
    if WORKER is None:
        from service.document_worker import DocumentWorker
        WORKER = DocumentWorker(STORE)
    WORKER.start()


def stop_worker() -> None:
    if WORKER is not None:
        WORKER.stop()


def _raise_error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise HTTPException(status_code=status, detail={
        "code": code, "message": message, "details": details or {},
    })


def _authorize(request: Request) -> None:
    if IS_SERVERLESS:
        _raise_error(503, "DOCUMENT_API_DISABLED", "Document processing is unavailable on this deployment.")
    if not DOCUMENT_API_KEY:
        _raise_error(503, "DOCUMENT_API_DISABLED", "Document API credentials are not configured.")
    expected = f"Bearer {DOCUMENT_API_KEY}"
    supplied = request.headers.get("Authorization", "")
    if not secrets.compare_digest(supplied, expected):
        _raise_error(401, "UNAUTHORIZED", "Authentication is required.")


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in (
        "id", "filename", "media_type", "size_bytes", "status", "page_count",
        "created_at", "updated_at",
    )}


def _public_job(job: dict[str, Any]) -> dict[str, str]:
    return {"id": job["id"], "status": job["status"]}


def _require_document(document_id: str) -> dict[str, Any]:
    if STORE is None:
        _raise_error(503, "DOCUMENT_API_DISABLED", "Document processing is unavailable on this deployment.")
    document = STORE.get_document(document_id)
    if not document:
        _raise_error(404, "DOCUMENT_NOT_FOUND", "Document was not found.")
    return document


def _page_cursor(limit: int, cursor: str | None, kind: str, document_id: str):
    try:
        offset = STORE._decode_cursor(cursor)
    except ValueError:
        _raise_error(400, "INVALID_REQUEST", "Pagination cursor is invalid.")
    if kind == "pages":
        values = STORE.get_pages(document_id, limit + 1, offset)
    else:
        values = STORE.get_entities(document_id, limit + 1, offset)
    has_more = len(values) > limit
    next_cursor = STORE._encode_cursor(offset + limit) if has_more else None
    return values[:limit], {"limit": limit, "next_cursor": next_cursor}


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    _authorize(request)
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 200):
        _raise_error(400, "INVALID_REQUEST", "Idempotency-Key must contain 1 to 200 characters.")
    try:
        metadata_value = json.loads(metadata) if metadata is not None else {}
    except (ValueError, TypeError):
        _raise_error(400, "INVALID_REQUEST", "metadata must contain valid JSON.")
    if not isinstance(metadata_value, dict):
        _raise_error(400, "INVALID_REQUEST", "metadata must be a JSON object.")

    content = await file.read(DOCUMENT_MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > DOCUMENT_MAX_UPLOAD_SIZE_BYTES:
        _raise_error(413, "FILE_TOO_LARGE", "The uploaded file exceeds the configured size limit.")
    from service import document_processing
    try:
        media_type, page_count = document_processing.validate_document(content)
    except document_processing.DocumentInputError as exc:
        _raise_error(exc.status_code, exc.code, str(exc))

    filename = document_processing.safe_filename(file.filename)
    fingerprint = document_processing.file_fingerprint(content, filename, metadata_value)
    if idempotency_key:
        try:
            existing = STORE.lookup_idempotency(idempotency_key, fingerprint)
        except IdempotencyConflict:
            _raise_error(409, "INVALID_REQUEST", "Idempotency-Key was already used for a different upload.")
        if existing:
            document, job = existing
            return _upload_response(document, job, status_code=200)

    upload_dir = Path(DOCUMENT_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    final_path = upload_dir / f"{opaque_id('src')}.bin"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=upload_dir, prefix=".upload-", delete=False) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, final_path)
        document, job, created = STORE.create_document(
            filename=filename,
            media_type=media_type,
            size_bytes=len(content),
            original_path=str(final_path),
            metadata=metadata_value,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            page_count=page_count,
            request_id=getattr(request.state, "request_id", None),
            max_attempts=DOCUMENT_MAX_ATTEMPTS,
        )
        if not created:
            final_path.unlink(missing_ok=True)
            return _upload_response(document, job, status_code=200)
    except IdempotencyConflict:
        final_path.unlink(missing_ok=True)
        _raise_error(409, "INVALID_REQUEST", "Idempotency-Key was already used for a different upload.")
    except Exception:
        final_path.unlink(missing_ok=True)
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
        raise

    start_worker()
    WORKER.enqueue(document["id"])
    return _upload_response(document, job, status_code=201)


def _upload_response(document: dict[str, Any], job: dict[str, Any], status_code: int) -> Any:
    from fastapi.responses import JSONResponse
    return JSONResponse(
        {"document": _public_document(document), "job": _public_job(job)},
        status_code=status_code,
    )


@router.get("/documents/{document_id}")
def get_document(document_id: str, request: Request) -> dict[str, Any]:
    _authorize(request)
    return {"document": _public_document(_require_document(document_id))}


@router.get("/documents/{document_id}/status")
def get_document_status(document_id: str, request: Request) -> dict[str, Any]:
    _authorize(request)
    document = _require_document(document_id)
    job = STORE.get_job(document_id)
    pages = STORE.get_pages(document_id, limit=100, offset=0)
    stage = job["stage"]
    progress = {"stage": stage, "percent": job["progress_percent"]} if stage else None
    return {
        "document_id": document_id,
        "job": _public_job(job),
        "document_status": document["status"],
        "progress": progress,
        "pages": {
            "total": document["page_count"],
            "processed": sum(page["status"] in {"COMPLETED", "FAILED"} for page in pages),
            "failed": [page["page"] for page in pages if page["status"] == "FAILED"],
        },
    }


@router.get("/documents/{document_id}/pages")
def get_document_pages(
    document_id: str, request: Request,
    limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None,
) -> dict[str, Any]:
    _authorize(request)
    _require_document(document_id)
    pages, pagination = _page_cursor(limit, cursor, "pages", document_id)
    return {"document_id": document_id, "pages": pages, "pagination": pagination}


@router.get("/documents/{document_id}/entities")
def get_document_entities(
    document_id: str, request: Request,
    limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None,
) -> dict[str, Any]:
    _authorize(request)
    _require_document(document_id)
    entities, pagination = _page_cursor(limit, cursor, "entities", document_id)
    return {"document_id": document_id, "entities": entities, "pagination": pagination}


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, request: Request) -> dict[str, Any]:
    _authorize(request)
    entity = STORE.get_entity(entity_id)
    if not entity:
        _raise_error(404, "DOCUMENT_NOT_FOUND", "Entity was not found.")
    return {"entity": entity}


@router.get("/documents/{document_id}/errors")
def get_document_errors(
    document_id: str, request: Request,
    limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None,
) -> dict[str, Any]:
    _authorize(request)
    _require_document(document_id)
    try:
        offset = STORE._decode_cursor(cursor)
    except ValueError:
        _raise_error(400, "INVALID_REQUEST", "Pagination cursor is invalid.")
    errors = STORE.get_errors(document_id, limit + 1, offset)
    has_more = len(errors) > limit
    return {"document_id": document_id, "errors": errors[:limit],
            "pagination": {"limit": limit,
                           "next_cursor": STORE._encode_cursor(offset + limit) if has_more else None}}


@router.get("/search")
def search_documents(
    request: Request,
    q: str = Query(...), limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, Any]:
    _authorize(request)
    query = q.strip()
    if not query:
        _raise_error(400, "EMPTY_QUERY", "Search query cannot be empty.")
    try:
        results, next_cursor = STORE.search(query, limit, cursor)
    except ValueError:
        _raise_error(400, "INVALID_REQUEST", "Pagination cursor is invalid.")
    except sqlite3.Error:
        raise
    except Exception:
        _raise_error(500, "SEARCH_FAILED", "Document search failed.")
    return {"query": query, "results": results,
            "pagination": {"limit": limit, "next_cursor": next_cursor}}