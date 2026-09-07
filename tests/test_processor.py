from datetime import UTC, datetime, timedelta

from common import repository as repo
from processor.__main__ import check_fleet_anomalies, evaluate
from processor.settings import MetricThresholds
from tests.conftest import make_device, seed_readings

TEMP = MetricThresholds(valid_range=(-10.0, 60.0), baseline=22.0, spike_sigma=4.0, drift_delta=3.0)


def _anomaly_count(cur, device_id, type_):
    cur.execute(
        "SELECT count(*) FROM anomaly WHERE device_id = %s AND type = %s", (device_id, type_)
    )
    return cur.fetchone()[0]


def test_drift_is_raised(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-drift")
        seed_readings(cur, dev, values=[30.0] * 30)  # mean ~30 vs baseline 22, delta > 3
        check_fleet_anomalies(cur, dev, "temperature_c", TEMP, drift_window=30, gap_seconds=20)
        assert _anomaly_count(cur, dev, "drift") == 1


def test_clean_series_raises_no_drift(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-clean")
        seed_readings(cur, dev, values=[22.0] * 30)  # on baseline
        check_fleet_anomalies(cur, dev, "temperature_c", TEMP, drift_window=30, gap_seconds=20)
        assert _anomaly_count(cur, dev, "drift") == 0


def test_drift_is_not_raised_twice(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-drift-dedup")
        seed_readings(cur, dev, values=[30.0] * 30)
        for _ in range(3):
            check_fleet_anomalies(cur, dev, "temperature_c", TEMP, drift_window=30, gap_seconds=20)
        assert _anomaly_count(cur, dev, "drift") == 1  # idempotent while open


def test_out_of_range_is_raised(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-oor")
        seed_readings(cur, dev, values=[22.0, 22.1, 100.0])  # 100 > 60
        evaluate(cur, dev, "temperature_c", TEMP, spike_window=20)
        assert _anomaly_count(cur, dev, "out_of_range") >= 1


def test_spike_is_raised(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-spike")
        seed_readings(cur, dev, values=[22.0] * 20 + [50.0])  # sharp transient
        evaluate(cur, dev, "temperature_c", TEMP, spike_window=20)
        assert _anomaly_count(cur, dev, "spike") >= 1


def test_offline_gap_is_raised(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-gap")
        now = datetime.now(UTC)
        repo.insert_reading(
            cur, dev, "temperature_c", 22.0, "C", now - timedelta(seconds=120), "t", 0
        )
        repo.insert_reading(
            cur, dev, "temperature_c", 22.0, "C", now - timedelta(seconds=118), "t", 1
        )
        repo.insert_reading(
            cur, dev, "temperature_c", 22.0, "C", now - timedelta(seconds=10), "t", 2
        )
        check_fleet_anomalies(cur, dev, "temperature_c", TEMP, drift_window=30, gap_seconds=20)
        assert _anomaly_count(cur, dev, "offline_gap") == 1


def test_incremental_evaluation_via_checkpoint(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-incr")
        base = datetime.now(UTC) - timedelta(minutes=10)
        seed_readings(cur, dev, values=[22.0] * 25, start=base)
        evaluate(cur, dev, "temperature_c", TEMP, spike_window=20)

        cur.execute(
            "SELECT last_sampled_at FROM processor_checkpoint WHERE device_id=%s AND metric=%s",
            (dev, "temperature_c"),
        )
        assert cur.fetchone() is not None  # checkpoint advanced on first pass

        # newer batch with a spike; a second pass must catch it without re-evaluating
        seed_readings(cur, dev, values=[22.0] * 3 + [50.0], start=datetime.now(UTC))
        evaluate(cur, dev, "temperature_c", TEMP, spike_window=20)

        cur.execute(
            """
            SELECT count(*) FROM reading r
            WHERE r.device_id = %s
              AND NOT EXISTS (SELECT 1 FROM reading_stage s
                              WHERE s.reading_id = r.id AND s.stage = 'evaluated')
            """,
            (dev,),
        )
        assert cur.fetchone()[0] == 0  # nothing left unevaluated

        cur.execute(
            """
            SELECT count(*) FROM reading_stage s
            JOIN reading r ON r.id = s.reading_id
            WHERE r.device_id = %s AND s.stage = 'evaluated'
            """,
            (dev,),
        )
        assert cur.fetchone()[0] == 29  # 25 + 4, each evaluated exactly once
        assert _anomaly_count(cur, dev, "spike") >= 1


def test_evaluate_completes_genealogy(db):
    with db.cursor() as cur:
        dev = make_device(cur, "temp-eval")
        seed_readings(cur, dev, values=[22.0, 22.1, 21.9])
        evaluate(cur, dev, "temperature_c", TEMP, spike_window=20)
        cur.execute(
            """
            SELECT count(*) FROM reading r
            WHERE r.device_id = %s
              AND NOT EXISTS (SELECT 1 FROM reading_stage s
                              WHERE s.reading_id = r.id AND s.stage = 'evaluated')
            """,
            (dev,),
        )
        assert cur.fetchone()[0] == 0  # every reading evaluated
