from __future__ import annotations

import io
import re
import subprocess
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageOps


EXTRACTOR_VERSION = "ocr-rules-v5"
BANKS = (
    ("dupondio", "Dupondio"),
    ("mercado pago", "Mercado Pago"),
    ("personal pay", "Personal Pay"),
    ("naranjax", "Naranja X"),
    ("naranja x", "Naranja X"),
    ("brubank", "Brubank"),
    ("cuenta dni", "Banco Provincia"),
    ("prex", "Prex"),
    ("uala", "Uala"),
    ("supervielle", "Supervielle"),
    ("galicia", "Galicia"),
    ("santander", "Santander"),
    ("macro", "Macro"),
    ("bna", "Banco Nacion"),
    ("banco de la nacion", "Banco Nacion"),
    ("pvs", "PVS"),
    ("pandapay", "PandaPay"),
    ("coinag", "Coinag"),
    ("provincia", "Banco Provincia"),
    ("bbva", "BBVA"),
    ("comafi", "Comafi"),
    ("credicoop", "Credicoop"),
    ("hsbc", "HSBC"),
    ("icbc", "ICBC"),
    ("banco del sol", "Banco del Sol"),
)

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "0ct": 10, "nov": 11, "dic": 12,
}


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def ocr(content: bytes, mime_type: str) -> str:
    chunks: list[str] = []
    if mime_type == "application/pdf":
        try:
            embedded = subprocess.run(
                ["pdftotext", "-layout", "-", "-"],
                input=content,
                capture_output=True,
                check=False,
                timeout=30,
            ).stdout.decode("utf-8", errors="replace").strip()
            if len(embedded) >= 80:
                # Digital PDF text is materially more reliable than OCR over a
                # rendered page. Mixing both created conflicting identifiers
                # from otherwise exact banking receipts.
                return embedded
        except (OSError, subprocess.SubprocessError):
            pass
        images = convert_from_bytes(content, dpi=300, first_page=1, last_page=3)
    else:
        images = [Image.open(io.BytesIO(content))]
    for image in images:
        source = ImageOps.exif_transpose(image).convert("RGB")
        if source.width < 1200:
            ratio = 1200 / source.width
            source = source.resize((1200, int(source.height * ratio)), Image.Resampling.LANCZOS)
        prepared = ImageOps.autocontrast(ImageOps.grayscale(source))
        prepared = ImageEnhance.Contrast(prepared).enhance(1.5)
        prepared = ImageEnhance.Sharpness(prepared).enhance(1.4)
        default_text = pytesseract.image_to_string(prepared, lang="spa")
        block_text = pytesseract.image_to_string(prepared, lang="spa", config="--psm 6")
        chunks.append(default_text)
        if block_text.strip() and block_text.strip() != default_text.strip():
            chunks.append(block_text)
    return "\n".join(chunks).strip()


def _date(text: str) -> date | None:
    plain = _plain(text)
    named = re.search(
        r"\b(\d{1,2})(?:\s+de\s+|[ /-]+)(" + "|".join(MONTHS)
        + r")(?:\s+de\s+|[ /-]+)(\d{4})\b",
        plain,
        re.IGNORECASE,
    )
    if named:
        try:
            return date(int(named.group(3)), MONTHS[named.group(2).lower()], int(named.group(1)))
        except ValueError:
            pass
    for pattern in (
        r"(?:fecha(?:\s+(?:de\s+)?(?:operacion|comprobante))?)\s*:?[ ]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
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


def _parse_money(raw: str) -> int | None:
    raw = raw.strip().replace("/", "")
    raw = re.sub(r"[^0-9.,]", "", raw)
    if not raw:
        return None
    if "." in raw and "," in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "." in raw or "," in raw:
        separator = "." if "." in raw else ","
        parts = raw.split(separator)
        if len(parts) > 2 or len(parts[-1]) == 3:
            raw = "".join(parts)
        else:
            raw = ".".join(parts)
    try:
        return int((Decimal(raw) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _money(text: str) -> int | None:
    labels = (
        r"importe(?:\s+(?:debitado|a\s+transferir|total))?",
        r"monto",
        r"dinero\s+enviado",
        r"enviaste(?:\s+dinero)?",
        r"transferencia\s+enviada",
    )
    labelled_values: list[int] = []
    for label in labels:
        matches = re.finditer(
            label + r"\s*:?[ ]*(?:\n\s*)?(\$?)[ ]*([0-9][0-9.,/ ]{0,24})",
            text,
            re.IGNORECASE,
        )
        for match in matches:
            # Labels such as "Enviaste" are often followed by an OCR-damaged
            # currency symbol. Without the symbol, a leading 5 can turn $1M
            # into $51M, so that case must remain unresolved.
            if match.group(1) != "$" and label.startswith(("enviaste", "transferencia")):
                continue
            value = _parse_money(match.group(2))
            if value is not None:
                labelled_values.append(value)
    if labelled_values:
        return max(labelled_values)

    standalone_values: list[int] = []
    for match in re.finditer(r"\$[ ]*([0-9][0-9.,/ ]{0,24})", text):
        # Several wallet receipts display the transferred amount as a standalone
        # currency line. Requiring the dollar sign avoids treating account or
        # document numbers as money.
        value = _parse_money(match.group(1))
        if value is not None:
            standalone_values.append(value)
    return max(standalone_values) if standalone_values else None


def _identifier(text: str) -> tuple[str | None, str | None, list[str]]:
    token = r"([A-Z0-9\[\]|}{-]{5,})"
    patterns = (
        ("operation_number", r"\bn(?:ro|[uú]mero)?\s*[.*?°ºo'\"”’]*\s*de\s+la\s+" + token + r"\s*\n?\s*operaci[oó]n"),
        ("operation_number", r"\bn(?:ro|[uú]mero)?\s*[.*?°ºo'\"”’]*\s*de\s+(?:la\s+)?operaci[oó]n(?:\s+de\s+[^\n]+)?\s*:?\s*" + token),
        ("operation_number", r"\bn(?:ro|[uú]mero)?\s*[.*?°ºo'\"”’]*\s*de\s+transacci[oó]n\s*:?\s*" + token),
        ("operation_number", r"\bid\.?\s*op\.?\s*:?\s*" + token),
        ("receipt_number", r"\bn(?:ro|[uú]mero)?\s*[.*?°ºo'\"”’]*\s*(?:de\s+)?comprobante\s*:?\s*" + token),
        ("receipt_number", r"n[uú]mero\s+de\s+control\s*:?\s*" + token),
        ("coelsa_id", r"(?:id\s+coelsa|coelsa\s*id)\s*:?\s*" + token),
    )
    for kind, pattern in patterns:
        candidates: list[str] = []
        damaged = False
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(1).strip()
            if value.count("-") == 4 and not re.fullmatch(
                r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
                value,
            ):
                continue
            candidates.append(value)
            damaged = damaged or re.fullmatch(r"[A-Z0-9-]+", value, re.IGNORECASE) is None
        unique_by_normalized = {value.upper(): value for value in candidates}
        unique = list(unique_by_normalized.values())
        if not unique:
            continue
        if damaged or len(unique) > 1:
            return kind, None, unique
        return kind, unique[0], unique
    return None, None, []


def _sender_section(text: str) -> str:
    section_patterns = (
        (r"datos\s+de\s+quien\s+realiz\w*(?:\s+la\s+transferencia)?", None),
        (r"\bde\s*:\s*", r"\bpara\s*:\s*"),
        (r"(?m)^[ \t]*[^\n]{0,6}\bde[ \t]*$", r"(?m)^[ \t]*[^\n]{0,6}\bpara[ \t]*$"),
        (r"\bordenante\b", r"datos\s+de\s+la\s+operaci"),
        (r"\benv[ií]a\b", r"\b(?:destinatario|recibe)\b"),
        (r"\bdesde\b", r"\b(?:monto|recibe|para)\b"),
        (r"\bemisor\b", r"\b(?:motivo|id\.?\s*op)\b"),
        (r"origen\s+y\s+destino", None),
        (r"cuenta\s+(?:de\s+)?origen", r"cuenta\s+(?:de\s+)?destino"),
        (r"\borigen\b", r"\bpara\b"),
    )
    plain = _plain(text)
    for start_pattern, end_pattern in section_patterns:
        start = re.search(start_pattern, plain, re.IGNORECASE)
        if not start:
            continue
        end = re.search(end_pattern, plain[start.end():], re.IGNORECASE) if end_pattern else None
        stop = start.end() + end.start() if end else len(text)
        return text[start.end():stop]
    return ""


def _tax_id(text: str, account_config: dict) -> str | None:
    section = _sender_section(text)
    match = re.search(r"\b(?:CUIT(?:/CUIL)?\s*:?[ ]*)?(\d{2}[- ]?\d{8}[- ]?\d)\b", section, re.IGNORECASE)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def _labelled_name(text: str) -> str | None:
    section = _sender_section(text)
    labelled = re.search(
        r"(?:apellido\s+y\s+nombre|nombre\s+y\s+apellido|nombre\s+o\s+raz[oó]n\s+social)"
        r"\s*:?[ ]*([^\n]{4,80})",
        section,
        re.IGNORECASE,
    )
    if labelled:
        candidate = labelled.group(1).strip(" :-\t")
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'., ]{4,80}", candidate):
            return candidate
    lines = [line.strip(" :-\t") for line in section.splitlines() if line.strip(" :-\t")]
    skip = (
        "apellido y nombre", "nombre y apellido", "nombre o razon social",
        "cuit", "cuil", "cbu", "cvu", "cuenta", "banco", "entidad",
        "importe", "monto", "fecha", "hora", "nro", "numero",
    )
    for line in lines[:8]:
        plain = _plain(line)
        if any(plain.startswith(value) for value in skip):
            continue
        cleaned = re.sub(r"^\([^)]{1,8}\)\s*", "", line)
        cleaned = re.sub(r"^(?:nx|prex)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ']+", "", cleaned)
        parts = cleaned.split()
        if len(parts) >= 4 and len(parts[0]) == 1 and parts[0].isupper():
            cleaned = " ".join(parts[1:])
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'., ]{4,80}", cleaned):
            return cleaned.strip()
    return None


def _bank(text: str) -> str | None:
    plain = _plain(text)
    if re.search(r"\b(?:un\s*vala|wnuald)\b", plain):
        return "Uala"
    if re.search(r"cuenta.{0,16}dni", plain, re.DOTALL):
        return "Banco Provincia"
    for marker, display in BANKS:
        if marker in plain:
            return display
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


def _visible_destination_identifiers(text: str) -> list[str]:
    values = re.findall(
        r"(?:cbu|cvu)(?:\s*/\s*(?:cbu|cvu))?\s*:?[ ]*([0-9][0-9 .-]{20,30})",
        text,
        re.IGNORECASE,
    )
    return sorted({re.sub(r"\D", "", value) for value in values if len(re.sub(r"\D", "", value)) == 22})


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
    identifier_type, identifier_value, identifier_candidates = _identifier(text)
    account_key, account_matches = _account(text, account_config)
    result = {
        "document_type": document_type,
        "ticket_date": _date(text),
        "amount_cents": _money(text),
        "identifier_type": identifier_type,
        "identifier_value": identifier_value,
        "identifier_candidates": identifier_candidates,
        "full_name": _labelled_name(text),
        "tax_id": _tax_id(text, account_config),
        "origin_bank": _bank(text),
        "destination_account_key": account_key,
        "account_matches": account_matches,
        "destination_identifiers_seen": _visible_destination_identifiers(text),
    }
    required = {
        "transfer": ("ticket_date", "amount_cents", "identifier_value", "full_name", "tax_id", "origin_bank"),
        "deposit": ("ticket_date", "amount_cents", "identifier_value", "origin_bank"),
    }.get(document_type, ())
    result["missing_fields"] = [field for field in required if result[field] in (None, "")]
    return result
