from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


TRANSFER_COLUMNS = (
    "FECHA TICHET",
    "MONTO",
    "NRO COMPROBANTE",
    "NOMBRE Y APELLIDO",
    "CUIT",
    "BANCO",
)

DEPOSIT_COLUMNS = ("FECHA", "IMPORTE", "NUMERO DE COMPROBANTE", "BANCO")

IDENTIFIER_PRIORITY = ("operation_number", "receipt_number", "coelsa_id")

TIMEZONE = ZoneInfo("America/Buenos_Aires")
CUT_TIME = time(15, 0)


def close_window(closing_day: date) -> tuple[datetime, datetime]:
    """Return [start, end) for a normal or Monday operational close."""
    end = datetime.combine(closing_day, CUT_TIME, tzinfo=TIMEZONE)
    days_back = 3 if closing_day.weekday() == 0 else 1
    start = end - timedelta(days=days_back)
    return start, end
