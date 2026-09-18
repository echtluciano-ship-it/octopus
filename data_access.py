from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).resolve().parent / "octopus.db"


def business_today() -> date:
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def database_revision(path: Path = DB_PATH) -> tuple:
    # Include WAL commits and atomic replacements, not only the file size.
    parts = []
    for candidate in (Path(path), Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
            parts.append((stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
        except FileNotFoundError:
            parts.append(None)
    return tuple(parts)


@st.cache_data(show_spinner=False, max_entries=512)
def _read_sql(query: str, params: tuple, db_uri: str, revision: tuple) -> pd.DataFrame:
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        return pd.read_sql_query(query, conn, params=params)


def read_sql(query: str, params: tuple = (), db_path: Path = DB_PATH) -> pd.DataFrame:
    path = Path(db_path).resolve()
    return _read_sql(query, params, path.as_uri() + "?mode=ro", database_revision(path))


def clear_cache() -> None:
    _read_sql.clear()
