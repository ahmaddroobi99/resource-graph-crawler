"""In-process job store for crawl runs.

This is intentionally process-local. On Vercel each invocation is isolated, so
the public API runs crawls synchronously and returns the finished job. Docker
and local uvicorn keep the store for the life of the process.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrawlJob:
    id: str
    status: str
    created_at: float
    max_pages: int
    workers: int
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    passwords: list[str] = field(default_factory=list)
    credential_leaks: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    target_reachable: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        elapsed = None
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.time()
            elapsed = round(end - self.started_at, 3)
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": elapsed,
            "max_pages": self.max_pages,
            "workers": self.workers,
            "error": self.error,
            "passwords": self.passwords,
            "credential_leaks": self.credential_leaks,
            "stats": self.stats,
            "target_reachable": self.target_reachable,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, CrawlJob] = {}
        self._lock = threading.Lock()

    def create(self, max_pages: int, workers: int) -> CrawlJob:
        job = CrawlJob(
            id=str(uuid.uuid4()),
            status="queued",
            created_at=time.time(),
            max_pages=max_pages,
            workers=workers,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> CrawlJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[CrawlJob]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]


STORE = JobStore()
