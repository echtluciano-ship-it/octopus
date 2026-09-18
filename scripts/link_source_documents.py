from __future__ import annotations

import sqlite3
import sys
from dataclasses import replace
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))

from source_identity import read_registry, sha256_file, visual_sha256, write_registry  # noqa: E402


LOCAL_IMAGE_ROOTS = (
    PROJECT_ROOT / "07_rentabilidad_julio_desde_pendientes" / "imagenes_julio",
    PROJECT_ROOT / "08_agosto_2026" / "imagenes_agosto_pendientes",
    PROJECT_ROOT / "08_agosto_2026" / "imagenes_agosto_pendientes_drive",
    PROJECT_ROOT / "08_agosto_2026" / "drive_downloaded_verified",
)


def source_candidates(source_path: str) -> list[Path]:
    raw = Path(source_path)
    candidates = [raw] if raw.is_absolute() else []
    for root in LOCAL_IMAGE_ROOTS:
        candidates.append(root / raw.name)
    return [candidate for candidate in candidates if candidate.is_file()]


def main() -> None:
    registry_path = APP_DIR / "source_documents.csv"
    documents = read_registry(registry_path)
    conn = sqlite3.connect(APP_DIR / "octopus.db")
    operations = conn.execute(
        """
        SELECT operation_key, status, source_drive_id, source_path, note
        FROM rentability_operations
        """
    ).fetchall()
    by_drive_id = {}
    by_file_name: dict[str, list[tuple[str, str, str]]] = {}
    by_sha: dict[str, list[tuple[str, str, str]]] = {}
    by_visual: dict[str, list[tuple[str, str, str]]] = {}
    hashed_paths: dict[Path, tuple[str, str]] = {}

    for operation_key, status, drive_id, source_path, operation_note in operations:
        match_data = (operation_key, status, operation_note or "")
        if drive_id:
            by_drive_id.setdefault(drive_id, match_data)
        source_name = Path(source_path or "").name
        if source_name:
            by_file_name.setdefault(source_name, []).append(match_data)
        for path in source_candidates(source_path or ""):
            hashes = hashed_paths.get(path)
            if hashes is None:
                hashes = sha256_file(path), visual_sha256(path)
                hashed_paths[path] = hashes
            by_sha.setdefault(hashes[0], []).append(match_data)
            if hashes[1]:
                by_visual.setdefault(hashes[1], []).append(match_data)

    updated = []
    linked = 0
    for document in documents:
        if document.status == "DUPLICADO":
            updated.append(document)
            continue
        match = by_drive_id.get(document.drive_id)
        evidence = "Drive ID"
        if not match:
            sha_matches = list(dict.fromkeys(by_sha.get(document.sha256, [])))
            visual_matches = list(dict.fromkeys(by_visual.get(document.visual_sha256, [])))
            matches = sha_matches or visual_matches
            if len(matches) == 1:
                match = matches[0]
                evidence = "SHA-256 local" if sha_matches else "pixel hash local"
        if not match:
            name_matches = list(dict.fromkeys(by_file_name.get(document.file_name, [])))
            non_duplicates = [match for match in name_matches if match[1] != "DUPLICADO"]
            if len(non_duplicates) == 1:
                match = non_duplicates[0]
                evidence = "nombre de fuente validada"
        if match:
            operation_key, operation_status, operation_note = match
            document = replace(
                document,
                operation_ref=operation_key,
                status=operation_status,
                note=operation_note or document.note or f"Vinculado a operacion por {evidence}.",
            )
            linked += 1
        updated.append(document)

    write_registry(registry_path, updated)
    print(f"Documents linked to operations: {linked}/{len(updated)}")
    unlinked = [document for document in updated if not document.operation_ref and document.status != "DUPLICADO"]
    print(f"Documents without operation link: {len(unlinked)}")
    for document in unlinked:
        print(document.folder_period, document.drive_id, document.file_name, document.status)


if __name__ == "__main__":
    main()
