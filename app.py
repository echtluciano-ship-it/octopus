from __future__ import annotations

import sqlite3
import hmac
import html
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "octopus.db"
CURRENT_DATE = date.today()
CURRENT_MONTH = CURRENT_DATE.strftime("%Y-%m")
HIDDEN_CLIENT_KEYS: set[str] = set()
MONTH_NAMES = {
    "01": "Enero",
    "02": "Febrero",
    "03": "Marzo",
    "04": "Abril",
    "05": "Mayo",
    "06": "Junio",
    "07": "Julio",
    "08": "Agosto",
    "09": "Septiembre",
    "10": "Octubre",
    "11": "Noviembre",
    "12": "Diciembre",
}


st.set_page_config(page_title="Octopus - Base de Clientes", layout="wide")


def get_secret(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""


def require_login() -> bool:
    expected_password = get_secret("OCTOPUS_APP_PASSWORD")
    expected_user = get_secret("OCTOPUS_APP_USER")
    if not expected_password:
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("Octopus")
    with st.form("login"):
        user = st.text_input("Usuario")
        password = st.text_input("Clave", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        user_ok = True if not expected_user else hmac.compare_digest(user, expected_user)
        password_ok = hmac.compare_digest(password, expected_password)
        if user_ok and password_ok:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Usuario o clave incorrectos.")
    return False


def money(value) -> str:
    if value is None or pd.isna(value):
        return "Pendiente"
    return "$ " + f"{float(value):,.0f}".replace(",", ".")


def percent(value) -> str:
    if value is None or pd.isna(value):
        return "Sin cuadros"
    return f"{float(value) * 100:.2f}%"


def percent_or_empty(value) -> str:
    if value is None or pd.isna(value):
        return "Sin datos confiables"
    return percent(value)


def executive_value(value: str) -> str:
    return html.escape(value)


def month_label(value: str) -> str:
    if not value or "-" not in value:
        return value or "Pendiente"
    year, month = value.split("-", 1)
    return f"{MONTH_NAMES.get(month, month)} {year}"


def months_between(from_month: str, to_month: str = CURRENT_MONTH) -> int | None:
    if not from_month:
        return None
    y1, m1 = map(int, from_month.split("-"))
    y2, m2 = map(int, to_month.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


@st.cache_data(show_spinner=False)
def read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)


def clear_cache() -> None:
    read_sql.clear()


def load_available_months() -> list[str]:
    months = read_sql(
        """
        SELECT DISTINCT month
        FROM (
            SELECT month FROM billing_operations WHERE month IS NOT NULL
            UNION
            SELECT month FROM rentability_operations WHERE month IS NOT NULL
        )
        WHERE month <= ?
        ORDER BY month DESC
        """,
        (CURRENT_MONTH,),
    )
    return months["month"].dropna().tolist()


def executive_summary(selected_month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    billing_where = [
        "month = ?",
        "net_amount IS NOT NULL",
        "net_amount > 0",
    ]
    billing_params: list = [selected_month]
    rentability_where = [
        "month = ?",
        "status LIKE 'OK%'",
        "billed_amount IS NOT NULL",
        "billed_amount > 0",
        "octopus_profit IS NOT NULL",
    ]
    rentability_params: list = [selected_month]

    if selected_month == CURRENT_MONTH:
        today = CURRENT_DATE.isoformat()
        billing_where.append("load_date <= ?")
        billing_params.append(today)
        rentability_where.append("operation_date <= ?")
        rentability_params.append(today)

    billing = read_sql(
        f"""
        SELECT
            COALESCE(SUM(net_amount), 0) AS facturacion,
            COUNT(*) AS registros
        FROM billing_operations
        WHERE {" AND ".join(billing_where)}
        """,
        tuple(billing_params),
    )

    rentability = read_sql(
        f"""
        SELECT
            COALESCE(SUM(billed_amount), 0) AS facturacion_neta_rentabilidad,
            COALESCE(SUM(octopus_profit), 0) AS ganancia_octopus,
            COUNT(*) AS operaciones
        FROM rentability_operations
        WHERE {" AND ".join(rentability_where)}
        """,
        tuple(rentability_params),
    )
    return billing, rentability


def rentability_ranking(selected_month: str, limit: int) -> pd.DataFrame:
    rentability_where = [
        "month = ?",
        "status LIKE 'OK%'",
        "billed_amount IS NOT NULL",
        "billed_amount > 0",
        "octopus_profit IS NOT NULL",
    ]
    params: list = [selected_month]
    if selected_month == CURRENT_MONTH:
        rentability_where.append("operation_date <= ?")
        params.append(CURRENT_DATE.isoformat())
    params.append(limit)

    return read_sql(
        f"""
        SELECT
            client_name,
            SUM(billed_amount) AS facturacion_validada,
            SUM(octopus_profit) AS ganancia_octopus,
            SUM(octopus_profit) / SUM(billed_amount) AS rentabilidad,
            COUNT(*) AS operaciones
        FROM rentability_operations
        WHERE {" AND ".join(rentability_where)}
        GROUP BY client_key, client_name
        HAVING SUM(billed_amount) > 0
        ORDER BY rentabilidad DESC, ganancia_octopus DESC
        LIMIT ?
        """,
        tuple(params),
    )


def billing_ranking(selected_month: str, limit: int) -> pd.DataFrame:
    billing_where = [
        "month = ?",
        "net_amount IS NOT NULL",
        "net_amount > 0",
    ]
    params: list = [selected_month]
    if selected_month == CURRENT_MONTH:
        billing_where.append("load_date <= ?")
        params.append(CURRENT_DATE.isoformat())
    params.append(limit)

    return read_sql(
        f"""
        SELECT
            client_name,
            SUM(net_amount) AS facturacion,
            COUNT(*) AS registros
        FROM billing_operations
        WHERE {" AND ".join(billing_where)}
        GROUP BY client_key, client_name
        ORDER BY facturacion DESC
        LIMIT ?
        """,
        tuple(params),
    )


def ranking_item(position: int, client_name: str, detail: str) -> str:
    return f"""
      <div class="ranking-item">
        <div class="ranking-position">{position}</div>
        <div class="ranking-main">
          <div class="ranking-client">{html.escape(client_name)}</div>
          <div class="ranking-detail">{html.escape(detail)}</div>
        </div>
      </div>
    """


def render_rentability_ranking(ranking: pd.DataFrame) -> str:
    if ranking.empty:
        return '<div class="ranking-empty">Sin datos confiables para este periodo.</div>'
    items = []
    for position, row in enumerate(ranking.itertuples(index=False), 1):
        detail = (
            f"{percent(row.rentabilidad)} · "
            f"{money(row.facturacion_validada)} · "
            f"{money(row.ganancia_octopus)}"
        )
        items.append(ranking_item(position, row.client_name, detail))
    return '<div class="ranking-list">' + "".join(items) + "</div>"


def render_billing_ranking(ranking: pd.DataFrame) -> str:
    if ranking.empty:
        return '<div class="ranking-empty">Sin datos de facturacion para este periodo.</div>'
    items = []
    for position, row in enumerate(ranking.itertuples(index=False), 1):
        items.append(ranking_item(position, row.client_name, money(row.facturacion)))
    return '<div class="ranking-list">' + "".join(items) + "</div>"


if not require_login():
    st.stop()

st.title("Base de Clientes")

if not DB_PATH.exists():
    st.warning("La base todavia no esta cargada.")
    st.stop()

st.markdown(
    """
    <style>
    .executive-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.5rem;
        margin: 0.25rem 0 0.2rem;
    }
    .executive-card {
        border: 1px solid rgba(49, 51, 63, 0.18);
        border-radius: 8px;
        padding: 0.55rem 0.65rem;
        min-width: 0;
    }
    .executive-label {
        color: rgba(49, 51, 63, 0.68);
        font-size: 0.78rem;
        line-height: 1.1;
        margin-bottom: 0.25rem;
    }
    .executive-number {
        color: rgb(49, 51, 63);
        font-size: 1.18rem;
        font-weight: 700;
        line-height: 1.15;
        overflow-wrap: anywhere;
    }
    .rankings-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.35rem 0 0.2rem;
    }
    .ranking-panel {
        border: 1px solid rgba(49, 51, 63, 0.14);
        border-radius: 8px;
        padding: 0.55rem 0.65rem 0.3rem;
        min-width: 0;
    }
    .ranking-panel-title {
        font-weight: 700;
        font-size: 0.95rem;
        margin-bottom: 0.35rem;
    }
    .ranking-list {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }
    .ranking-item {
        display: flex;
        gap: 0.45rem;
        align-items: flex-start;
        padding: 0.34rem 0;
        border-top: 1px solid rgba(49, 51, 63, 0.08);
        min-width: 0;
    }
    .ranking-item:first-child {
        border-top: 0;
        padding-top: 0;
    }
    .ranking-position {
        flex: 0 0 1.35rem;
        color: rgba(49, 51, 63, 0.65);
        font-weight: 700;
        font-size: 0.85rem;
        line-height: 1.2;
    }
    .ranking-main {
        min-width: 0;
    }
    .ranking-client {
        color: rgb(49, 51, 63);
        font-weight: 700;
        font-size: 0.88rem;
        line-height: 1.16;
        overflow-wrap: anywhere;
    }
    .ranking-detail {
        color: rgba(49, 51, 63, 0.68);
        font-size: 0.78rem;
        line-height: 1.22;
        margin-top: 0.1rem;
        overflow-wrap: anywhere;
    }
    .ranking-empty {
        color: rgba(49, 51, 63, 0.62);
        font-size: 0.82rem;
        padding: 0.2rem 0 0.35rem;
    }
    @media (max-width: 640px) {
        .executive-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.42rem;
        }
        .executive-card {
            padding: 0.45rem 0.5rem;
        }
        .executive-label {
            font-size: 0.72rem;
        }
        .executive-number {
            font-size: 0.96rem;
        }
        .rankings-grid {
            grid-template-columns: 1fr;
            gap: 0.55rem;
        }
        .ranking-panel {
            padding: 0.5rem 0.55rem 0.25rem;
        }
        .ranking-panel-title {
            font-size: 0.9rem;
        }
        .ranking-client {
            font-size: 0.84rem;
        }
        .ranking-detail {
            font-size: 0.73rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

available_months = load_available_months()
if available_months:
    st.subheader("Inicio Ejecutivo")
    selected_month = st.selectbox(
        "Mes",
        options=available_months,
        format_func=month_label,
        label_visibility="collapsed",
    )
    billing_summary, rentability_summary = executive_summary(selected_month)

    facturacion_total = float(billing_summary["facturacion"].iloc[0]) if not billing_summary.empty else 0
    registros_facturacion = int(billing_summary["registros"].iloc[0]) if not billing_summary.empty else 0
    rentability_base = (
        float(rentability_summary["facturacion_neta_rentabilidad"].iloc[0])
        if not rentability_summary.empty
        else 0
    )
    ganancia = (
        float(rentability_summary["ganancia_octopus"].iloc[0])
        if not rentability_summary.empty
        else 0
    )
    operaciones_rentabilidad = (
        int(rentability_summary["operaciones"].iloc[0]) if not rentability_summary.empty else 0
    )
    rentabilidad_global = ganancia / rentability_base if rentability_base else None
    facturacion_total_label = money(facturacion_total) if registros_facturacion else "Sin datos confiables"
    rentability_base_label = money(rentability_base) if operaciones_rentabilidad else "Sin datos confiables"
    ganancia_label = money(ganancia) if operaciones_rentabilidad else "Sin datos confiables"
    rentabilidad_label = percent_or_empty(rentabilidad_global)

    st.markdown(
        f"""
        <div class="executive-grid">
          <div class="executive-card">
            <div class="executive-label">Facturacion total</div>
            <div class="executive-number">{executive_value(facturacion_total_label)}</div>
          </div>
          <div class="executive-card">
            <div class="executive-label">Facturacion con rentabilidad</div>
            <div class="executive-number">{executive_value(rentability_base_label)}</div>
          </div>
          <div class="executive-card">
            <div class="executive-label">Ganancia Octopus</div>
            <div class="executive-number">{executive_value(ganancia_label)}</div>
          </div>
          <div class="executive-card">
            <div class="executive-label">Rentabilidad global</div>
            <div class="executive-number">{executive_value(rentabilidad_label)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "Facturacion total es el historico del mes. "
        f"Rentabilidad usa {operaciones_rentabilidad} operaciones validadas."
    )
    st.divider()

    st.subheader("Rankings")
    top_limit = st.radio(
        "Ver",
        options=[5, 10, 20],
        horizontal=True,
        format_func=lambda value: f"Top {value}",
    )
    rentability_top = rentability_ranking(selected_month, top_limit)
    billing_top = billing_ranking(selected_month, top_limit)
    st.markdown(
        f"""
        <div class="rankings-grid">
          <div class="ranking-panel">
            <div class="ranking-panel-title">Por rentabilidad</div>
            {render_rentability_ranking(rentability_top)}
          </div>
          <div class="ranking-panel">
            <div class="ranking-panel-title">Por facturacion</div>
            {render_billing_ranking(billing_top)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

clients = read_sql(
    """
    SELECT
        c.client_key,
        c.display_name,
        MAX(r.operation_date) AS last_operation,
        MAX(r.month) AS last_month,
        COALESCE(GROUP_CONCAT(DISTINCT a.alias_name), '') AS aliases
    FROM clients c
    INNER JOIN rentability_operations r
        ON r.client_key = c.client_key
       AND r.status LIKE 'OK%'
       AND r.billed_amount > 0
       AND r.octopus_profit IS NOT NULL
    LEFT JOIN client_aliases a ON a.official_key = c.client_key
    GROUP BY c.client_key, c.display_name
    ORDER BY c.display_name
    """
)

clients = clients[~clients["client_key"].isin(HIDDEN_CLIENT_KEYS)].copy()

clients["months_without_activity"] = clients["last_month"].map(months_between)
clients["status"] = clients["months_without_activity"].map(
    lambda value: "Activo" if value is not None and value <= 3 else "Inactivo"
)

if clients.empty:
    st.info("Todavia no hay clientes cargados.")
    st.stop()

top_left, top_right = st.columns([3, 1])
with top_left:
    search = st.text_input("Buscar cliente", placeholder="Nombre del cliente")
with top_right:
    if st.button("Actualizar datos"):
        clear_cache()
        st.rerun()

filtered = clients.copy()
if search.strip():
    query = search.strip().lower()
    filtered = filtered[
        filtered["display_name"].str.lower().str.contains(query, na=False)
        | filtered["aliases"].str.lower().str.contains(query, na=False)
        | filtered["status"].str.lower().str.contains(query, na=False)
    ]

left, right = st.columns([1, 2.4])

with left:
    st.subheader("Clientes")
    st.caption(f"{len(filtered)} encontrados")
    if filtered.empty:
        st.info("No hay coincidencias.")
        st.stop()
    selected_name = st.selectbox(
        "Seleccionar",
        options=filtered["client_key"].tolist(),
        format_func=lambda key: clients.loc[clients["client_key"] == key, "display_name"].iloc[0],
        label_visibility="collapsed",
    )

selected = clients.loc[clients["client_key"] == selected_name].iloc[0]
client_key = selected["client_key"]

channel_summary = read_sql(
    """
    SELECT
        channel AS Canal,
        SUM(billed_amount) AS facturacion_neta,
        SUM(octopus_profit) AS ganancia_octopus,
        SUM(octopus_profit) / SUM(billed_amount) AS rentabilidad,
        MAX(month) AS ultimo_mes,
        COUNT(*) AS cuadros_validos
    FROM rentability_operations
    WHERE client_key = ?
      AND status LIKE 'OK%'
      AND billed_amount > 0
      AND octopus_profit IS NOT NULL
    GROUP BY channel
    ORDER BY channel
    """,
    (client_key,),
)

monthly = read_sql(
    """
    SELECT
        month AS Mes,
        channel AS Canal,
        SUM(billed_amount) AS facturacion_neta,
        SUM(octopus_profit) AS ganancia_octopus,
        SUM(octopus_profit) / SUM(billed_amount) AS rentabilidad,
        COUNT(*) AS cuadros_rentabilidad
    FROM rentability_operations
    WHERE client_key = ?
      AND status LIKE 'OK%'
      AND billed_amount > 0
      AND octopus_profit IS NOT NULL
    GROUP BY month, channel
    ORDER BY Mes DESC, Canal
    """,
    (client_key,),
)

trace = read_sql(
    """
    SELECT
        operation_date AS Fecha,
        client_name AS Cliente,
        channel AS Canal,
        check_amount AS ECHEQ,
        billed_amount AS "Facturacion Neta",
        octopus_profit AS Ganancia,
        CASE
            WHEN billed_amount > 0 AND status LIKE 'OK%'
            THEN octopus_profit / billed_amount
            ELSE NULL
        END AS Rentabilidad,
        status AS Estado,
        operation_type AS Tipo,
        reference AS Referencia,
        source_file AS Cuadro,
        source_path AS Archivo,
        note AS Observacion
    FROM rentability_operations
    WHERE client_key = ?
      AND status LIKE 'OK%'
      AND billed_amount > 0
      AND octopus_profit IS NOT NULL
    ORDER BY operation_date DESC, id DESC
    """,
    (client_key,),
)

total_rent_billed = channel_summary["facturacion_neta"].sum() if not channel_summary.empty else 0
total_profit = channel_summary["ganancia_octopus"].sum() if not channel_summary.empty else 0
current_rentability = total_profit / total_rent_billed if total_rent_billed else None
channels = ", ".join(channel_summary["Canal"].dropna().astype(str).unique()) or "Pendiente"
months = ", ".join(monthly["Mes"].dropna().drop_duplicates().sort_values().tolist()) or "Pendiente"
loaded_rentability_cards = int(monthly["cuadros_rentabilidad"].sum()) if not monthly.empty else 0

with right:
    st.subheader(selected["display_name"])
    cards = st.columns(4)
    cards[0].metric("Estado", selected["status"])
    cards[1].metric("Rentabilidad actual", percent(current_rentability))
    cards[2].metric("Facturacion neta", money(total_rent_billed))
    cards[3].metric("Ganancia acumulada", money(total_profit))

    detail_cards = st.columns(4)
    detail_cards[0].metric("Ultima operacion", selected["last_operation"] or "Pendiente")
    detail_cards[1].metric("Ultimo mes", selected["last_month"] or "Pendiente")
    detail_cards[2].metric("Canales", channels)
    detail_cards[3].metric("Meses sin operar", selected["months_without_activity"])

    source_cards = st.columns(1)
    source_cards[0].metric("Cuadros validos", loaded_rentability_cards)

    st.caption("Meses en los que opero")
    st.write(months)

    st.subheader("Canales")
    if channel_summary.empty:
        st.info("Sin datos por canal.")
    else:
        display_channels = channel_summary.copy()
        display_channels["facturacion_neta"] = display_channels["facturacion_neta"].map(money)
        display_channels["ganancia_octopus"] = display_channels["ganancia_octopus"].map(money)
        display_channels["rentabilidad"] = display_channels["rentabilidad"].map(percent)
        st.dataframe(display_channels, use_container_width=True, hide_index=True)

    st.subheader("Datos mensuales")
    if monthly.empty:
        st.info("Sin datos mensuales.")
    else:
        display_monthly = monthly.copy()
        for col in ["facturacion_neta", "ganancia_octopus"]:
            display_monthly[col] = display_monthly[col].map(money)
        display_monthly["rentabilidad"] = display_monthly["rentabilidad"].map(percent)
        st.dataframe(display_monthly, use_container_width=True, hide_index=True)

    st.subheader("Trazabilidad")
    if trace.empty:
        st.info("Sin cuadros cargados para este cliente.")
    else:
        display_trace = trace.copy()
        display_trace["ECHEQ"] = display_trace["ECHEQ"].map(money)
        display_trace["Facturacion Neta"] = display_trace["Facturacion Neta"].map(money)
        display_trace["Ganancia"] = display_trace["Ganancia"].map(money)
        display_trace["Rentabilidad"] = display_trace["Rentabilidad"].map(percent)
        st.dataframe(display_trace, use_container_width=True, hide_index=True)
