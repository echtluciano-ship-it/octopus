from __future__ import annotations

import os
import tempfile
from pathlib import Path

from service.config import settings


def _path(object_key: str) -> Path:
    root = settings.object_store_path.resolve()
    target = (root / object_key).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Object key escapes the configured store")
    return target


def ensure_ready() -> Path:
    root = settings.object_store_path
    root.mkdir(parents=True, exist_ok=True)
    probe = root / ".write-probe"
    probe.write_bytes(b"ok")
    probe.unlink()
    return root


def put_original(object_key: str, content: bytes, mime_type: str) -> None:
    del mime_type
    target = _path(object_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != content:
            raise RuntimeError(f"Immutable object collision: {object_key}")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".incoming-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != content:
                raise RuntimeError(f"Immutable object collision: {object_key}")
        target.chmod(0o440)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_original(object_key: str) -> bytes:
    return _path(object_key).read_bytes()
