"""Production FastAPI control plane for the resource-graph crawler."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from config import (
    ALLOWED_HOST,
    API_KEY,
    API_MAX_PAGES,
    API_MAX_WORKERS,
    BASE_URL,
    DOCUMENT_API_KEY,
    IS_SERVERLESS,
    REQUEST_TIMEOUT,
    SERVICE_ENV,
    SERVICE_NAME,
    USERNAME,
)
from crawler.engine import Crawler
from crawler.fetcher import fetch
from service.jobs import STORE, CrawlJob
from service.ui import index_html
from service.document_ui import document_html
from service import document_api

LOGGER = logging.getLogger("rgc.service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app):
    if not IS_SERVERLESS and DOCUMENT_API_KEY:
        document_api.start_worker()
    try:
        yield
    finally:
        if not IS_SERVERLESS and DOCUMENT_API_KEY:
            document_api.stop_worker()


app = FastAPI(
    title="Resource Graph Crawler",
    description="Production control plane for the Visualping resource-graph crawler.",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(document_api.router)


def _error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


@app.middleware("http")
async def request_logging(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_id) else uuid.uuid4().hex
    request.state.request_id = request_id
    segments = request.url.path.strip("/").split("/")
    document_id = segments[3] if len(segments) > 3 and segments[:3] == ["api", "v1", "documents"] else "-"
    started = time.monotonic()
    response = await call_next(request)
    status_code = response.status_code
    error_codes = {400: "INVALID_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
                   404: "NOT_FOUND", 409: "INVALID_REQUEST", 413: "FILE_TOO_LARGE",
                   415: "UNSUPPORTED_FILE_TYPE", 422: "INVALID_REQUEST",
                   500: "INTERNAL_ERROR", 503: "SERVICE_UNAVAILABLE", 504: "TIMEOUT"}
    error_code = response.headers.get(
        "X-Error-Code", error_codes.get(status_code, "-") if status_code >= 400 else "-"
    )
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    LOGGER.info(
        "request_id=%s document_id=%s operation=%s timestamp=%s duration_ms=%d status=%d error_code=%s",
        request_id, document_id, f"{request.method} {request.url.path}", timestamp,
        int((time.monotonic() - started) * 1000), status_code, error_code,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and {"code", "message"}.issubset(detail):
        body = _error_body(str(detail["code"]), str(detail["message"]), detail.get("details"))
    else:
        codes = {
            400: "INVALID_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
            404: "NOT_FOUND", 413: "FILE_TOO_LARGE", 415: "UNSUPPORTED_FILE_TYPE",
            422: "INVALID_REQUEST", 500: "INTERNAL_ERROR", 503: "SERVICE_UNAVAILABLE",
            504: "TIMEOUT",
        }
        body = _error_body(codes.get(exc.status_code, "INTERNAL_ERROR"), str(detail))
    headers = dict(exc.headers or {})
    headers["X-Error-Code"] = body["error"]["code"]
    return JSONResponse(body, status_code=exc.status_code, headers=headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(_error_body("INVALID_REQUEST", "Request parameters are invalid."),
                        status_code=400, headers={"X-Error-Code": "INVALID_REQUEST"})


@app.exception_handler(sqlite3.Error)
async def handle_database_error(_request: Request, exc: sqlite3.Error) -> JSONResponse:
    LOGGER.error("Document database operation failed: %s", type(exc).__name__)
    return JSONResponse(_error_body("DATABASE_ERROR", "The document database operation failed."),
                        status_code=500, headers={"X-Error-Code": "DATABASE_ERROR"})


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled API error", exc_info=exc)
    return JSONResponse(_error_body("INTERNAL_ERROR", "An unexpected server error occurred."),
                        status_code=500, headers={"X-Error-Code": "INTERNAL_ERROR"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    max_pages: int = Field(default=8, ge=1, le=2000)
    workers: int = Field(default=2, ge=1, le=16)


def _require_api_key(authorization: str | None) -> None:
    if not API_KEY:
        return
    expected = f"Bearer {API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


def _probe_target() -> dict[str, Any]:
    started = time.monotonic()
    response = fetch(BASE_URL)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if response is None:
        return {
            "ok": False,
            "host": ALLOWED_HOST,
            "base_url": BASE_URL,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "detail": "Target did not return a response (timeout, DNS, or connection refused).",
        }
    snippet = ""
    try:
        snippet = (response.text or "")[:240]
    except Exception:
        snippet = ""
    return {
        "ok": 200 <= response.status_code < 400,
        "host": ALLOWED_HOST,
        "base_url": BASE_URL,
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "content_type": response.headers.get("Content-Type"),
        "bytes": len(response.content or b""),
        "snippet": snippet,
    }


def _run_crawl(job: CrawlJob) -> CrawlJob:
    job.status = "running"
    job.started_at = time.time()
    probe = _probe_target()
    job.target_reachable = bool(probe.get("ok"))
    if not job.target_reachable:
        job.status = "failed"
        job.finished_at = time.time()
        job.error = probe.get("detail") or "Challenge target is unreachable."
        job.stats = {"probe": probe}
        return job
    try:
        crawler = Crawler(verbose=False)
        crawler.run(max_pages=job.max_pages, workers=job.workers)
        job.passwords = crawler.results.get_all()
        job.credential_leaks = sorted(crawler.credential_leaks)
        job.stats = crawler.get_stats()
        job.stats["probe"] = probe
        job.status = "succeeded"
    except Exception as exc:
        LOGGER.exception("Crawl job %s failed", job.id)
        job.status = "failed"
        job.error = "Crawl job failed unexpectedly."
    job.finished_at = time.time()
    return job


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    page = index_html()
    link = '<a href="/documents" style="position:fixed;right:18px;bottom:18px;padding:12px 16px;background:#3ee0b0;color:#071018;border-radius:5px;font:600 14px sans-serif;text-decoration:none">Document Workbench</a>'
    return HTMLResponse(page.replace("</body>", f"{link}</body>", 1))


@app.get("/documents", response_class=HTMLResponse)
def documents_ui() -> HTMLResponse:
    return HTMLResponse(document_html())


@app.get("/openapi.yaml")
def openapi_yaml():
    from fastapi.responses import FileResponse
    from pathlib import Path
    return FileResponse(Path(__file__).resolve().parent.parent / "openapi.yaml",
                        media_type="application/yaml", filename="openapi.yaml")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "environment": SERVICE_ENV,
        "target_host": ALLOWED_HOST,
        "auth_configured": bool(USERNAME),
        "api_key_required": bool(API_KEY),
    }


@app.get("/ready")
def ready() -> JSONResponse:
    probe = _probe_target()
    payload = {"status": "ready" if probe["ok"] else "degraded", "probe": probe}
    return JSONResponse(payload, status_code=200 if probe["ok"] else 503)


@app.get("/api/v1/status")
def status() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "environment": SERVICE_ENV,
        "target": {
            "host": ALLOWED_HOST,
            "base_url": BASE_URL,
            "timeout_seconds": REQUEST_TIMEOUT,
        },
        "limits": {
            "api_max_pages": API_MAX_PAGES,
            "api_max_workers": API_MAX_WORKERS,
        },
        "jobs": [job.to_dict() for job in STORE.list()],
    }


@app.get("/api/v1/probe")
def probe() -> dict[str, Any]:
    return _probe_target()


@app.post("/api/v1/crawl")
def crawl(
    payload: CrawlRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_api_key(authorization)
    max_pages = min(payload.max_pages, API_MAX_PAGES)
    workers = min(payload.workers, API_MAX_WORKERS)
    job = STORE.create(max_pages=max_pages, workers=workers)
    _run_crawl(job)
    return job.to_dict()


@app.get("/api/v1/jobs")
def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return {"jobs": [job.to_dict() for job in STORE.list(limit=limit)]}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job.to_dict()
