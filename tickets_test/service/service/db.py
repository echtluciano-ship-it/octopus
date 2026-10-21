from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from service.config import settings


@contextmanager
def connection():
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn
