from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from common.telemetry import get_tracer

load_dotenv()

_pool: ConnectionPool | None = None
_tracer = get_tracer("sensorline-api.db")


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env (or export DATABASE_URL)."
        )
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(_database_url(), min_size=1, max_size=5, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with _tracer.start_as_current_span("db.query") as span:
        span.set_attribute("db.system", "postgresql")
        with get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def fetch_one(sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    with _tracer.start_as_current_span("db.query") as span:
        span.set_attribute("db.system", "postgresql")
        with get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
