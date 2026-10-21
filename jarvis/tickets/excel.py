from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import Workbook
from openpyxl.styles import Font

from jarvis.tickets.rules import DEPOSIT_COLUMNS, TRANSFER_COLUMNS


def write_editable_sheet(
    output: Path,
    rows: Iterable[Mapping[str, object]],
    *,
    document_type: str,
) -> None:
    """Write an editable workbook in the supplied arrival order."""
    columns = TRANSFER_COLUMNS if document_type == "transfer" else DEPOSIT_COLUMNS
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Hoja1"
    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    sheet.column_dimensions["A"].width = 16
    sheet.column_dimensions["B"].width = 16
    for column in range(3, len(columns) + 1):
        sheet.column_dimensions[chr(64 + column)].width = 24
    for cell in sheet["A"][1:]:
        if isinstance(cell.value, (date,)):
            cell.number_format = "DD/MM/YYYY"
    for cell in sheet["B"][1:]:
        cell.number_format = '#,##0.00'
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
