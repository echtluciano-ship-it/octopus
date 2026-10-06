from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_counts(path: Path) -> dict[str, int]:
    tables = ("clients", "billing_operations", "rentability_operations", "source_documents")
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def create_shadow_snapshot(source: Path, output: Path, manifest: Path | None = None) -> dict[str, Any]:
    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == output:
        raise ValueError("The SHADOW snapshot cannot replace the OCTOPUS source database")
    if "shadow" not in output.name.lower():
        raise ValueError("The snapshot filename must contain 'shadow'")

    output.parent.mkdir(parents=True, exist_ok=True)
    source_before = sha256_file(source)
    temp_handle, temp_name = tempfile.mkstemp(prefix="octopus-shadow-", suffix=".db", dir=output.parent)
    os.close(temp_handle)
    temp_path = Path(temp_name)
    try:
        source_uri = source.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source_conn:
            source_conn.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(temp_path)) as destination_conn:
                source_conn.backup(destination_conn)
                integrity = destination_conn.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise sqlite3.DatabaseError(f"SHADOW snapshot integrity check failed: {integrity}")

        source_after = sha256_file(source)
        if source_before != source_after:
            raise RuntimeError("OCTOPUS source database changed while the SHADOW snapshot was created")
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)

    result = {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_path": str(source),
        "source_sha256_before": source_before,
        "source_sha256_after": source_after,
        "snapshot_path": str(output),
        "snapshot_sha256": sha256_file(output),
        "counts": database_counts(output),
        "source_unchanged": source_before == source_after,
        "integrity_check": "ok",
    }
    if manifest is not None:
        manifest = Path(manifest)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result
