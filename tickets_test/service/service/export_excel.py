from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, PatternFill

from service.config import settings
from service.db import connection


TRANSFER_COLUMNS = ("FECHA TICHET", "MONTO", "NRO COMPROBANTE", "NOMBRE Y APELLIDO", "CUIT", "BANCO")
DEPOSIT_COLUMNS = ("FECHA", "IMPORTE", "NUMERO DE COMPROBANTE", "BANCO")


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "sin_cuenta"


def _write(path: Path, rows: list[dict], *, deposit: bool = False, review: bool = False) -> None:
    columns = DEPOSIT_COLUMNS if deposit else TRANSFER_COLUMNS
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Hoja1"
    sheet.append(columns)
    for cell in sheet[1]:
        cell.alignment = Alignment(horizontal="center")
    for item in rows:
        if deposit:
            values = (item["ticket_date"], item["amount"], item["identifier_value"], item["origin_bank"])
        else:
            values = (
                item["ticket_date"], item["amount"], item["identifier_value"],
                item["full_name"], item["tax_id"], item["origin_bank"],
            )
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            cell.alignment = Alignment(horizontal="center")
        if review:
            for cell in sheet[sheet.max_row]:
                cell.fill = PatternFill("solid", fgColor="FFD9D9")
                cell.comment = Comment(item["review_reason"], "OCTOPUS TEST")
    widths = (12, 18.71, 34, 30.71, 24.86, 22.29)
    for index, width in enumerate(widths[: len(columns)], start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    for cell in sheet["A"][1:]:
        cell.number_format = "mm-dd-yy"
    for cell in sheet["B"][1:]:
        cell.number_format = '_-* #,##0.00_-;\\-* #,##0.00_-;_-* "-"??_-;_-@_-'
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def generate() -> dict:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT d.document_id,d.status,m.arrival_sequence,e.document_type,e.ticket_date,
                   e.amount_cents,e.identifier_value,e.full_name,e.tax_id,e.origin_bank,
                   e.destination_account_key,e.observations
            FROM ticket_documents d
            JOIN inbound_messages m USING(message_id)
            JOIN LATERAL (
                SELECT * FROM ticket_extractions x WHERE x.document_id=d.document_id
                ORDER BY attempt DESC LIMIT 1
            ) e ON true
            WHERE d.status IN ('READY_FOR_SHEET','REVIEW','WRONG_ACCOUNT_REVIEW','CHECK_REVIEW')
            ORDER BY m.arrival_sequence,d.attachment_index
            """
        ).fetchall()
    groups: dict[str, list[dict]] = defaultdict(list)
    review_rows: list[dict] = []
    deposits: list[dict] = []
    for row in rows:
        item = dict(row)
        item["amount"] = item["amount_cents"] / 100 if item["amount_cents"] is not None else None
        item["review_reason"] = item["observations"] or item["status"]
        if item["status"] != "READY_FOR_SHEET":
            review_rows.append(item)
        elif item["document_type"] == "deposit":
            deposits.append(item)
        else:
            groups[item["destination_account_key"] or "sin_cuenta"].append(item)
    output = settings.export_dir
    written: list[str] = []
    for key, items in groups.items():
        path = output / f"transferencias_{_safe(key)}.xlsx"
        _write(path, items)
        written.append(str(path))
    if deposits:
        path = output / "depositos.xlsx"
        _write(path, deposits, deposit=True)
        written.append(str(path))
    if review_rows:
        path = output / "REVIEW.xlsx"
        _write(path, review_rows, review=True)
        written.append(str(path))
    report = {"generated_at": date.today().isoformat(), "files": written, "rows": len(rows)}
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
