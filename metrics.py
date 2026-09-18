from __future__ import annotations

from datetime import date

from data_access import read_sql


VALID_RENTABILITY = "status LIKE 'OK%' AND billed_amount > 0 AND octopus_profit IS NOT NULL"
VALID_BILLING = "net_amount IS NOT NULL AND net_amount > 0"


def period_filter(kind: str, month: str, as_of: date) -> tuple[str, tuple]:
    current_month = as_of.strftime("%Y-%m")
    validity, cutoff = {
        "billing": (VALID_BILLING, "load_date"),
        "rentability": (VALID_RENTABILITY, "operation_date"),
    }[kind]
    where = f"month = ? AND {validity}"
    params = [month]
    if month > current_month:
        where += " AND 0"
    elif month == current_month:
        where += f" AND {cutoff} <= ?"
        params.append(as_of.isoformat())
    return where, tuple(params)


def executive_summary(selected_month: str, as_of: date, read=read_sql):
    billing_where, billing_params = period_filter("billing", selected_month, as_of)
    rentability_where, rentability_params = period_filter("rentability", selected_month, as_of)
    billing = read(
        f"""SELECT COALESCE(SUM(net_amount), 0) AS facturacion, COUNT(*) AS registros
        FROM billing_operations WHERE {billing_where}""", billing_params,
    )
    rentability = read(
        f"""SELECT COALESCE(SUM(billed_amount), 0) AS facturacion_neta_rentabilidad,
        COALESCE(SUM(octopus_profit), 0) AS ganancia_octopus, COUNT(*) AS operaciones
        FROM rentability_operations WHERE {rentability_where}""", rentability_params,
    )
    return billing, rentability


def rentability_ranking(selected_month: str, limit: int, as_of: date, read=read_sql):
    where, params = period_filter("rentability", selected_month, as_of)
    return read(
        f"""SELECT c.display_name AS client_name, r.client_key,
            SUM(billed_amount) AS facturacion_validada,
            SUM(octopus_profit) AS ganancia_octopus,
            SUM(octopus_profit) / SUM(billed_amount) AS rentabilidad,
            COUNT(*) AS operaciones
        FROM (SELECT * FROM rentability_operations WHERE {where}) r
        JOIN clients c ON c.client_key = r.client_key
        GROUP BY r.client_key, c.display_name
        HAVING SUM(billed_amount) > 0
        ORDER BY rentabilidad DESC, ganancia_octopus DESC, r.client_key
        LIMIT ?""", params + (limit,),
    )


def billing_ranking(selected_month: str, limit: int, as_of: date, read=read_sql):
    where, params = period_filter("billing", selected_month, as_of)
    return read(
        f"""SELECT c.display_name AS client_name, b.client_key,
            SUM(net_amount) AS facturacion, COUNT(*) AS registros
        FROM billing_operations b JOIN clients c ON c.client_key = b.client_key
        WHERE {where}
        GROUP BY b.client_key, c.display_name
        ORDER BY facturacion DESC, b.client_key
        LIMIT ?""", params + (limit,),
    )
