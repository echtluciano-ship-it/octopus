from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image


IDENTITY_FIELDS = (
    "drive_id",
    "file_name",
    "mime_type",
    "size_bytes",
    "sha256",
    "visual_sha256",
    "detected_at",
    "folder_id",
    "folder_period",
    "operation_ref",
    "status",
    "duplicate_of",
    "duplicate_reason",
    "source_url",
    "note",
)


@dataclass(frozen=True)
class SourceDocument:
    drive_id: str
    file_name: str
    mime_type: str = ""
    size_bytes: int = 0
    sha256: str = ""
    visual_sha256: str = ""
    detected_at: str = ""
    folder_id: str = ""
    folder_period: str = ""
    operation_ref: str = ""
    status: str = "NUEVO"
    duplicate_of: str = ""
    duplicate_reason: str = ""
    source_url: str = ""
    note: str = ""


@dataclass(frozen=True)
class DuplicateEvidence:
    duplicate_of: str
    reason: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def visual_sha256(path: Path) -> str:
    """Hash exact decoded pixels, ignoring JPEG metadata and file encoding."""
    try:
        with Image.open(path) as image:
            pixels = image.convert("RGBA")
            digest = hashlib.sha256()
            digest.update(f"{pixels.width}x{pixels.height}:RGBA:".encode("ascii"))
            digest.update(pixels.tobytes())
            return digest.hexdigest()
    except (OSError, ValueError):
        return ""


def identity_for_file(
    path: Path,
    *,
    drive_id: str,
    mime_type: str = "",
    detected_at: str = "",
    folder_id: str = "",
    folder_period: str = "",
    operation_ref: str = "",
    status: str = "NUEVO",
    source_url: str = "",
    note: str = "",
) -> SourceDocument:
    return SourceDocument(
        drive_id=drive_id,
        file_name=path.name,
        mime_type=mime_type,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        visual_sha256=visual_sha256(path),
        detected_at=detected_at or utc_now(),
        folder_id=folder_id,
        folder_period=folder_period,
        operation_ref=operation_ref,
        status=status,
        source_url=source_url,
        note=note,
    )


def find_exact_duplicate(
    candidate: SourceDocument,
    existing: Iterable[SourceDocument],
) -> DuplicateEvidence | None:
    """Return only strong documentary evidence; business fields are irrelevant."""
    for document in existing:
        if candidate.drive_id and candidate.drive_id == document.drive_id:
            return DuplicateEvidence(document.drive_id, "SAME_DRIVE_ID")
    for document in existing:
        if candidate.sha256 and candidate.sha256 == document.sha256:
            return DuplicateEvidence(document.drive_id, "SAME_SHA256")
    for document in existing:
        if candidate.visual_sha256 and candidate.visual_sha256 == document.visual_sha256:
            return DuplicateEvidence(document.drive_id, "IDENTICAL_DECODED_PIXELS")
    return None


def mark_duplicate(
    candidate: SourceDocument,
    evidence: DuplicateEvidence,
) -> SourceDocument:
    values = asdict(candidate)
    values.update(
        status="DUPLICADO",
        duplicate_of=evidence.duplicate_of,
        duplicate_reason=evidence.reason,
    )
    return SourceDocument(**values)


def read_registry(path: Path) -> list[SourceDocument]:
    if not path.exists():
        return []
    valid_fields = {field.name for field in fields(SourceDocument)}
    documents = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            values = {key: raw.get(key, "") for key in valid_fields}
            try:
                values["size_bytes"] = int(values["size_bytes"] or 0)
            except ValueError:
                values["size_bytes"] = 0
            documents.append(SourceDocument(**values))
    return documents


def write_registry(path: Path, documents: Iterable[SourceDocument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(documents, key=lambda item: (item.folder_period, item.file_name, item.drive_id))
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=IDENTITY_FIELDS)
        writer.writeheader()
        for document in ordered:
            writer.writerow(asdict(document))
