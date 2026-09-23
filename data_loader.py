from __future__ import annotations

import re
import sqlite3
import unicodedata
import csv
import hashlib
import os
import tempfile
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app_octopus"
DB_PATH = APP_DIR / "octopus.db"

FACTURACION_CANDIDATES = [
    APP_DIR / "data" / "FACTURACION OCTOPUS.xlsx",
    ROOT / "00_fuentes_originales" / "facturacion_octopus_historica.xlsx",
    ROOT / "outputs" / "alias_aplicado_2026_08_11" / "FACTURACION_OCTOPUS_2026_08_11.xlsx",
    Path(r"C:\Users\Luciano\Downloads\FACTURACION OCTOPUS.xlsx"),
    Path(r"C:\Users\Luciano\Downloads\FACTURACION OCTOPUS opa.xlsx"),
]

RENTABILIDAD_FILES = [
    ROOT / "07_rentabilidad_julio_desde_pendientes" / "Rentabilidad - Julio 2026 - Pendientes Octopus.xlsx",
    ROOT / "08_agosto_2026" / "Rentabilidad_Clientes_Agosto_2026.xlsx",
]

TRANSFER_1_2_BY_SOURCE = {
    "00003753-PHOTO-2026-07-01-13-00-18.jpg": 27205436.0,
    "00003755-PHOTO-2026-07-01-14-31-36.jpg": 20703695.0,
    "00003797-PHOTO-2026-07-03-12-49-44.jpg": 47212990.0,
    "00003852-PHOTO-2026-07-08-11-46-09.jpg": 47204733.0,
    "00003901-PHOTO-2026-07-14-11-35-06.jpg": 64670937.0,
    "00004079-PHOTO-2026-07-26-20-13-53.jpg": 129828122.0,
}

MANUAL_RENTABILITY_FILE = APP_DIR / "manual_rentability_operations.csv"
CLIENT_ALIASES_FILE = APP_DIR / "client_aliases.csv"
SOURCE_DOCUMENTS_FILE = APP_DIR / "source_documents.csv"

CURRENT_MONTH = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%Y-%m")
ALIAS_BY_KEY: dict[str, str] = {}


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\u00a0", " ").strip())


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_name(value: str) -> str:
    text = strip_accents(clean_text(value)).upper()
    text = text.replace("SOCIEDAD ANONIMA", " SA ")
    text = text.replace("SOCIEDAD DE RESPONSABILIDAD LIMITADA", " SRL ")
    text = re.sub(r"\bS\s*\.?\s*A\s*\.?\b", " SA ", text)
    text = re.sub(r"\bS\s*\.?\s*R\s*\.?\s*L\s*\.?\b", " SRL ", text)
    text = re.sub(r"\bS\s*\.?\s*A\s*\.?\s*S\s*\.?\b", " SAS ", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(SA|SRL|SAS|SC|SCA|SCS)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def load_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    if not CLIENT_ALIASES_FILE.exists():
        return aliases
    with CLIENT_ALIASES_FILE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            decision = clean_text(row.get("decision")).lower()
            if "unificar" not in decision:
                continue
            alias_name = clean_text(row.get("alias_name"))
            official_name = clean_text(row.get("official_name"))
            alias_key = normalize_name(alias_name)
            if alias_key and official_name:
                aliases[alias_key] = official_name
    return aliases


def canonical_client_name(value: str) -> str:
    original = clean_text(value)
    if not original:
        return ""
    return ALIAS_BY_KEY.get(normalize_name(original), original)


def normalize_channel(value: str) -> str:
    text = strip_accents(clean_text(value)).upper()
    if "HYF" in text or "H Y F" in text:
        return "HYF"
    if "ESPORA" in text:
        return "Espora"
    if "FARO" in text:
        return "Faro 18"
    if "BARBY" in text:
        return "El Barby"
    if "FARMACIA JUJUY" in text:
        return "Farmacia Jujuy"
    return clean_text(value) or "Pendiente"


def header_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", strip_accents(clean_text(value)).upper())


def parse_decimal(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    text = clean_text(value).replace("$", "").replace(" ", "")
    if not text or text.lower().startswith("revisi"):
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    spanish_months = {
        "ENE": 1,
        "FEB": 2,
        "MAR": 3,
        "ABR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SEP": 9,
        "SET": 9,
        "OCT": 10,
        "NOV": 11,
        "DIC": 12,
    }
    match = re.fullmatch(r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,10})[-/](\d{2,4})", text)
    if match:
        month_token = strip_accents(match.group(1)).upper()
        month_aliases = {
            **spanish_months,
            "ENERO": 1,
            "FEBRERO": 2,
            "MARZO": 3,
            "ABRIL": 4,
            "MAYO": 5,
            "JUNIO": 6,
            "JULIO": 7,
            "AGOS": 8,
            "AGOSTO": 8,
            "SEPT": 9,
            "SEPTIEMBRE": 9,
            "SETIEMBRE": 9,
            "OCTUBRE": 10,
            "NOVIEMBRE": 11,
            "DICIEMBRE": 12,
        }
        month = month_aliases.get(month_token)
        year = int(match.group(2))
        if month:
            if year < 100:
                year += 2000
            return date(year, month, 1)
    return None


def month_diff(from_month: str, to_month: str = CURRENT_MONTH) -> int:
    y1, m1 = map(int, from_month.split("-"))
    y2, m2 = map(int, to_month.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


def parse_cliente_canal(value: str) -> tuple[str, str]:
    text = clean_text(value)
    text = re.sub(r"\s*/\s*Fact.*$", "", text, flags=re.IGNORECASE)
    parts = [part.strip() for part in re.split(r"\s+-\s+|(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", text) if part.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:-1]), normalize_channel(parts[-1])
    return text, "Pendiente"


def extract_invoice_numbers(value: str) -> list[str]:
    text = clean_text(value)
    match = re.search(r"FACT\s*([0-9][0-9\s,./-]*)", text, flags=re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)
    if "-" in raw:
        nums = re.findall(r"\d+", raw)
        if len(nums) >= 2:
            start, end = int(nums[0]), int(nums[-1])
            if end >= start and end - start <= 20:
                return [str(n) for n in range(start, end + 1)]
    return [n.lstrip("0") or "0" for n in re.findall(r"\d+", raw)]


def extract_drive_id(value: str) -> str:
    match = re.search(r"#drive_id_([A-Za-z0-9_-]+)", clean_text(value))
    return match.group(1) if match else ""


def make_operation_key(
    source_path: str,
    operation_date: date | None,
    client_key: str,
    channel: str,
    billed_amount: float | None,
    octopus_profit: float | None,
    fragment_key: str | None = None,
) -> str:
    drive_id = extract_drive_id(source_path)
    if drive_id:
        suffix = f":fragment:{clean_text(fragment_key)}" if fragment_key else ""
        return f"drive:{drive_id}{suffix}"
    payload = "|".join(
        [
            clean_text(source_path),
            operation_date.isoformat() if operation_date else "",
            client_key,
            channel,
            "" if billed_amount is None else f"{billed_amount:.4f}",
            "" if octopus_profit is None else f"{octopus_profit:.4f}",
        ]
    )
    return f"legacy:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def pick_facturacion_file() -> Path:
    for path in FACTURACION_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No encontré Excel histórico de facturación.")


def lookup_billed_from_history(
    conn: sqlite3.Connection,
    original_client_name: str,
    channel: str,
    cliente_canal: str,
) -> tuple[float | None, str | None]:
    invoice_numbers = extract_invoice_numbers(cliente_canal)
    if not invoice_numbers:
        return None, "No se ve Facturado y no hay número de factura para cruzar con Facturación Histórica."

    invoice_keys = [("00000000" + number)[-8:] for number in invoice_numbers]
    client_key = normalize_name(canonical_client_name(original_client_name))
    resolved = []
    missing = []

    for invoice_key in invoice_keys:
        matches = conn.execute(
            """
            SELECT net_amount, invoice_number
            FROM billing_operations
            WHERE client_key = ?
              AND channel = ?
              AND substr(replace(replace(replace(invoice_number, ' ', ''), '-', ''), '/', ''), -8) = ?
              AND net_amount IS NOT NULL
              AND net_amount > 0
            """,
            (client_key, channel, invoice_key),
        ).fetchall()
        if len(matches) == 1:
            resolved.append(matches[0])
        elif len(matches) == 0:
            missing.append(invoice_key.lstrip("0") or "0")
        else:
            return None, (
                "No se ve Facturado y la factura "
                f"{invoice_key.lstrip('0') or '0'} tiene más de una coincidencia en Facturación Histórica."
            )

    if missing:
        return None, (
            "No se ve Facturado; no encontré en Facturación Histórica la factura "
            f"{', '.join(missing)}."
        )

    total = sum(float(row[0]) for row in resolved)
    invoices = ", ".join(clean_text(row[1]) for row in resolved)
    return total, f"Facturado recuperado de Facturación Histórica por factura: {invoices}."


def lookup_transfer_1_2(source_file: str, ganancia: float | None) -> tuple[float | None, str | None]:
    transfer_amount = TRANSFER_1_2_BY_SOURCE.get(Path(source_file).name)
    if transfer_amount is None or ganancia is None:
        return None, None
    expected_profit = round(transfer_amount * 0.012)
    if abs(expected_profit - float(ganancia)) <= 1:
        return (
            transfer_amount,
            "Modalidad TRANSFERENCIA_1_2: costos pagados previamente; "
            "base calculada desde ECHEQ/transferencia visible al 1,20%.",
        )
    return None, (
        "Posible modalidad TRANSFERENCIA_1_2, pero la ganancia no coincide "
        "con el 1,20% del importe transferido."
    )


def connect() -> sqlite3.Connection:
    APP_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS monthly_metrics;
        DROP TABLE IF EXISTS source_documents;
        DROP TABLE IF EXISTS rentability_operations;
        DROP TABLE IF EXISTS billing_operations;
        DROP TABLE IF EXISTS data_quality_issues;
        DROP TABLE IF EXISTS client_aliases;
        DROP TABLE IF EXISTS clients;

        CREATE TABLE clients (
            client_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            first_operation TEXT,
            last_operation TEXT,
            last_month TEXT,
            months_without_activity INTEGER,
            status TEXT NOT NULL
        );

        CREATE TABLE client_aliases (
            alias_key TEXT PRIMARY KEY,
            alias_name TEXT NOT NULL,
            official_key TEXT NOT NULL,
            official_name TEXT NOT NULL,
            decision TEXT NOT NULL,
            source_group TEXT,
            source_sheet TEXT
        );

        CREATE TABLE billing_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT NOT NULL,
            client_name TEXT NOT NULL,
            original_client_name TEXT,
            channel TEXT NOT NULL,
            load_date TEXT,
            period_date TEXT,
            month TEXT,
            period_raw TEXT,
            echeq_date TEXT,
            contact_name TEXT,
            invoice_number TEXT,
            net_amount REAL,
            total_amount REAL,
            is_credit_note INTEGER DEFAULT 0,
            source TEXT NOT NULL
        );

        CREATE TABLE data_quality_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_row INTEGER,
            issue_type TEXT NOT NULL,
            raw_client_name TEXT,
            raw_channel TEXT,
            raw_period TEXT,
            raw_invoice_number TEXT,
            raw_value TEXT,
            note TEXT
        );

        CREATE TABLE rentability_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_key TEXT NOT NULL,
            client_key TEXT NOT NULL,
            client_name TEXT NOT NULL,
            original_client_name TEXT,
            channel TEXT NOT NULL,
            operation_date TEXT,
            month TEXT,
            check_amount REAL,
            net_billing_amount REAL,
            billed_amount REAL,
            octopus_profit REAL,
            status TEXT NOT NULL,
            operation_type TEXT NOT NULL DEFAULT 'NORMAL',
            source_file TEXT,
            source_path TEXT,
            reference TEXT,
            note TEXT,
            source_drive_id TEXT
        );

        CREATE TABLE source_documents (
            drive_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER,
            sha256 TEXT,
            visual_sha256 TEXT,
            detected_at TEXT,
            folder_id TEXT,
            folder_period TEXT,
            operation_ref TEXT,
            status TEXT NOT NULL,
            duplicate_of TEXT,
            duplicate_reason TEXT,
            source_url TEXT,
            note TEXT
        );

        CREATE TABLE monthly_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT NOT NULL,
            client_name TEXT NOT NULL,
            channel TEXT NOT NULL,
            month TEXT NOT NULL,
            billing_total REAL DEFAULT 0,
            rentability_billed REAL DEFAULT 0,
            octopus_profit REAL DEFAULT 0,
            rentability_pct REAL,
            billing_operations INTEGER DEFAULT 0,
            rentability_operations INTEGER DEFAULT 0,
            has_pending_data INTEGER DEFAULT 0
        );
        CREATE UNIQUE INDEX monthly_metrics_identity ON monthly_metrics (client_key, channel, month);
        """
    )


def seed_aliases(conn: sqlite3.Connection) -> None:
    if not CLIENT_ALIASES_FILE.exists():
        return
    with CLIENT_ALIASES_FILE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            decision = clean_text(row.get("decision")) or "unificar"
            alias_name = clean_text(row.get("alias_name"))
            official_name = clean_text(row.get("official_name"))
            alias_key = normalize_name(alias_name)
            official_key = normalize_name(official_name)
            if not alias_key or not official_key:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO client_aliases (
                    alias_key, alias_name, official_key, official_name,
                    decision, source_group, source_sheet
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alias_key,
                    alias_name,
                    official_key,
                    official_name,
                    decision,
                    clean_text(row.get("grupo")),
                    clean_text(row.get("source_sheet")),
                ),
            )


def load_billing(conn: sqlite3.Connection) -> None:
    source = pick_facturacion_file()
    wb = load_workbook(source, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(min_row=2, values_only=True)
    for row_number, raw in enumerate(rows, start=2):
        values = list(raw) + [None] * 13
        cliente_original = clean_text(values[2])
        channel_raw = clean_text(values[3])
        period_raw = clean_text(values[5])
        invoice_number = clean_text(values[4])
        total = parse_decimal(values[10])
        net = parse_decimal(values[6])
        row_has_business_data = any(
            [
                cliente_original,
                channel_raw,
                invoice_number,
                period_raw,
                total not in (None, 0),
                net not in (None, 0),
            ]
        )
        if not row_has_business_data:
            continue
        if not cliente_original:
            conn.execute(
                """
                INSERT INTO data_quality_issues (
                    source, source_row, issue_type, raw_client_name, raw_channel,
                    raw_period, raw_invoice_number, raw_value, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source),
                    row_number,
                    "BILLING_MISSING_CLIENT",
                    cliente_original,
                    channel_raw,
                    period_raw,
                    invoice_number,
                    clean_text(values[10]),
                    "Fila de Facturación Histórica con datos pero sin cliente.",
                ),
            )
            continue
        cliente_oficial = canonical_client_name(cliente_original)
        period = parse_date(values[5])
        if not period:
            conn.execute(
                """
                INSERT INTO data_quality_issues (
                    source, source_row, issue_type, raw_client_name, raw_channel,
                    raw_period, raw_invoice_number, raw_value, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source),
                    row_number,
                    "BILLING_UNPARSEABLE_PERIOD",
                    cliente_original,
                    channel_raw,
                    period_raw,
                    invoice_number,
                    clean_text(values[10]),
                    "No se pudo interpretar el período de Facturación Histórica.",
                ),
            )
            continue
        month = period.strftime("%Y-%m")
        if month > CURRENT_MONTH:
            conn.execute(
                """
                INSERT INTO data_quality_issues (
                    source, source_row, issue_type, raw_client_name, raw_channel,
                    raw_period, raw_invoice_number, raw_value, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source),
                    row_number,
                    "BILLING_FUTURE_PERIOD",
                    cliente_original,
                    channel_raw,
                    period_raw,
                    invoice_number,
                    clean_text(values[10]),
                    "Período posterior al mes operativo configurado; no se carga hasta confirmar corte.",
                ),
            )
            continue
        client_key = normalize_name(cliente_oficial)
        if not client_key:
            continue
        channel = normalize_channel(values[3])
        if total is None and net is None:
            conn.execute(
                """
                INSERT INTO data_quality_issues (
                    source, source_row, issue_type, raw_client_name, raw_channel,
                    raw_period, raw_invoice_number, raw_value, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source),
                    row_number,
                    "BILLING_MISSING_AMOUNT",
                    cliente_original,
                    channel_raw,
                    period_raw,
                    invoice_number,
                    clean_text(values[10]),
                    "Fila de Facturación Histórica sin Neto ni Total interpretable.",
                ),
            )
            continue
        load_date = parse_date(values[0])
        echeq_date = parse_date(values[12])
        conn.execute(
            """
            INSERT INTO billing_operations (
                client_key, client_name, original_client_name, channel, load_date,
                period_date, month, period_raw, echeq_date, contact_name,
                invoice_number, net_amount, total_amount, is_credit_note, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_key,
                cliente_oficial,
                cliente_original,
                channel,
                load_date.isoformat() if load_date else None,
                period.isoformat(),
                month,
                period_raw,
                echeq_date.isoformat() if echeq_date else None,
                clean_text(values[1]),
                invoice_number,
                net,
                total,
                1 if (total is not None and total < 0) or (net is not None and net < 0) else 0,
                str(source),
            ),
        )


def load_rentability(conn: sqlite3.Connection) -> None:
    for file_path in RENTABILIDAD_FILES:
        if not file_path.exists():
            continue
        wb = load_workbook(file_path, data_only=True)
        if "Trazabilidad" not in wb.sheetnames:
            continue
        ws = wb["Trazabilidad"]
        headers = [clean_text(c.value) for c in ws[1]]
        index = {header_key(name): pos for pos, name in enumerate(headers)}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            cliente_canal = clean_text(row[index.get("CLIENTE", 1)])
            if not cliente_canal:
                continue
            client_name, channel = parse_cliente_canal(cliente_canal)
            original_client_name = client_name
            client_name = canonical_client_name(original_client_name)
            client_key = normalize_name(client_name)
            op_date = parse_date(row[index.get("FECHA", 0)])
            month = op_date.strftime("%Y-%m") if op_date else file_path.stem[-7:]
            facturado = parse_decimal(row[index.get("FACTURADO", 2)])
            ganancia = parse_decimal(row[index.get("GANANCIAOCTOPUS", 3)])
            status = clean_text(row[index.get("ESTADO", 5)]) or "PENDIENTE"
            note = clean_text(row[index.get("OBSERVACION", 7)])
            source_file = clean_text(row[index.get("FUENTE", 6)])
            operation_type = "NORMAL"
            if client_key == "OVNIPLAST" and Path(source_file).name in {
                "00003864-PHOTO-2026-07-08-19-11-01.jpg",
                "00003865-PHOTO-2026-07-08-19-16-38.jpg",
            }:
                status = "DUPLICADO"
                note = (
                    "Duplicado heredado del Excel mensual; "
                    "los cuadros validados se cargan desde manual_rentability_operations.csv."
                )
            transfer_amount, transfer_note = lookup_transfer_1_2(source_file, ganancia)
            if transfer_amount is not None:
                facturado = transfer_amount
                status = "OK_TRANSFERENCIA_1_2"
                operation_type = "TRANSFERENCIA_1_2"
                note = transfer_note or ""
            elif transfer_note:
                note = "; ".join(part for part in [note, transfer_note] if part)
            if facturado is None and ganancia is not None:
                recovered, recovery_note = lookup_billed_from_history(
                    conn, original_client_name, channel, cliente_canal
                )
                if recovered is not None:
                    facturado = recovered
                    status = "OK_FC_HISTORICA"
                    operation_type = "FACTURACION_HISTORICA"
                    note = "; ".join(part for part in [note, recovery_note] if part)
                elif recovery_note:
                    note = "; ".join(part for part in [note, recovery_note] if part)
            if month > CURRENT_MONTH:
                continue
            conn.execute(
                """
                INSERT INTO rentability_operations (
                    operation_key, client_key, client_name, original_client_name, channel, operation_date, month,
                    check_amount, net_billing_amount, billed_amount, octopus_profit, status,
                    operation_type, source_file, source_path, reference, note, source_drive_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    make_operation_key(
                        source_file, op_date, client_key, channel, facturado, ganancia
                    ),
                    client_key,
                    client_name,
                    original_client_name,
                    channel,
                    op_date.isoformat() if op_date else None,
                    month,
                    facturado if operation_type == "TRANSFERENCIA_1_2" else None,
                    None if operation_type == "TRANSFERENCIA_1_2" else facturado,
                    facturado,
                    ganancia,
                    status,
                    operation_type,
                    file_path.name,
                    source_file,
                    "",
                    note,
                    extract_drive_id(source_file),
                ),
            )


def manual_rentability_record(row: dict[str, str]) -> dict | None:
    """Normalize one persisted manual row into the database representation."""
    client_name = clean_text(row.get("client_name"))
    if not client_name:
        return None
    original_client_name = client_name
    client_name = canonical_client_name(original_client_name)
    op_date = parse_date(row.get("received_date"))
    if not op_date:
        return None
    month = op_date.strftime("%Y-%m")
    channel = normalize_channel(row.get("channel"))
    status = clean_text(row.get("status")) or "PENDIENTE"
    operation_type = clean_text(row.get("operation_type")) or "NORMAL"
    net_billing_amount = parse_decimal(row.get("net_billing_amount"))
    legacy_billed_amount = parse_decimal(row.get("billed_amount"))
    billed_amount = net_billing_amount if net_billing_amount is not None else legacy_billed_amount
    check_amount = parse_decimal(row.get("check_amount"))
    if check_amount is None and operation_type == "TRANSFERENCIA_1_2":
        check_amount = legacy_billed_amount
    source_path = clean_text(row.get("source_path"))
    profit = parse_decimal(row.get("octopus_profit"))
    client_key = normalize_name(client_name)
    fragment_key = month if operation_type == "MULTI_MONTH_SPLIT" else None
    return {
        "operation_key": make_operation_key(
            source_path, op_date, client_key, channel, billed_amount, profit, fragment_key
        ),
        "client_key": client_key,
        "client_name": client_name,
        "original_client_name": original_client_name,
        "channel": channel,
        "operation_date": op_date.isoformat(),
        "month": month,
        "check_amount": check_amount,
        "net_billing_amount": net_billing_amount,
        "billed_amount": billed_amount,
        "octopus_profit": profit,
        "status": status,
        "operation_type": operation_type,
        "source_file": Path(source_path).name,
        "source_path": source_path,
        "reference": clean_text(row.get("reference")),
        "note": clean_text(row.get("note")),
        "source_drive_id": extract_drive_id(source_path),
    }


def insert_manual_rentability(conn: sqlite3.Connection, record: dict) -> None:
    columns = (
        "operation_key", "client_key", "client_name", "original_client_name", "channel",
        "operation_date", "month", "check_amount", "net_billing_amount", "billed_amount",
        "octopus_profit", "status", "operation_type", "source_file", "source_path",
        "reference", "note", "source_drive_id",
    )
    conn.execute(
        f"INSERT INTO rentability_operations ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        tuple(record[column] for column in columns),
    )


def load_manual_rentability(
    conn: sqlite3.Connection, drive_ids: set[str] | None = None
) -> None:
    if not MANUAL_RENTABILITY_FILE.exists():
        return
    with MANUAL_RENTABILITY_FILE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            record = manual_rentability_record(row)
            if record is None:
                continue
            if drive_ids is not None and record["source_drive_id"] not in drive_ids:
                continue
            insert_manual_rentability(conn, record)


def load_source_documents(conn: sqlite3.Connection) -> None:
    if not SOURCE_DOCUMENTS_FILE.exists():
        return
    with SOURCE_DOCUMENTS_FILE.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            drive_id = clean_text(row.get("drive_id"))
            if not drive_id:
                continue
            operation_ref = clean_text(row.get("operation_ref"))
            if not operation_ref:
                match = conn.execute(
                    "SELECT operation_key FROM rentability_operations WHERE source_drive_id = ? ORDER BY id LIMIT 1",
                    (drive_id,),
                ).fetchone()
                if match:
                    operation_ref = match[0]
            conn.execute(
                """
                INSERT INTO source_documents (
                    drive_id, file_name, mime_type, size_bytes, sha256, visual_sha256,
                    detected_at, folder_id, folder_period, operation_ref, status,
                    duplicate_of, duplicate_reason, source_url, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drive_id,
                    clean_text(row.get("file_name")),
                    clean_text(row.get("mime_type")),
                    int(parse_decimal(row.get("size_bytes")) or 0),
                    clean_text(row.get("sha256")),
                    clean_text(row.get("visual_sha256")),
                    clean_text(row.get("detected_at")),
                    clean_text(row.get("folder_id")),
                    clean_text(row.get("folder_period")),
                    operation_ref,
                    clean_text(row.get("status")) or "NUEVO",
                    clean_text(row.get("duplicate_of")),
                    clean_text(row.get("duplicate_reason")),
                    clean_text(row.get("source_url")),
                    clean_text(row.get("note")),
                ),
            )


def _where_client_keys(client_keys: set[str] | None) -> tuple[str, tuple[str, ...]]:
    if client_keys is None:
        return "", ()
    ordered = tuple(sorted(client_keys))
    if not ordered:
        return " WHERE 0", ()
    return f" WHERE client_key IN ({', '.join('?' for _ in ordered)})", ordered


def rebuild_clients(conn: sqlite3.Connection, client_keys: set[str] | None = None) -> None:
    where, params = _where_client_keys(client_keys)
    if client_keys is not None:
        conn.executemany("DELETE FROM clients WHERE client_key = ?", [(key,) for key in client_keys])
    names: dict[str, dict] = {}
    for client_key, client_name, period_date, month in conn.execute(
        "SELECT client_key, client_name, period_date, month FROM billing_operations" + where,
        params,
    ):
        item = names.setdefault(
            client_key,
            {"display": client_name, "norm": client_key, "dates": [], "months": []},
        )
        item["dates"].append(period_date)
        item["months"].append(month)
    for client_key, client_name, operation_date, month in conn.execute(
        "SELECT client_key, client_name, operation_date, month FROM rentability_operations" + where,
        params,
    ):
        item = names.setdefault(
            client_key,
            {"display": client_name, "norm": client_key, "dates": [], "months": []},
        )
        if operation_date:
            item["dates"].append(operation_date)
        if month:
            item["months"].append(month)

    for client_key, item in names.items():
        first_op = min(item["dates"]) if item["dates"] else None
        last_op = max(item["dates"]) if item["dates"] else None
        last_month = max(item["months"]) if item["months"] else None
        months_without = month_diff(last_month) if last_month else None
        status = "Activo" if months_without is not None and months_without <= 3 else "Inactivo"
        conn.execute(
            """
            INSERT INTO clients (
                client_key, display_name, normalized_name, first_operation, last_operation,
                last_month, months_without_activity, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_key,
                item["display"],
                item["norm"],
                first_op,
                last_op,
                last_month,
                months_without,
                status,
            ),
        )


def rebuild_monthly_metrics(
    conn: sqlite3.Connection,
    identities: set[tuple[str, str, str]] | None = None,
) -> None:
    from metrics import VALID_BILLING, VALID_RENTABILITY

    if identities is None:
        conn.execute("DELETE FROM monthly_metrics")
        keys = set()
        for row in conn.execute("SELECT DISTINCT client_key, channel, month FROM billing_operations"):
            keys.add(row)
        for row in conn.execute("SELECT DISTINCT client_key, channel, month FROM rentability_operations"):
            keys.add(row)
    else:
        keys = set()
        for identity in identities:
            conn.execute(
                "DELETE FROM monthly_metrics WHERE client_key = ? AND channel = ? AND month = ?",
                identity,
            )
            exists = conn.execute(
                """SELECT 1 FROM billing_operations
                   WHERE client_key = ? AND channel = ? AND month = ?
                   UNION ALL
                   SELECT 1 FROM rentability_operations
                   WHERE client_key = ? AND channel = ? AND month = ? LIMIT 1""",
                identity + identity,
            ).fetchone()
            if exists:
                keys.add(identity)

    names = dict(conn.execute("SELECT client_key, display_name FROM clients"))
    for client_key, channel, month in sorted(keys):
        billing_total, billing_ops = conn.execute(
            f"""
            SELECT COALESCE(SUM(net_amount), 0), COUNT(*)
            FROM billing_operations
            WHERE client_key = ? AND channel = ? AND month = ?
              AND {VALID_BILLING}
            """,
            (client_key, channel, month),
        ).fetchone()
        rent_billed, profit, rent_ops, pending = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN {VALID_RENTABILITY} THEN billed_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN {VALID_RENTABILITY} THEN octopus_profit ELSE 0 END), 0),
                SUM(CASE WHEN {VALID_RENTABILITY} THEN 1 ELSE 0 END),
                SUM(CASE WHEN {VALID_RENTABILITY} THEN 0 ELSE 1 END)
            FROM rentability_operations
            WHERE client_key = ? AND channel = ? AND month = ?
            """,
            (client_key, channel, month),
        ).fetchone()
        pct = profit / rent_billed if rent_billed else None
        conn.execute(
            """
            INSERT INTO monthly_metrics (
                client_key, client_name, channel, month, billing_total, rentability_billed,
                octopus_profit, rentability_pct, billing_operations, rentability_operations, has_pending_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_key,
                names[client_key],
                channel,
                month,
                billing_total or 0,
                rent_billed or 0,
                profit or 0,
                pct,
                billing_ops or 0,
                rent_ops or 0,
                1 if pending else 0,
            ),
        )


def load_database() -> None:
    global ALIAS_BY_KEY
    ALIAS_BY_KEY = load_alias_map()
    # Publish one complete, reconciled snapshot so readers never see a partial load.
    fd, temporary = tempfile.mkstemp(prefix=".octopus-", suffix=".db", dir=DB_PATH.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn:
            reset_schema(conn)
            seed_aliases(conn)
            load_billing(conn)
            load_rentability(conn)
            load_manual_rentability(conn)
            load_source_documents(conn)
            rebuild_clients(conn)
            rebuild_monthly_metrics(conn)
            from sync_checks import reconcile_database, write_manifest

            report = reconcile_database(conn, datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date())
            conn.commit()
        os.replace(temporary, DB_PATH)
        write_manifest(DB_PATH.parent, report)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    load_database()
    with connect() as conn:
        clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        billing = conn.execute("SELECT COUNT(*) FROM billing_operations").fetchone()[0]
        rent = conn.execute("SELECT COUNT(*) FROM rentability_operations").fetchone()[0]
        print(f"Base creada: {DB_PATH}")
        print(f"Clientes: {clients}")
        print(f"Operaciones de facturación: {billing}")
        print(f"Cuadros de rentabilidad: {rent}")
