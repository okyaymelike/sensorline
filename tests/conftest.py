import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from common import repository as repo

ROOT = Path(__file__).parent.parent
ADMIN_URL = os.environ.get(
    "DATABASE_URL", "postgresql://telemetry:telemetry@localhost:5434/telemetry"
)
TEST_DB = "telemetry_test"


def _test_url() -> str:
    base, _, _name = ADMIN_URL.rpartition("/")
    return f"{base}/{TEST_DB}"


def _strip_comments(stmt: str) -> str:
    return "\n".join(
        line for line in stmt.splitlines() if not line.strip().startswith("--")
    ).strip()


@pytest.fixture(scope="session")
def test_db_url() -> str:
    # create the test database if it does not exist
    admin = psycopg.connect(ADMIN_URL, autocommit=True)
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()

    # apply schema (idempotent — schema.sql uses IF NOT EXISTS)
    url = _test_url()
    raw = (ROOT / "db" / "schema.sql").read_text()
    conn = psycopg.connect(url, autocommit=True)
    with conn.cursor() as cur:
        for stmt in raw.split(";"):
            core = _strip_comments(stmt)
            if not core or core.upper() in ("BEGIN", "COMMIT"):
                continue
            cur.execute(stmt)
    conn.close()
    return url


@pytest.fixture
def db(test_db_url):
    # each test runs in a transaction that is rolled back, for isolation
    conn = psycopg.connect(test_db_url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ── seeding helpers ────────────────────────────────────────────────────────


def make_device(cur, external_id="dev-x", kind="temp-probe") -> int:
    return repo.upsert_device(cur, external_id, kind, "loc", "fw")


def seed_readings(cur, device_id, values, metric="temperature_c", unit="C", step=2, start=None):
    start = start or datetime.now(UTC) - timedelta(seconds=len(values) * step)
    for i, v in enumerate(values):
        ts = start + timedelta(seconds=i * step)
        repo.insert_reading(cur, device_id, metric, v, unit, ts, "telemetry.readings", i)
