"""SQLite persistence for uploaded documents and asynchronous processing jobs."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different upload."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def opaque_id(kind: str) -> str:
    return f"{kind}_{uuid.uuid4().hex}"


class DocumentStore:
    """Persist document metadata, job state, page OCR, entities, and errors."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    status TEXT NOT NULL,
                    page_count INTEGER,
                    original_path TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    request_fingerprint TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_jobs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
                    request_id TEXT,
                    status TEXT NOT NULL,
                    stage TEXT,
                    progress_percent INTEGER,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS document_jobs_status_idx
                    ON document_jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS document_pages (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    text TEXT NOT NULL DEFAULT '',
                    width INTEGER,
                    height INTEGER,
                    blocks_json TEXT NOT NULL DEFAULT '[]',
                    error_code TEXT,
                    error_message TEXT,
                    PRIMARY KEY (document_id, page_number)
                );
                CREATE TABLE IF NOT EXISTS document_entities (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    type TEXT NOT NULL,
                    confidence REAL,
                    evidence_json TEXT
                );
                CREATE INDEX IF NOT EXISTS document_entities_document_idx
                    ON document_entities(document_id);
                CREATE TABLE IF NOT EXISTS document_errors (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    page_number INTEGER,
                    retryable INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(
                    document_id UNINDEXED,
                    page_number UNINDEXED,
                    entity_id UNINDEXED,
                    record_type UNINDEXED,
                    text,
                    tokenize='unicode61'
                );
                """
            )
            job_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_jobs)")}
            if "request_id" not in job_columns:
                connection.execute("ALTER TABLE document_jobs ADD COLUMN request_id TEXT")

    def create_document(
        self,
        *,
        filename: str,
        media_type: str,
        size_bytes: int,
        original_path: str,
        metadata: dict[str, Any],
        fingerprint: str,
        idempotency_key: str | None,
        page_count: int | None = None,
        request_id: str | None = None,
        max_attempts: int = 3,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """Create a document/job pair, or return the matching idempotent pair."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM documents WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    if existing["request_fingerprint"] != fingerprint:
                        raise IdempotencyConflict("Idempotency key was already used for another upload.")
                    existing_job = connection.execute(
                        "SELECT * FROM document_jobs WHERE document_id = ?", (existing["id"],)
                    ).fetchone()
                    return self._document_from_row(existing), self._job_from_row(existing_job), False

            now = utc_now()
            document_id = opaque_id("doc")
            job_id = opaque_id("job")
            connection.execute(
                "INSERT INTO documents (id, filename, media_type, size_bytes, status, "
                "page_count, original_path, metadata_json, idempotency_key, request_fingerprint, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, 'PROCESSING', ?, ?, ?, ?, ?, ?, ?)",
                (document_id, filename, media_type, size_bytes, page_count, original_path,
                 json.dumps(metadata, separators=(",", ":")), idempotency_key,
                 fingerprint, now, now),
            )
            connection.execute(
                "INSERT INTO document_jobs (id, document_id, request_id, status, stage, max_attempts, "
                "created_at, updated_at) VALUES (?, ?, ?, 'QUEUED', 'VALIDATION', ?, ?, ?)",
                (job_id, document_id, request_id, max_attempts, now, now),
            )
            document = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            job = connection.execute("SELECT * FROM document_jobs WHERE id = ?", (job_id,)).fetchone()
            return self._document_from_row(document), self._job_from_row(job), True

    def lookup_idempotency(
        self, idempotency_key: str, fingerprint: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self._connection() as connection:
            document = connection.execute(
                "SELECT * FROM documents WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if not document:
                return None
            if document["request_fingerprint"] != fingerprint:
                raise IdempotencyConflict("Idempotency key was already used for another upload.")
            job = connection.execute(
                "SELECT * FROM document_jobs WHERE document_id = ?", (document["id"],)
            ).fetchone()
            return self._document_from_row(document), self._job_from_row(job)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            return self._document_from_row(row) if row else None

    def get_job(self, document_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM document_jobs WHERE document_id = ?", (document_id,)
            ).fetchone()
            return self._job_from_row(row) if row else None

    def recover_jobs(self) -> list[str]:
        """Requeue accepted work after process restart and return its document IDs."""
        now = utc_now()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_id, attempts, max_attempts FROM document_jobs "
                "WHERE status IN ('QUEUED', 'PROCESSING')"
            ).fetchall()
            retry_ids = []
            for row in rows:
                document_id = row["document_id"]
                if row["attempts"] >= row["max_attempts"]:
                    connection.execute(
                        "UPDATE document_jobs SET status = 'FAILED', stage = NULL, "
                        "progress_percent = NULL, error_code = 'TIMEOUT', updated_at = ?, "
                        "finished_at = ? WHERE document_id = ?", (now, now, document_id)
                    )
                    connection.execute(
                        "UPDATE documents SET status = 'FAILED', updated_at = ? WHERE id = ?",
                        (now, document_id),
                    )
                    connection.execute(
                        "INSERT INTO document_errors (id, document_id, code, message, retryable) "
                        "SELECT ?, ?, 'TIMEOUT', 'Processing stopped before completion.', 0 "
                        "WHERE NOT EXISTS (SELECT 1 FROM document_errors WHERE document_id = ? "
                        "AND code = 'TIMEOUT' AND message = 'Processing stopped before completion.')",
                        (opaque_id("err"), document_id, document_id),
                    )
                else:
                    connection.execute(
                        "UPDATE document_jobs SET status = 'QUEUED', stage = 'VALIDATION', "
                        "progress_percent = NULL, updated_at = ?, started_at = NULL "
                        "WHERE document_id = ?", (now, document_id)
                    )
                    connection.execute(
                        "UPDATE documents SET status = 'PROCESSING', updated_at = ? WHERE id = ?",
                        (now, document_id),
                    )
                    retry_ids.append(document_id)
            return retry_ids

    def queued_documents(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_id FROM document_jobs WHERE status = 'QUEUED' ORDER BY created_at"
            ).fetchall()
            return [row["document_id"] for row in rows]

    def update_job(
        self, document_id: str, *, status: str, stage: str | None = None,
        progress_percent: int | None = None, error_code: str | None = None,
        started_at: str | None = None, finished_at: str | None = None,
        increment_attempt: bool = False,
    ) -> None:
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                "UPDATE document_jobs SET status = ?, stage = ?, progress_percent = ?, "
                "error_code = ?, updated_at = ?, started_at = COALESCE(?, started_at), "
                "finished_at = ?, attempts = attempts + ? WHERE document_id = ?",
                (status, stage, progress_percent, error_code, now, started_at,
                 finished_at, int(increment_attempt), document_id),
            )

    def update_document(self, document_id: str, *, status: str, page_count: int | None = None) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE documents SET status = ?, page_count = COALESCE(?, page_count), "
                "updated_at = ? WHERE id = ?",
                (status, page_count, utc_now(), document_id),
            )

    def save_page(
        self, document_id: str, page_number: int, *, status: str,
        blocks: list[dict[str, Any]] | None = None, text: str = "",
        error_code: str | None = None, error_message: str | None = None,
        width: int | None = None, height: int | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO document_pages (document_id, page_number, status, text, width, height, "
                "blocks_json, error_code, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(document_id, page_number) DO UPDATE SET status=excluded.status, "
                "text=excluded.text, width=excluded.width, height=excluded.height, "
                "blocks_json=excluded.blocks_json, "
                "error_code=excluded.error_code, error_message=excluded.error_message",
                (document_id, page_number, status, text, width, height,
                 json.dumps(blocks or [], separators=(",", ":")), error_code, error_message),
            )
            connection.execute(
                "DELETE FROM document_search WHERE document_id = ? AND page_number = ? "
                "AND record_type = 'TEXT'", (document_id, str(page_number))
            )
            if status == "COMPLETED" and text:
                connection.execute(
                    "INSERT INTO document_search (document_id, page_number, entity_id, record_type, text) "
                    "VALUES (?, ?, '', 'TEXT', ?)", (document_id, str(page_number), text)
                )

    def replace_entities(self, document_id: str, entities: list[dict[str, Any]]) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM document_entities WHERE document_id = ?", (document_id,))
            connection.execute(
                "DELETE FROM document_search WHERE document_id = ? AND record_type = 'ENTITY'",
                (document_id,),
            )
            for entity in entities:
                entity_id = entity.get("id") or opaque_id("ent")
                evidence = entity.get("evidence")
                connection.execute(
                    "INSERT INTO document_entities (id, document_id, text, type, confidence, "
                    "evidence_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (entity_id, document_id, entity["text"],
                     entity["type"], entity.get("confidence"),
                     json.dumps(evidence, separators=(",", ":"))),
                )
                if evidence and evidence.get("page"):
                    connection.execute(
                        "INSERT INTO document_search (document_id, page_number, entity_id, record_type, text) "
                        "VALUES (?, ?, ?, 'ENTITY', ?)",
                        (document_id, str(evidence["page"]), entity_id, entity["text"]),
                    )

    def add_error(
        self, document_id: str, *, code: str, message: str,
        page: int | None = None, retryable: bool = False,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO document_errors (id, document_id, code, message, page_number, retryable) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (opaque_id("err"), document_id, code, message, page, int(retryable)),
            )

    def clear_retryable_errors(self, document_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM document_errors WHERE document_id = ? AND retryable = 1",
                (document_id,),
            )

    def get_pages(self, document_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM document_pages WHERE document_id = ? ORDER BY page_number "
                "LIMIT ? OFFSET ?", (document_id, limit, offset)
            ).fetchall()
            return [{
                "page": row["page_number"], "status": row["status"],
                "text": row["text"], "width": row["width"], "height": row["height"],
                "blocks": json.loads(row["blocks_json"]),
                "error": ({"code": row["error_code"], "message": row["error_message"]}
                          if row["error_code"] else None),
            } for row in rows]

    def get_entities(self, document_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM document_entities WHERE document_id = ? ORDER BY id LIMIT ? OFFSET ?",
                (document_id, limit, offset)
            ).fetchall()
            return [self._entity_from_row(row) for row in rows]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM document_entities WHERE id = ?", (entity_id,)
            ).fetchone()
            return self._entity_from_row(row) if row else None

    def get_errors(self, document_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT code, message, page_number, retryable FROM document_errors "
                "WHERE document_id = ? ORDER BY rowid LIMIT ? OFFSET ?",
                (document_id, limit, offset)
            ).fetchall()
            return [{"code": row["code"], "message": row["message"],
                     "page": row["page_number"], "retryable": bool(row["retryable"])}
                    for row in rows]

    def search(
        self, query: str, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        offset = self._decode_cursor(cursor)
        terms = re.findall(r"\w+", query, re.UNICODE)
        if not terms:
            return [], None
        match_query = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT d.id, d.filename FROM document_search "
                "JOIN documents d ON d.id = document_search.document_id "
                "WHERE document_search MATCH ? AND d.status IN ('COMPLETED', 'PARTIAL') "
                "ORDER BY d.created_at DESC, d.id LIMIT ? OFFSET ?",
                (match_query, limit + 1, offset),
            ).fetchall()
            has_more = len(rows) > limit
            results = []
            for row in rows[:limit]:
                matches = []
                match_rows = connection.execute(
                    "SELECT page_number, entity_id, record_type, text FROM document_search "
                    "WHERE document_search MATCH ? AND document_id = ? "
                    "ORDER BY CAST(page_number AS INTEGER), record_type",
                    (match_query, row["id"]),
                ).fetchall()
                for indexed in match_rows:
                    if indexed["record_type"] == "ENTITY":
                        entity = connection.execute(
                            "SELECT type, evidence_json FROM document_entities WHERE id = ?",
                            (indexed["entity_id"],),
                        ).fetchone()
                        evidence = json.loads(entity["evidence_json"]) if entity and entity["evidence_json"] else None
                        matches.append({"type": "ENTITY", "text": indexed["text"],
                                        "entity_type": entity["type"] if entity else None,
                                        "page": evidence.get("page") if evidence else None,
                                        "bbox": evidence.get("bbox") if evidence else None})
                    else:
                        page = connection.execute(
                            "SELECT text, blocks_json FROM document_pages "
                            "WHERE document_id = ? AND page_number = ?",
                            (row["id"], int(indexed["page_number"])),
                        ).fetchone()
                        page_blocks = json.loads(page["blocks_json"]) if page else []
                        matching_blocks = [
                            block for block in page_blocks
                            if all(term.casefold() in block["text"].casefold() for term in terms)
                        ]
                        if matching_blocks:
                            matches.extend({"type": "TEXT", "text": block["text"],
                                            "page": int(indexed["page_number"]), "bbox": block.get("bbox")}
                                           for block in matching_blocks)
                        else:
                            matches.append({"type": "TEXT", "text": indexed["text"][:500],
                                            "page": int(indexed["page_number"]), "bbox": None})
                results.append({"document_id": row["id"], "filename": row["filename"],
                                "matches": matches})
        next_cursor = self._encode_cursor(offset + limit) if has_more else None
        return results, next_cursor

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            value = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            offset = int(value)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("Invalid pagination cursor.") from None
        if offset < 0 or offset > 2_147_483_647:
            raise ValueError("Invalid pagination cursor.")
        return offset

    @staticmethod
    def _entity_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "document_id": row["document_id"],
                "text": row["text"], "type": row["type"],
                "confidence": row["confidence"],
                "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else None}

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "filename": row["filename"],
            "media_type": row["media_type"], "size_bytes": row["size_bytes"],
            "status": row["status"], "page_count": row["page_count"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "original_path": row["original_path"],
        }

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "document_id": row["document_id"],
            "request_id": row["request_id"],
            "status": row["status"], "stage": row["stage"],
            "progress_percent": row["progress_percent"], "attempts": row["attempts"],
            "max_attempts": row["max_attempts"], "error_code": row["error_code"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "started_at": row["started_at"], "finished_at": row["finished_at"],
        }