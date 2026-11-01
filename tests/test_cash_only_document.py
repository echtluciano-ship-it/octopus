import sqlite3
from datetime import date

import pandas as pd

from data_loader import reset_schema, manual_rentability_record, insert_manual_rentability
from metrics import validated_without_billing, executive_summary


def test_confirmed_cash_document_keeps_return_amount_without_changing_profitability():
    conn = sqlite3.connect(":memory:")
    reset_schema(conn)
    row = {
        "client_name": "Lumbrera", "channel": "Espora", "received_date": "2026-10-31",
        "check_amount": "39983648", "octopus_profit": "1199509", "net_to_return": "38784139",
        "status": "VALIDADO_SIN_FC_NETA", "source_path": "card.jpg#drive_id_confirmed",
    }
    insert_manual_rentability(conn, manual_rentability_record(row))
    read = lambda q, params=(): pd.read_sql_query(q, conn, params=params)
    shown = validated_without_billing("2026-10", date(2026, 11, 1), read)
    assert shown.iloc[0]["Neto a devolver"] == 38784139
    assert shown.iloc[0]["Ganancia"] == 1199509
    assert validated_without_billing("2026-11", date(2026, 11, 1), read).empty
    assert validated_without_billing("2026-10", date(2026, 10, 30), read).empty
    _, rent = executive_summary("2026-10", date(2026, 11, 1), read)
    assert rent.iloc[0].operaciones == 0
    assert rent.iloc[0].ganancia_octopus == 0
    assert conn.execute("SELECT billed_amount FROM rentability_operations").fetchone()[0] is None
    conn.close()
