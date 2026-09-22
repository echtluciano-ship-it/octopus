from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_STATE = Path(__file__).resolve().parents[1] / "data" / "incremental_update_state.json"


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def document_key(document: dict) -> tuple:
    return (
        str(document.get("name") or document.get("file_name") or ""),
        str(document.get("size_bytes") or document.get("size") or ""),
        str(document.get("modified_time") or ""),
        str(document.get("folder_id") or ""),
    )


def normalize_document(document: dict) -> dict:
    drive_id = str(document.get("drive_id") or document.get("id") or "")
    if not drive_id:
        raise ValueError("Every Drive candidate requires drive_id/id")
    return {
        "drive_id": drive_id,
        "name": str(document.get("name") or document.get("file_name") or document.get("title") or ""),
        "mime_type": str(document.get("mime_type") or ""),
        "size_bytes": int(document.get("size_bytes") or document.get("size") or 0),
        "modified_time": str(document.get("modified_time") or ""),
        "folder_id": str(document.get("folder_id") or ""),
        "folder_period": str(document.get("folder_period") or ""),
        "source_type": str(document.get("source_type") or ""),
        "url": str(document.get("url") or ""),
    }


def build_plan(state: dict, snapshot: dict) -> dict:
    known = state.get("documents", {})
    new, modified, unchanged = [], [], []
    seen = set()
    for raw in snapshot.get("files", []):
        document = normalize_document(raw)
        drive_id = document["drive_id"]
        if drive_id in seen:
            continue
        seen.add(drive_id)
        previous = known.get(drive_id)
        if previous is None:
            new.append(document)
        elif document_key(document) != document_key(previous):
            modified.append({"before": previous, "after": document})
        else:
            unchanged.append(document)

    changed_sources = {}
    for name, current in snapshot.get("official_sources", {}).items():
        previous = state.get("official_sources", {}).get(name)
        if previous != current:
            changed_sources[name] = {"before": previous, "after": current}
    return {
        "scan_started_at": snapshot.get("scan_started_at"),
        "new": new,
        "modified": modified,
        "unchanged": unchanged,
        "official_sources_changed": changed_sources,
        "folders": snapshot.get("folders", {}),
        "counts": {
            "detected": len(seen),
            "new": len(new),
            "modified": len(modified),
            "unchanged": len(unchanged),
            "official_sources_changed": len(changed_sources),
        },
    }


def commit_snapshot(state: dict, snapshot: dict) -> dict:
    documents = state.setdefault("documents", {})
    for raw in snapshot.get("files", []):
        document = normalize_document(raw)
        documents[document["drive_id"]] = document
    state.setdefault("official_sources", {}).update(snapshot.get("official_sources", {}))
    state.setdefault("folders", {}).update(snapshot.get("folders", {}))
    if snapshot.get("scan_started_at"):
        state["last_successful_scan"] = snapshot["scan_started_at"]
    state["version"] = 1
    return state


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Plan or persist an incremental Google Drive scan.")
    parser.add_argument("command", choices=("plan", "commit", "init"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    snapshot = read_json(args.snapshot)
    state = read_json(args.state, {"version": 1, "documents": {}, "official_sources": {}})
    if args.command == "plan":
        result = build_plan(state, snapshot)
    else:
        if args.command == "init" and state.get("documents"):
            raise SystemExit("State is already initialized; use commit")
        result = commit_snapshot(state, snapshot)
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
