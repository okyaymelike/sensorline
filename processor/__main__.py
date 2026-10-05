from __future__ import annotations

import signal
import time

from prometheus_client import Counter, Histogram, start_http_server

from common import repository as repo
from common.config import load_config
from common.telemetry import get_logger, init_logging
from processor.settings import MetricThresholds, ProcessorSettings, load_settings

ANOMALIES = Counter("processor_anomalies_total", "Anomalies raised", ["type"])
EVALUATED = Counter("processor_readings_evaluated_total", "Readings evaluated")
CYCLE_SECONDS = Histogram(
    "processor_cycle_seconds",
    "Time to evaluate one full sweep",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
log = get_logger("processor")

_running = True


def _stop(*_):
    global _running
    _running = False


def has_open_anomaly(cur, device_id: int, type_: str) -> bool:
    cur.execute(
        "SELECT 1 FROM anomaly WHERE device_id=%s AND type=%s AND resolved_at IS NULL LIMIT 1",
        (device_id, type_),
    )
    return cur.fetchone() is not None


def device_metric_pairs(cur) -> list[tuple[int, str]]:
    cur.execute("SELECT DISTINCT device_id, metric FROM reading")
    return cur.fetchall()


# Each reading with the mean/std of its own trailing window, so spike detection
# compares a value against its local neighbourhood, not a global mean. `since`
# bounds the scan to recent readings; it must be a concrete value, not a subquery,
# or the planner misestimates and adds JIT + a reading_stage seq scan.
def readings_with_stats(cur, device_id: int, metric: str, spike_window: int, since=None):
    bound = "AND r.sampled_at >= %(since)s" if since is not None else ""
    cur.execute(
        f"""
        SELECT id, value, mean, std, evaluated, sampled_at FROM (
            SELECT r.id,
                   r.value,
                   r.sampled_at,
                   AVG(r.value) OVER w                        AS mean,
                   COALESCE(STDDEV_POP(r.value) OVER w, 0)    AS std,
                   EXISTS(SELECT 1 FROM reading_stage s
                          WHERE s.reading_id = r.id AND s.stage = 'evaluated') AS evaluated
            FROM reading r
            WHERE r.device_id = %(device)s AND r.metric = %(metric)s {bound}
            WINDOW w AS (ORDER BY r.sampled_at ROWS BETWEEN {int(spike_window)} PRECEDING AND CURRENT ROW)
        ) t
        ORDER BY id
        """,
        {"device": device_id, "metric": metric, "since": since},
    )
    return cur.fetchall()


# sampled_at of the row `spike_window` positions at/before the checkpoint, so the
# bounded rescan still carries a full trailing window for the first new reading.
def window_anchor(cur, device_id: int, metric: str, checkpoint, spike_window: int):
    cur.execute(
        """
        SELECT sampled_at FROM reading
        WHERE device_id = %s AND metric = %s AND sampled_at <= %s
        ORDER BY sampled_at DESC
        OFFSET %s LIMIT 1
        """,
        (device_id, metric, checkpoint, spike_window),
    )
    row = cur.fetchone()
    return row[0] if row else None


def recent_mean(cur, device_id: int, metric: str, window: int) -> float | None:
    cur.execute(
        """
        SELECT AVG(value) FROM (
            SELECT value FROM reading
            WHERE device_id = %s AND metric = %s
            ORDER BY sampled_at DESC LIMIT %s
        ) t
        """,
        (device_id, metric, window),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def latest_gap_seconds(cur, device_id: int, metric: str) -> float | None:
    cur.execute(
        """
        SELECT EXTRACT(EPOCH FROM MAX(gap)) FROM (
            SELECT sampled_at - LAG(sampled_at) OVER (ORDER BY sampled_at) AS gap
            FROM reading
            WHERE device_id = %s AND metric = %s
            ORDER BY sampled_at DESC LIMIT 200
        ) g
        """,
        (device_id, metric),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def evaluate(cur, device_id, metric, mt: MetricThresholds, spike_window: int) -> None:
    lo, hi = mt.valid_range
    checkpoint = repo.get_eval_checkpoint(cur, device_id, metric)
    since = window_anchor(cur, device_id, metric, checkpoint, spike_window) if checkpoint else None
    max_sampled = None
    for rid, value, mean, std, evaluated, sampled_at in readings_with_stats(
        cur, device_id, metric, spike_window, since
    ):
        if max_sampled is None or sampled_at > max_sampled:
            max_sampled = sampled_at
        if evaluated:
            continue
        value, mean, std = float(value), float(mean), float(std)
        repo.add_stage(cur, rid, "enriched", "ok", {"mean": round(mean, 3), "std": round(std, 3)})

        if value < lo or value > hi:
            repo.record_anomaly(
                cur, device_id, rid, "out_of_range", "critical", {"value": value, "range": [lo, hi]}
            )
            repo.add_stage(cur, rid, "evaluated", "warn", {"reason": "out_of_range"})
            ANOMALIES.labels(type="out_of_range").inc()
            log.info("anomaly type=out_of_range device=%s metric=%s value=%s", device_id, metric, value)
        elif std > 0 and abs(value - mean) > mt.spike_sigma * std:
            repo.record_anomaly(
                cur,
                device_id,
                rid,
                "spike",
                "warn",
                {"value": value, "mean": round(mean, 3), "sigma": mt.spike_sigma},
            )
            repo.add_stage(cur, rid, "evaluated", "warn", {"reason": "spike"})
            ANOMALIES.labels(type="spike").inc()
            log.info("anomaly type=spike device=%s metric=%s value=%s", device_id, metric, value)
        else:
            repo.add_stage(cur, rid, "evaluated", "ok")
        EVALUATED.inc()

    if max_sampled is not None:
        repo.set_eval_checkpoint(cur, device_id, metric, max_sampled)


def check_fleet_anomalies(
    cur, device_id, metric, mt: MetricThresholds, drift_window: int, gap_seconds: int
) -> None:
    mean = recent_mean(cur, device_id, metric, drift_window)
    if (
        mean is not None
        and abs(mean - mt.baseline) > mt.drift_delta
        and not has_open_anomaly(cur, device_id, "drift")
    ):
        repo.record_anomaly(
            cur,
            device_id,
            None,
            "drift",
            "warn",
            {"recent_mean": round(mean, 3), "baseline": mt.baseline},
        )
        ANOMALIES.labels(type="drift").inc()
        log.info("anomaly type=drift device=%s metric=%s mean=%s", device_id, metric, round(mean, 3))

    gap = latest_gap_seconds(cur, device_id, metric)
    if (
        gap is not None
        and gap > gap_seconds
        and not has_open_anomaly(cur, device_id, "offline_gap")
    ):
        repo.record_anomaly(
            cur, device_id, None, "offline_gap", "critical", {"gap_seconds": round(gap, 1)}
        )
        ANOMALIES.labels(type="offline_gap").inc()
        log.info("anomaly type=offline_gap device=%s metric=%s gap=%s", device_id, metric, round(gap, 1))


def run_cycle(cur, settings: ProcessorSettings) -> None:
    for device_id, metric in device_metric_pairs(cur):
        mt = settings.thresholds.get(metric)
        if mt is None:
            continue
        evaluate(cur, device_id, metric, mt, settings.spike_window)
        check_fleet_anomalies(
            cur, device_id, metric, mt, settings.drift_window, settings.gap_seconds
        )


def main() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    cfg = load_config()
    settings = load_settings()
    init_logging("sensorline-processor")
    start_http_server(cfg.processor_metrics_port)
    conn = repo.connect(cfg.database_url)
    log.info("processor evaluating (cycle=%ss)", settings.cycle_seconds)

    try:
        while _running:
            started = time.perf_counter()
            with conn.cursor() as cur:
                run_cycle(cur, settings)
            conn.commit()
            CYCLE_SECONDS.observe(time.perf_counter() - started)
            time.sleep(settings.cycle_seconds)
    finally:
        conn.close()
        log.info("processor stopped")


if __name__ == "__main__":
    main()
