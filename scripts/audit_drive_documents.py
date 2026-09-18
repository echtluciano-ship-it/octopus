from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import asdict, replace
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from source_identity import (  # noqa: E402
    SourceDocument,
    find_exact_duplicate,
    identity_for_file,
    mark_duplicate,
    read_registry,
    write_registry,
)


def load_folder_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    folders = data["folders"]["cuadros"]["pendientes"]
    return {period: folder_id for period, folder_id in folders.items() if period[:4].isdigit()}


def list_drive_files(folder_id: str, api_key: str) -> list[dict]:
    query = urllib.parse.quote(f"'{folder_id}' in parents and trashed = false")
    fields = urllib.parse.quote(
        "nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime)"
    )
    url = (
        "https://www.googleapis.com/drive/v3/files"
        f"?q={query}&pageSize=1000&orderBy=createdTime&fields={fields}&key={api_key}"
    )
    with urllib.request.urlopen(url) as response:
        return json.load(response).get("files", [])


def download_drive_file(file_id: str, api_key: str, destination: Path) -> None:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def manual_status_by_drive_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    result = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row_number, row in enumerate(csv.DictReader(fh), start=2):
            source_path = row.get("source_path", "")
            marker = "#drive_id_"
            if marker not in source_path:
                continue
            drive_id = source_path.split(marker, 1)[1].strip()
            result[drive_id] = {
                "status": row.get("status", "") or "NUEVO",
                "operation_ref": f"drive:{drive_id}",
                "note": row.get("note", ""),
            }
    return result


def canonical_priority(document: SourceDocument, created_time: str) -> tuple:
    status_order = {
        "OK": 0,
        "OK_FC_NETA": 0,
        "OK_FC_HISTORICA": 0,
        "OK_TRANSFERENCIA_1_2": 0,
        "REVISION": 1,
        "EXCLUIDO": 1,
        "NO_PROCESAR": 1,
        "NUEVO": 2,
        "DUPLICADO": 3,
    }
    return status_order.get(document.status, 2), created_time, document.drive_id


def audit(api_key: str, registry_path: Path, download_root: Path) -> list[SourceDocument]:
    folders = load_folder_map(APP_DIR / "drive_sources.json")
    manual = manual_status_by_drive_id(APP_DIR / "manual_rentability_operations.csv")
    previous = {document.drive_id: document for document in read_registry(registry_path)}
    candidates: list[tuple[SourceDocument, str]] = []

    for period, folder_id in sorted(folders.items()):
        for metadata in list_drive_files(folder_id, api_key):
            drive_id = metadata["id"]
            target = download_root / period / f"{drive_id}__{metadata['name']}"
            if not target.exists() or target.stat().st_size != int(metadata.get("size") or 0):
                download_drive_file(drive_id, api_key, target)
            known = previous.get(drive_id)
            validated = manual.get(drive_id, {})
            known_status = known.status if known else ""
            resolved_status = (
                validated.get("status", "NUEVO")
                if not known_status or known_status == "NUEVO"
                else known_status
            )
            document = identity_for_file(
                target,
                drive_id=drive_id,
                mime_type=metadata.get("mimeType", ""),
                detected_at=(known.detected_at if known else ""),
                folder_id=folder_id,
                folder_period=period,
                operation_ref=(
                    known.operation_ref
                    if known and known.operation_ref
                    else validated.get("operation_ref", "")
                ),
                status=resolved_status,
                source_url=f"https://drive.google.com/open?id={drive_id}",
                note=(known.note if known and known.note else validated.get("note", "")),
            )
            document = replace(document, file_name=metadata["name"])
            candidates.append((document, metadata.get("createdTime", "")))

    ordered = sorted(candidates, key=lambda item: canonical_priority(item[0], item[1]))
    audited: list[SourceDocument] = []
    for document, _created_time in ordered:
        evidence = find_exact_duplicate(document, audited)
        if evidence and evidence.reason != "SAME_DRIVE_ID":
            document = mark_duplicate(document, evidence)
        elif document.status == "DUPLICADO" and not document.duplicate_of:
            document = replace(
                document,
                status="REVISION",
                duplicate_reason="LEGACY_DUPLICATE_WITHOUT_IDENTITY_EVIDENCE",
            )
        audited.append(document)

    write_registry(registry_path, audited)
    return audited


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit exact identities in Pendientes Drive.")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GOOGLE_API_KEY", ""),
        help="Google Drive API key. It is never written to the registry.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=APP_DIR / "source_documents.csv",
    )
    parser.add_argument(
        "--download-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "octopus-drive-identity",
    )
    args = parser.parse_args()
    if not args.api_key:
        parser.error("Provide --api-key or GOOGLE_API_KEY.")
    audited = audit(args.api_key, args.registry, args.download_root)
    totals: dict[str, int] = {}
    for document in audited:
        totals[document.status] = totals.get(document.status, 0) + 1
    print(f"Documents audited: {len(audited)}")
    for status, count in sorted(totals.items()):
        print(f"{status}: {count}")


if __name__ == "__main__":
    main()
