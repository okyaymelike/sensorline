from __future__ import annotations

from typing import Any

from .db import fetch_all, fetch_one

# Read-only queries. These are the db/queries/01-06 investigation queries,
# parameterised and generalised (no hardcoded device / reading id).


def list_devices() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT d.external_id, d.kind, d.location, d.firmware,
               COALESCE(
                   array_agg(DISTINCT r.metric) FILTER (WHERE r.metric IS NOT NULL),
                   '{}'
               ) AS metrics
        FROM device d
        LEFT JOIN reading r ON r.device_id = d.id
        WHERE EXISTS (SELECT 1 FROM device_heartbeat h WHERE h.device_id = d.id)
        GROUP BY d.id, d.external_id, d.kind, d.location, d.firmware
        ORDER BY d.external_id
        """
    )


def fleet() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT d.external_id, d.kind, d.location,
               lr.metric, lr.value AS last_value, lr.unit,
               lr.sampled_at AS last_reading,
               hb.last_seen_at,
               EXTRACT(EPOCH FROM (now() - hb.last_seen_at))::float8 AS staleness_s,
               COUNT(a.id) FILTER (WHERE a.resolved_at IS NULL) AS open_anomalies
        FROM device d
        LEFT JOIN device_heartbeat hb ON hb.device_id = d.id
        LEFT JOIN LATERAL (
            SELECT metric, value, unit, sampled_at
            FROM reading
            WHERE device_id = d.id
            ORDER BY sampled_at DESC
            LIMIT 1
        ) lr ON true
        LEFT JOIN anomaly a ON a.device_id = d.id
        WHERE hb.last_seen_at IS NOT NULL
        GROUP BY d.id, d.external_id, d.kind, d.location,
                 lr.metric, lr.value, lr.unit, lr.sampled_at, hb.last_seen_at
        ORDER BY open_anomalies DESC, d.external_id
        """
    )


def default_metric(external_id: str) -> str | None:
    row = fetch_one(
        """
        SELECT r.metric
        FROM reading r JOIN device d ON d.id = r.device_id
        WHERE d.external_id = %s
        ORDER BY r.sampled_at DESC
        LIMIT 1
        """,
        (external_id,),
    )
    return row["metric"] if row else None


def series(external_id: str, metric: str, limit: int) -> list[dict[str, Any]]:
    # last `limit` readings, oldest-first, with a trailing 10-sample rolling mean
    # (the baseline band in db/queries/03).
    return fetch_all(
        """
        WITH recent AS (
            SELECT r.sampled_at, r.value
            FROM reading r JOIN device d ON d.id = r.device_id
            WHERE d.external_id = %s AND r.metric = %s
            ORDER BY r.sampled_at DESC
            LIMIT %s
        )
        SELECT sampled_at,
               value::float8 AS value,
               ROUND(
                   AVG(value) OVER (
                       ORDER BY sampled_at
                       ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                   )::numeric, 3
               )::float8 AS rolling_mean_10
        FROM recent
        ORDER BY sampled_at ASC
        """,
        (external_id, metric, limit),
    )


def device_anomalies(external_id: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT a.id, a.reading_id, a.type, a.severity, a.detail,
               a.detected_at, a.resolved_at,
               r.sampled_at AS reading_sampled_at,
               r.value::float8 AS reading_value
        FROM anomaly a
        JOIN device d ON d.id = a.device_id
        LEFT JOIN reading r ON r.id = a.reading_id
        WHERE d.external_id = %s
        ORDER BY a.detected_at DESC
        """,
        (external_id,),
    )


def genealogy(reading_id: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT r.id AS reading_id, d.external_id, r.metric, r.value::float8 AS value,
               r.sampled_at, s.stage, s.status, s.detail, s.at
        FROM reading r
        JOIN device d ON d.id = r.device_id
        JOIN reading_stage s ON s.reading_id = r.id
        WHERE r.id = %s
        ORDER BY s.at
        """,
        (reading_id,),
    )


def anomaly_pareto() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT a.type, a.severity,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.resolved_at IS NULL) AS still_open,
               COUNT(DISTINCT a.device_id) AS devices_affected
        FROM anomaly a
        WHERE EXISTS (SELECT 1 FROM device_heartbeat h WHERE h.device_id = a.device_id)
        GROUP BY a.type, a.severity
        ORDER BY total DESC
        """
    )


def recent_anomalies(limit: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT d.external_id, a.type, a.severity, a.detected_at, a.resolved_at
        FROM anomaly a JOIN device d ON d.id = a.device_id
        WHERE EXISTS (SELECT 1 FROM device_heartbeat h WHERE h.device_id = a.device_id)
        ORDER BY a.detected_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def freshness() -> dict[str, Any]:
    staleness = fetch_all(
        """
        SELECT d.external_id,
               hb.last_seen_at,
               EXTRACT(EPOCH FROM (now() - hb.last_seen_at))::float8 AS staleness_s
        FROM device d
        JOIN device_heartbeat hb ON hb.device_id = d.id
        ORDER BY staleness_s DESC NULLS FIRST
        """
    )
    consumers = fetch_all(
        """
        SELECT consumer, topic, partition, last_offset, updated_at
        FROM ingest_checkpoint
        ORDER BY topic, partition
        """
    )
    return {"staleness": staleness, "consumers": consumers}
