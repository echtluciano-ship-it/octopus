from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageOps


EXTRACTOR_VERSION = "ocr-rules-v1"
BANKS = (
    "mercado pago", "naranja", "macro", "provincia", "galicia", "santander",
    "bbva", "brubank", "supervielle", "comafi", "nacion", "credicoop",
    "hsbc", "icbc", "uala", "personal pay", "banco del sol",
)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def ocr(content: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        images = convert_from_bytes(content, dpi=250, first_page=1, last_page=3)
    else:
        images = [Image.open(io.BytesIO(content))]
    chunks: list[str] = []
    for image in images:
        prepared = ImageOps.grayscale(image)
        prepared = ImageEnhance.Contrast(prepared).enhance(1.8)
        chunks.append(pytesseract.image_to_string(prepared, lang="spa"))
    return "\n".join(chunks).strip()


def _date(text: str) -> date | None:
    for pattern in (
        r"(?:fecha(?:\s+(?:de\s+)?(?:operacion|comprobante))?)\s*:?[ ]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
    return None


def _money(text: str) -> int | None:
    pattern = re.compile(
        r"(?:importe|monto|total|transfer(?:iste|encia)?(?:\s+por)?)\s*:?[ ]*\$?[ ]*"
        r"([0-9][0-9. ]*(?:,[0-9]{1,2})?)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return int((Decimal(raw) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _identifier(text: str) -> tuple[str | None, str | None]:
    patterns = (
        ("operation_number", r"(?:n(?:ro|[uú]mero)?\.?\s+de\s+)?operaci[oó]n\s*:?[ ]*([A-Z0-9-]{5,})"),
        ("receipt_number", r"(?:n(?:ro|[uú]mero)?\.?\s+(?:de\s+)?)?comprobante\s*:?[ ]*([A-Z0-9-]{5,})"),
        ("coelsa_id", r"(?:id\s+)?coelsa\s*:?[ ]*([A-Z0-9-]{5,})"),
    )
    for kind, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return kind, match.group(1).strip()
    return None, None


def _tax_id(text: str) -> str | None:
    match = re.search(r"\b(?:CUIT\s*:?[ ]*)?(\d{2}[- ]?\d{8}[- ]?\d)\b", text, re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def _labelled_name(text: str) -> str | None:
    match = re.search(
        r"(?:nombre(?:\s+y\s+apellido)?|titular|ordenante)\s*:?[ ]*"
        r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ' ]{4,80})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return re.split(r"\n|\s{3,}", match.group(1).strip())[0].strip()


def _bank(text: str) -> str | None:
    plain = _plain(text)
    for bank in BANKS:
        if bank in plain:
            return bank.title()
    match = re.search(r"banco\s*:?[ ]*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]{3,40})", text, re.IGNORECASE)
    return match.group(1).strip().title() if match else None


def _account(text: str, account_config: dict) -> tuple[str | None, list[str]]:
    plain = _plain(text)
    digits = re.sub(r"\D", "", text)
    matches: list[str] = []
    for account in account_config.get("accounts", []):
        for identifier in account.get("destination_identifiers", []):
            value = str(identifier.get("value") or "")
            if not value:
                continue
            if identifier.get("kind") in {"cbu", "cvu", "tax_id", "account"}:
                found = re.sub(r"\D", "", value) in digits
            else:
                found = _plain(value) in plain
            if found:
                matches.append(account["key"])
                break
    unique = sorted(set(matches))
    return (unique[0] if len(unique) == 1 else None), unique


def parse(text: str, account_config: dict) -> dict[str, Any]:
    plain = _plain(text)
    if "cheque" in plain:
        document_type = "check"
    elif "deposito" in plain or "depositaste" in plain:
        document_type = "deposit"
    elif any(word in plain for word in ("transferencia", "transferiste", "enviaste", "comprobante")):
        document_type = "transfer"
    else:
        document_type = None
    identifier_type, identifier_value = _identifier(text)
    account_key, account_matches = _account(text, account_config)
    result = {
        "document_type": document_type,
        "ticket_date": _date(text),
        "amount_cents": _money(text),
        "identifier_type": identifier_type,
        "identifier_value": identifier_value,
        "full_name": _labelled_name(text),
        "tax_id": _tax_id(text),
        "origin_bank": _bank(text),
        "destination_account_key": account_key,
        "account_matches": account_matches,
    }
    required = {
        "transfer": ("ticket_date", "amount_cents", "identifier_value", "full_name", "tax_id", "origin_bank"),
        "deposit": ("ticket_date", "amount_cents", "identifier_value", "origin_bank"),
    }.get(document_type, ())
    result["missing_fields"] = [field for field in required if result[field] in (None, "")]
    return result
