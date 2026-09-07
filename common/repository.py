from __future__ import annotations

from typing import Any

import psycopg


def connect(database_url: str) -> psycopg.Connection:
    # autocommit off: one consumed message = one transaction.
    return psycopg.connect(database_url, autocommit=False)


def upsert_device(
    cur: psycopg.Cursor,
    external_id: str,
    kind: str,
    location: str | None,
    firmware: str | None,
) -> int:
    cur.execute(
        """
        INSERT INTO device (external_id, kind, location, firmware)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (external_id) DO UPDATE
            SET kind     = EXCLUDED.kind,
                location = COALESCE(EXCLUDED.location, device.location),
                firmware = COALESCE(EXCLUDED.firmware, device.firmware)
        RETURNING id
        """,
        (external_id, kind, location, firmware),
    )
    return cur.fetchone()[0]


# Returns the new reading id, or None if it was a duplicate.
# The (device_id, metric, sampled_at) unique constraint is the idempotency key.
def insert_reading(
    cur: psycopg.Cursor,
    device_id: int,
    metric: str,
    value: float,
    unit: str,
    sampled_at: str,
    source_topic: str,
    source_offset: int,
) -> int | None:
    cur.execute(
        """
        INSERT INTO reading
            (device_id, metric, value, unit, sampled_at, source_topic, source_offset)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_id, metric, sampled_at) DO NOTHING
        RETURNING id
        """,
        (device_id, metric, value, unit, sampled_at, source_topic, source_offset),
    )
    row = cur.fetchone()
    return row[0] if row else None


def add_stage(
    cur: psycopg.Cursor,
    reading_id: int,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        "INSERT INTO reading_stage (reading_id, stage, status, detail) VALUES (%s, %s, %s, %s)",
        (reading_id, stage, status, psycopg.types.json.Json(detail or {})),
    )


def record_anomaly(
    cur: psycopg.Cursor,
    device_id: int,
    reading_id: int | None,
    type_: str,
    severity: str,
    detail: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        "INSERT INTO anomaly (device_id, reading_id, type, severity, detail) VALUES (%s, %s, %s, %s, %s)",
        (device_id, reading_id, type_, severity, psycopg.types.json.Json(detail or {})),
    )


def upsert_heartbeat(cur: psycopg.Cursor, device_id: int, seen_at: str, offset_: int) -> None:
    cur.execute(
        """
        INSERT INTO device_heartbeat (device_id, last_seen_at, last_offset)
        VALUES (%s, %s, %s)
        ON CONFLICT (device_id) DO UPDATE
            SET last_seen_at = EXCLUDED.last_seen_at,
                last_offset  = EXCLUDED.last_offset
        """,
        (device_id, seen_at, offset_),
    )


def get_eval_checkpoint(cur: psycopg.Cursor, device_id: int, metric: str):
    cur.execute(
        "SELECT last_sampled_at FROM processor_checkpoint WHERE device_id = %s AND metric = %s",
        (device_id, metric),
    )
    row = cur.fetchone()
    return row[0] if row else None


def set_eval_checkpoint(cur: psycopg.Cursor, device_id: int, metric: str, sampled_at) -> None:
    cur.execute(
        """
        INSERT INTO processor_checkpoint (device_id, metric, last_sampled_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (device_id, metric) DO UPDATE
            SET last_sampled_at = EXCLUDED.last_sampled_at,
                updated_at      = now()
        """,
        (device_id, metric, sampled_at),
    )


def upsert_checkpoint(
    cur: psycopg.Cursor, consumer: str, topic: str, partition: int, offset_: int
) -> None:
    cur.execute(
        """
        INSERT INTO ingest_checkpoint (consumer, topic, partition, last_offset)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (consumer, topic, partition) DO UPDATE
            SET last_offset = EXCLUDED.last_offset,
                updated_at  = now()
        """,
        (consumer, topic, partition, offset_),
    )
