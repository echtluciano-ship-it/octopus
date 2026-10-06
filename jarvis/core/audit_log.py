from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(value: str) -> str:
    clean = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            clean = pattern.sub(lambda match: match.group(1) + "[REDACTED]", clean)
        else:
            clean = pattern.sub("[REDACTED]", clean)
    return clean


class AuditLog:
    """Append-only local record of every laboratory run and decision."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    audit_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS runs_no_update
                BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS runs_no_delete
                BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                """
            )

    def event(self, run_id: str, sequence: int, actor: str, event_type: str, payload: Any) -> None:
        safe_payload = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO events(run_id,sequence,created_at,actor,event_type,payload_json) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, sequence, utc_now(), actor, event_type, redact(safe_payload)),
            )

    def complete(
        self,
        *,
        run_id: str,
        request: str,
        intent: str,
        status: str,
        response: str,
        audit: dict[str, Any],
    ) -> None:
        safe_request = redact(request)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    utc_now(),
                    hashlib.sha256(request.encode("utf-8")).hexdigest(),
                    safe_request,
                    intent,
                    status,
                    redact(response),
                    redact(json.dumps(audit, ensure_ascii=True, sort_keys=True)),
                ),
            )
