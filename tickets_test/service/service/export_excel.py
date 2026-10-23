from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

from service.config import settings
from service.db import connection


TRANSFER_COLUMNS = ("FECHA TICHET", "MONTO", "NRO COMPROBANTE", "NOMBRE Y APELLIDO", "CUIT", "BANCO")
DEPOSIT_COLUMNS = ("FECHA", "IMPORTE", "NUMERO DE COMPROBANTE", "BANCO")
ERIKA_COLUMNS = (
    "FECHA TICKET", "MONTO", "NRO COMPROBANTE", "NOMBRE Y APELLIDO",
    "CUIT", "BANCO", "OBSERVACIONES",
)
DELIVERABLE_STATUSES = frozenset({
    "READY_FOR_SHEET",
    "REVIEW",
    "WRONG_ACCOUNT_REVIEW",
    "CHECK_REVIEW",
    "DUPLICATE_CONFIRMED",
})
CONTROL_COLUMNS = (
    "DOCUMENT ID", "ORDEN", "ESTADO", "TIPO", "FECHA", "MONTO", "TIPO IDENTIFICADOR",
    "IDENTIFICADOR", "NOMBRE Y APELLIDO", "CUIT", "BANCO", "CUENTA DESTINO",
    "RESULTADO / MOTIVO", "ARCHIVO ORIGINAL", "DRIVE ID", "LINK DRIVE",
    "EXCEL", "FILA",
)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "sin_cuenta"


def _prepare_output(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.xlsx", "manifest.json"):
        for existing in path.glob(pattern):
            existing.unlink()


def _deposit_group_key(origin_bank: str | None) -> str:
    plain = re.sub(r"[^a-z0-9]", "", (origin_bank or "").lower())
    if "macro" in plain:
        return "macro"
    if "comafi" in plain:
        return "comafi"
    return "sin_banco_confirmado"


def evaluate_delivery_gate(rows: list[dict]) -> dict:
    blockers: list[dict] = []
    if not rows:
        blockers.append({"code": "NO_DOCUMENTS", "detail": "El lote no contiene comprobantes."})
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        group_id = str(row.get("group_id") or "")
        if not group_id:
            blockers.append({
                "code": "MISSING_GROUP",
                "document_id": int(row["document_id"]),
                "detail": "El comprobante no conserva su grupo de origen.",
            })
        grouped[group_id].append(row)
    group_reports: list[dict] = []
    for group_id, group_rows in grouped.items():
        order_keys = [
            (int(row["arrival_sequence"]), int(row["attachment_index"]), int(row["document_id"]))
            for row in group_rows
        ]
        order_verified = order_keys == sorted(order_keys) and len(order_keys) == len(set(order_keys))
        if not order_verified:
            blockers.append({
                "code": "GROUP_ORDER_MISMATCH",
                "group_id": group_id,
                "detail": "Las filas del grupo no respetan el orden persistido de llegada.",
            })
        group_reports.append({
            "group_id": group_id,
            "group_name": str(group_rows[0].get("group_name") or group_id),
            "received_documents": len(group_rows),
            "order_verified": order_verified,
        })
    for row in rows:
        status = row.get("status")
        document_id = int(row["document_id"])
        if status not in DELIVERABLE_STATUSES:
            blockers.append({
                "code": "NON_DELIVERABLE_STATUS",
                "document_id": document_id,
                "status": status,
                "detail": "El comprobante todavía no tiene un estado apto para la planilla.",
            })
        elif row.get("extraction_id") is None:
            blockers.append({
                "code": "MISSING_EXTRACTION",
                "document_id": document_id,
                "status": status,
                "detail": "El comprobante no tiene una extracción recuperable.",
            })
    return {
        "delivery_ready": not blockers,
        "received_documents": len(rows),
        "accounted_documents": len(rows) - sum(
            1 for row in rows
            if row.get("status") not in DELIVERABLE_STATUSES or row.get("extraction_id") is None
        ),
        "group_count": len(grouped),
        "groups": group_reports,
        "order_verified": bool(rows) and all(item["order_verified"] for item in group_reports),
        "status_counts": dict(Counter(row.get("status") or "SIN_ESTADO" for row in rows)),
        "blockers": blockers,
    }


def _erika_observation(item: dict) -> str:
    status = item.get("status")
    reason = str(item.get("review_reason") or "").strip()
    if status == "READY_FOR_SHEET":
        return ""
    if status == "DUPLICATE_CONFIRMED":
        return f"DUPLICADO: {reason or 'comprobante duplicado confirmado.'}"
    if status == "WRONG_ACCOUNT_REVIEW":
        return f"REVIEW: {reason or 'la cuenta de destino no corresponde a una cuenta válida.'}"
    if status in {"REVIEW", "CHECK_REVIEW"}:
        return f"REVIEW: {reason or 'requiere validación manual.'}"
    return f"BLOQUEADO: estado {status or 'sin definir'}. {reason}".strip()


def _write_erika(path: Path, rows: list[dict]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tickets"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    sheet.append(ERIKA_COLUMNS)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    ready_fill = PatternFill("solid", fgColor="E6F4EA")
    review_fill = PatternFill("solid", fgColor="FCE8E6")
    blocked_fill = PatternFill("solid", fgColor="FFF2CC")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for item in rows:
        sheet.append((
            item.get("ticket_date"), item.get("amount"), item.get("identifier_value"),
            item.get("full_name"), item.get("tax_id"), item.get("origin_bank"),
            _erika_observation(item),
        ))
        row_number = sheet.max_row
        status = item.get("status")
        fill = ready_fill if status == "READY_FOR_SHEET" else (
            review_fill if status in DELIVERABLE_STATUSES else blocked_fill
        )
        for cell in sheet[row_number]:
            cell.fill = fill
            cell.font = Font(
                name="Arial", size=10,
                color="1F2937" if status == "READY_FOR_SHEET" else "A61B1B",
            )
            cell.alignment = Alignment(vertical="center")
        sheet.cell(row_number, 1).number_format = "dd/mm/yyyy"
        sheet.cell(row_number, 2).number_format = '"$"#,##0.00'
        sheet.cell(row_number, 3).number_format = "@"
        sheet.cell(row_number, 3).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.cell(row_number, 7).alignment = Alignment(vertical="center", wrap_text=True)
    widths = (14, 17, 40, 31, 19, 20, 58)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.auto_filter.ref = f"A1:G{max(sheet.max_row, 1)}"
    sheet.protection.sheet = False
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


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


def _write_control(path: Path, rows: list[dict], trace_by_document: dict[int, dict]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Control"
    sheet.append(CONTROL_COLUMNS)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    status_fill = {
        "READY_FOR_SHEET": "E2F0D9",
        "REVIEW": "FFF2CC",
        "WRONG_ACCOUNT_REVIEW": "FCE4D6",
        "CHECK_REVIEW": "FFF2CC",
        "DUPLICATE_CONFIRMED": "D9E1F2",
        "ERROR_FINAL": "F4CCCC",
        "ERROR_RETRYABLE": "F4CCCC",
    }
    for item in rows:
        trace = trace_by_document.get(item["document_id"], {})
        sheet.append((
            item["document_id"], item["arrival_sequence"], item["status"], item["document_type"],
            item["ticket_date"], item["amount"], item["identifier_type"],
            item["identifier_value"], item["full_name"], item["tax_id"],
            item["origin_bank"], item["destination_account_key"],
            item["review_reason"], item["original_filename"],
            item["source_document_id"], item["source_url"],
            trace.get("workbook"), trace.get("row"),
        ))
        row_number = sheet.max_row
        fill = status_fill.get(item["status"])
        if fill:
            sheet.cell(row_number, 3).fill = PatternFill("solid", fgColor=fill)
        if item["source_url"]:
            link_cell = sheet.cell(row_number, 16)
            link_cell.hyperlink = item["source_url"]
            link_cell.style = "Hyperlink"
    widths = (12, 9, 24, 14, 12, 16, 20, 38, 30, 18, 20, 22, 54, 44, 34, 18, 38, 8)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index) if index <= 26 else "A"].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:R{sheet.max_row}"
    sheet.sheet_view.showGridLines = False
    for cell in sheet["E"][1:]:
        cell.number_format = "dd/mm/yyyy"
    for cell in sheet["F"][1:]:
        cell.number_format = '$#,##0.00'
    for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def generate(
    source_batch: str | None = None,
    document_id: int | list[int] | None = None,
) -> dict:
    document_ids = (
        [document_id]
        if isinstance(document_id, int)
        else list(document_id or [])
    )
    if source_batch and document_ids:
        raise ValueError("source_batch and document_id are mutually exclusive")
    if source_batch:
        where_filter = "AND d.source_batch=%s"
        params = (source_batch,)
    elif document_ids:
        where_filter = "AND d.document_id = ANY(%s)"
        params = (document_ids,)
    else:
        where_filter = ""
        params = ()
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT d.document_id,d.status,d.attachment_index,d.original_filename,d.source_system,
                   d.source_document_id,d.source_url,d.source_batch,m.arrival_sequence,e.extraction_id,
                   m.group_id,m.group_name,e.document_type,e.ticket_date,
                   e.amount_cents,e.identifier_type,e.identifier_value,e.full_name,e.tax_id,e.origin_bank,
                   e.destination_account_key,
                   CASE WHEN d.status='DUPLICATE_CONFIRMED'
                        THEN COALESCE(d.duplicate_reason,'Duplicado confirmado.')
                        ELSE e.observations END AS observations
            FROM ticket_documents d
            JOIN inbound_messages m USING(message_id)
            LEFT JOIN LATERAL (
                SELECT * FROM ticket_extractions x
                WHERE x.document_id=COALESCE(d.duplicate_of,d.document_id)
                ORDER BY attempt DESC LIMIT 1
            ) e ON true
            WHERE true {where_filter}
            ORDER BY m.arrival_sequence,d.attachment_index,d.document_id
            """,
            params,
        ).fetchall()
    all_rows: list[dict] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    review_rows: list[dict] = []
    deposits: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        item["amount"] = item["amount_cents"] / 100 if item["amount_cents"] is not None else None
        item["review_reason"] = item["observations"] or item["status"]
        item["group_name"] = settings.group_name(
            str(item.get("group_id") or ""),
            str(item.get("group_name") or "") or None,
        )
        all_rows.append(item)
        if item["status"] not in DELIVERABLE_STATUSES or item["extraction_id"] is None:
            continue
        if item["status"] != "READY_FOR_SHEET":
            review_rows.append(item)
        elif item["document_type"] == "deposit":
            deposits[_deposit_group_key(item.get("origin_bank"))].append(item)
        else:
            groups[item["destination_account_key"] or "sin_cuenta"].append(item)
    if source_batch:
        output = settings.export_dir / _safe(source_batch)
    elif len(document_ids) == 1:
        output = settings.export_dir / f"documento_{document_ids[0]}"
    elif document_ids:
        output = settings.export_dir / ("documentos_" + "_".join(map(str, document_ids)))
    else:
        output = settings.export_dir
    _prepare_output(output)
    written: list[str] = []
    delivery_gate = evaluate_delivery_gate(all_rows)
    erika_groups: dict[str, list[dict]] = defaultdict(list)
    for item in all_rows:
        erika_groups[str(item.get("group_id") or "sin_grupo")].append(item)
    erika_workbooks: list[dict] = []
    erika_row_trace: list[dict] = []
    used_names: set[str] = set()
    for group_index, (group_id, group_rows) in enumerate(erika_groups.items(), start=1):
        group_name = settings.group_name(group_id, str(group_rows[0].get("group_name") or "") or None)
        base_name = _safe(group_name)
        if base_name == _safe(group_id):
            base_name = f"grupo_{group_index}"
        filename = f"TICKETS_ERIKA_{base_name}.xlsx"
        if filename in used_names:
            filename = f"TICKETS_ERIKA_{base_name}_{group_index}.xlsx"
        used_names.add(filename)
        erika_path = output / filename
        _write_erika(erika_path, group_rows)
        written.append(str(erika_path))
        erika_workbooks.append({
            "group_id": group_id,
            "group_name": group_name,
            "path": str(erika_path),
            "rows": len(group_rows),
        })
        for excel_row, item in enumerate(group_rows, start=2):
            erika_row_trace.append({
                "document_id": item["document_id"],
                "group_id": group_id,
                "arrival_sequence": item["arrival_sequence"],
                "attachment_index": item["attachment_index"],
                "workbook": erika_path.name,
                "row": excel_row,
            })
    expected_document_ids = [int(item["document_id"]) for item in all_rows]
    workbook_document_ids = [int(item["document_id"]) for item in erika_row_trace]
    delivery_gate["workbook_rows"] = len(workbook_document_ids)
    delivery_gate["workbook_reconciled"] = (
        len(workbook_document_ids) == len(expected_document_ids)
        and sorted(workbook_document_ids) == sorted(expected_document_ids)
        and len(workbook_document_ids) == len(set(workbook_document_ids))
    )
    if not delivery_gate["workbook_reconciled"]:
        delivery_gate["blockers"].append({
            "code": "WORKBOOK_RECONCILIATION_FAILED",
            "detail": "Los Excel por grupo no contienen exactamente una fila por comprobante recibido.",
        })
        delivery_gate["delivery_ready"] = False
    for key, items in groups.items():
        path = output / f"transferencias_{_safe(key)}.xlsx"
        _write(path, items)
        written.append(str(path))
    row_trace: list[dict] = []
    for key, items in groups.items():
        filename = f"transferencias_{_safe(key)}.xlsx"
        for excel_row, item in enumerate(items, start=2):
            row_trace.append({
                "document_id": item["document_id"],
                "arrival_sequence": item["arrival_sequence"],
                "original_filename": item["original_filename"],
                "source_system": item["source_system"],
                "source_document_id": item["source_document_id"],
                "source_url": item["source_url"],
                "workbook": filename,
                "row": excel_row,
            })
    for key, items in deposits.items():
        path = output / f"depositos_{_safe(key)}.xlsx"
        _write(path, items, deposit=True)
        written.append(str(path))
        for excel_row, item in enumerate(items, start=2):
            row_trace.append({
                "document_id": item["document_id"],
                "arrival_sequence": item["arrival_sequence"],
                "original_filename": item["original_filename"],
                "source_system": item["source_system"],
                "source_document_id": item["source_document_id"],
                "source_url": item["source_url"],
                "workbook": path.name,
                "row": excel_row,
            })
    if review_rows:
        path = output / "REVIEW.xlsx"
        _write(path, review_rows, review=True)
        written.append(str(path))
        for excel_row, item in enumerate(review_rows, start=2):
            row_trace.append({
                "document_id": item["document_id"],
                "arrival_sequence": item["arrival_sequence"],
                "original_filename": item["original_filename"],
                "source_system": item["source_system"],
                "source_document_id": item["source_document_id"],
                "source_url": item["source_url"],
                "workbook": path.name,
                "row": excel_row,
            })
    trace_by_document = {item["document_id"]: item for item in row_trace}
    control_path = output / "CONTROL_LOTE.xlsx"
    _write_control(control_path, all_rows, trace_by_document)
    written.append(str(control_path))
    report = {
        "generated_at": datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat(),
        "source_batch": source_batch,
        "document_id": document_ids[0] if len(document_ids) == 1 else None,
        "document_ids": document_ids,
        "files": written,
        "rows": len(all_rows),
        "status_counts": dict(Counter(item["status"] for item in all_rows)),
        "row_trace": row_trace,
        "erika_workbooks": erika_workbooks,
        "erika_row_trace": erika_row_trace,
        "delivery_gate": delivery_gate,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
