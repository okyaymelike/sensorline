from datetime import UTC, datetime

from common import repository as repo
from tests.conftest import make_device


def test_insert_reading_is_idempotent(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-idem")
        ts = datetime.now(UTC)

        first = repo.insert_reading(cur, dev, "temperature_c", 22.0, "C", ts, "t", 0)
        second = repo.insert_reading(cur, dev, "temperature_c", 22.0, "C", ts, "t", 1)

        assert first is not None  # first insert wins
        assert second is None  # same key → no-op
        cur.execute("SELECT count(*) FROM reading WHERE device_id = %s", (dev,))
        assert cur.fetchone()[0] == 1  # exactly one row


def test_upsert_device_returns_same_id(db):
    with db.cursor() as cur:
        a = repo.upsert_device(cur, "dev-a", "temp-probe", "loc", "fw")
        b = repo.upsert_device(cur, "dev-a", "temp-probe", "loc", "fw")
        assert a == b


def test_add_stage_records_genealogy(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-stage")
        ts = datetime.now(UTC)
        rid = repo.insert_reading(cur, dev, "temperature_c", 22.0, "C", ts, "t", 0)
        repo.add_stage(cur, rid, "ingested", "ok", {"offset": 0})
        repo.add_stage(cur, rid, "validated", "ok")

        cur.execute("SELECT stage FROM reading_stage WHERE reading_id = %s ORDER BY at", (rid,))
        assert [r[0] for r in cur.fetchall()] == ["ingested", "validated"]
