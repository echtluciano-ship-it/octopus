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


def close_window(
    closing_day: date,
    *,
    holidays: set[date] | frozenset[date] = frozenset(),
) -> tuple[datetime, datetime]:
    """Return the half-open window from the previous business-day cutoff."""
    if closing_day.weekday() >= 5 or closing_day in holidays:
        raise ValueError("A close can only run on a business day")
    end = datetime.combine(closing_day, CUT_TIME, tzinfo=TIMEZONE)
    previous = closing_day - timedelta(days=1)
    while previous.weekday() >= 5 or previous in holidays:
        previous -= timedelta(days=1)
    start = datetime.combine(previous, CUT_TIME, tzinfo=TIMEZONE)
    return start, end
