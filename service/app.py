"""Production FastAPI control plane for the resource-graph crawler."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from config import (
    ALLOWED_HOST,
    API_KEY,
    API_MAX_PAGES,
    API_MAX_WORKERS,
    BASE_URL,
    REQUEST_TIMEOUT,
    SERVICE_ENV,
    SERVICE_NAME,
    USERNAME,
)
from crawler.engine import Crawler
from crawler.fetcher import fetch
from service.jobs import STORE, CrawlJob
from service.ui import index_html

LOGGER = logging.getLogger("rgc.service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Resource Graph Crawler",
    description="Production control plane for the Visualping resource-graph crawler.",
    version="1.1.0",
)

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
        job.error = str(exc)
    job.finished_at = time.time()
    return job


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(index_html())


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
