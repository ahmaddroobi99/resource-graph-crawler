"""Configuration for the resource-graph crawler.

Challenge defaults remain for local/CLI compatibility. Production deployments
should override via environment variables (see `.env.example`).
"""

from __future__ import annotations

import os
import re


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


BASE_URL = _env("RGC_BASE_URL", "http://54.214.7.161/") or "http://54.214.7.161/"
ALLOWED_HOST = _env("RGC_ALLOWED_HOST", "54.214.7.161") or "54.214.7.161"
USERNAME = _env("RGC_USERNAME", "ahmad.droobi2") or "ahmad.droobi2"
PASSWORD = _env("RGC_PASSWORD", "2dd4b97903ace571f147") or "2dd4b97903ace571f147"
PASSWORD_REGEX = r"VISUALPING\{[0-9a-fA-F]{16}\}"
COMPILED_PASSWORD_RE = re.compile(PASSWORD_REGEX)
EXAMPLE_PASSWORD = "VISUALPING{0000deadbeef0000}"

# The active search pattern. Defaults to the challenge password shape but can be
# overridden (RGC_PATTERN env var, CLI ``--pattern``, or the GUI "Search pattern"
# field) so the crawler can hunt for any regex, not just VISUALPING{...}.
PATTERN_REGEX = _env("RGC_PATTERN", PASSWORD_REGEX) or PASSWORD_REGEX
COMPILED_PATTERN_RE = re.compile(PATTERN_REGEX)
MAX_PAGES = _env_int("RGC_MAX_PAGES", 2000)
REQUEST_TIMEOUT = _env_int("RGC_REQUEST_TIMEOUT", 10)
USER_AGENT = _env("RGC_USER_AGENT", "ResourceGraphCrawler/1.1") or "ResourceGraphCrawler/1.1"

# Optional outbound proxy for geo-restricted resources.
PROXY = _env("VP_PROXY") or _env("RGC_PROXY") or None

# Serverless / public API safety caps. Full crawls belong in Docker/CLI.
API_MAX_PAGES = _env_int("RGC_API_MAX_PAGES", 12)
API_MAX_WORKERS = _env_int("RGC_API_MAX_WORKERS", 4)
API_KEY = _env("RGC_API_KEY")
SERVICE_NAME = _env("RGC_SERVICE_NAME", "resource-graph-crawler") or "resource-graph-crawler"
SERVICE_ENV = _env("RGC_ENV") or _env("VERCEL_ENV") or "development"

# Document processing is supported only by local/Docker deployments with durable storage.
DOCUMENT_DB_PATH = _env("RGC_DOCUMENT_DB_PATH", "data/documents.sqlite3") or "data/documents.sqlite3"
DOCUMENT_UPLOAD_DIR = _env("RGC_DOCUMENT_UPLOAD_DIR", "data/uploads") or "data/uploads"
DOCUMENT_API_KEY = _env("RGC_DOCUMENT_API_KEY") or API_KEY
DOCUMENT_MAX_UPLOAD_SIZE_BYTES = _env_int("RGC_DOCUMENT_MAX_UPLOAD_SIZE_BYTES", 20 * 1024 * 1024)
DOCUMENT_MAX_PAGES = _env_int("RGC_DOCUMENT_MAX_PAGES", 100)
DOCUMENT_MAX_PIXELS = _env_int("RGC_DOCUMENT_MAX_PIXELS", 50_000_000)
DOCUMENT_MAX_OCR_SECONDS = _env_int("RGC_DOCUMENT_MAX_OCR_SECONDS", 30)
DOCUMENT_MAX_PROCESSING_SECONDS = _env_int("RGC_DOCUMENT_MAX_PROCESSING_SECONDS", 600)
DOCUMENT_MAX_ATTEMPTS = _env_int("RGC_DOCUMENT_MAX_ATTEMPTS", 3)
DOCUMENT_RETRY_BASE_SECONDS = _env_int("RGC_DOCUMENT_RETRY_BASE_MILLISECONDS", 500) / 1000
DOCUMENT_WORKER_POLL_SECONDS = _env_int("RGC_DOCUMENT_WORKER_POLL_MILLISECONDS", 500) / 1000
IS_SERVERLESS = bool(os.environ.get("VERCEL"))

TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "v", "hl", "sid", "session", "gclid", "fbclid", "_", "page",
})
