from __future__ import annotations

import sqlite3
import hmac
import os
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "octopus.db"
CURRENT_MONTH = "2026-09"
HIDDEN_CLIENT_KEYS: set[str] = set()


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


if not require_login():
    st.stop()

st.title("Base de Clientes")

if not DB_PATH.exists():
    st.warning("La base todavia no esta cargada.")
    st.stop()

top_left, top_right = st.columns([3, 1])
with top_right:
    if st.button("Actualizar datos"):
        clear_cache()
        st.rerun()

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

with top_left:
    search = st.text_input("Buscar cliente", placeholder="Nombre del cliente")

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
        SUM(billed_amount) AS facturado_rentabilidad,
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
        SUM(billed_amount) AS facturado_rentabilidad,
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
        billed_amount AS Facturado,
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

total_rent_billed = channel_summary["facturado_rentabilidad"].sum() if not channel_summary.empty else 0
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
    cards[2].metric("Facturado en cuadros", money(total_rent_billed))
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
        display_channels["facturado_rentabilidad"] = display_channels["facturado_rentabilidad"].map(money)
        display_channels["ganancia_octopus"] = display_channels["ganancia_octopus"].map(money)
        display_channels["rentabilidad"] = display_channels["rentabilidad"].map(percent)
        st.dataframe(display_channels, use_container_width=True, hide_index=True)

    st.subheader("Datos mensuales")
    if monthly.empty:
        st.info("Sin datos mensuales.")
    else:
        display_monthly = monthly.copy()
        for col in ["facturado_rentabilidad", "ganancia_octopus"]:
            display_monthly[col] = display_monthly[col].map(money)
        display_monthly["rentabilidad"] = display_monthly["rentabilidad"].map(percent)
        st.dataframe(display_monthly, use_container_width=True, hide_index=True)

    st.subheader("Trazabilidad")
    if trace.empty:
        st.info("Sin cuadros cargados para este cliente.")
    else:
        display_trace = trace.copy()
        display_trace["Facturado"] = display_trace["Facturado"].map(money)
        display_trace["Ganancia"] = display_trace["Ganancia"].map(money)
        display_trace["Rentabilidad"] = display_trace["Rentabilidad"].map(percent)
        st.dataframe(display_trace, use_container_width=True, hide_index=True)
