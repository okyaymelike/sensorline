-- Sensorline system-of-record schema.

BEGIN;

-- devices (onboarded via simulator/devices.yaml, never hardcoded)
CREATE TABLE IF NOT EXISTS device (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id   TEXT        NOT NULL UNIQUE,
    kind          TEXT        NOT NULL,
    location      TEXT,
    firmware      TEXT,
    config        JSONB       NOT NULL DEFAULT '{}',
    status        TEXT        NOT NULL DEFAULT 'active',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- raw readings, immutable system-of-record.
-- UNIQUE (device_id, metric, sampled_at) is the idempotency key: a redelivered
-- message upserts to a no-op, so at-least-once delivery is safe.
CREATE TABLE IF NOT EXISTS reading (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id     BIGINT      NOT NULL REFERENCES device(id),
    metric        TEXT        NOT NULL,
    value         DOUBLE PRECISION NOT NULL,
    unit          TEXT        NOT NULL,
    sampled_at    TIMESTAMPTZ NOT NULL,               -- device clock
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(), -- platform clock
    source_topic  TEXT        NOT NULL,
    source_offset BIGINT      NOT NULL,
    UNIQUE (device_id, metric, sampled_at)
);
CREATE INDEX IF NOT EXISTS reading_device_time_idx ON reading (device_id, sampled_at DESC);
CREATE INDEX IF NOT EXISTS reading_metric_time_idx ON reading (metric, sampled_at DESC);
-- BRIN for fleet-wide time-range scans: tiny, and effective because readings are
-- appended in sampled_at order. See docs/sql-performance.md (Case 1).
CREATE INDEX IF NOT EXISTS reading_sampled_at_brin ON reading USING brin (sampled_at) WITH (pages_per_range = 32);

-- reading genealogy: one row per stage each reading passes through
-- (ingested -> validated -> enriched -> evaluated).
CREATE TABLE IF NOT EXISTS reading_stage (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reading_id BIGINT      NOT NULL REFERENCES reading(id) ON DELETE CASCADE,
    stage      TEXT        NOT NULL,
    status     TEXT        NOT NULL,   -- ok | warn | reject
    detail     JSONB       NOT NULL DEFAULT '{}',
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reading_stage_reading_idx ON reading_stage (reading_id);
-- Partial index for the processor's evaluated-stage check. See
-- docs/sql-performance.md (Case 4).
CREATE INDEX IF NOT EXISTS reading_stage_evaluated_idx ON reading_stage (reading_id) WHERE stage = 'evaluated';

-- anomalies
CREATE TABLE IF NOT EXISTS anomaly (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_id   BIGINT      NOT NULL REFERENCES device(id),
    reading_id  BIGINT      REFERENCES reading(id),
    type        TEXT        NOT NULL,  -- drift | spike | flatline | offline_gap | out_of_range
    severity    TEXT        NOT NULL,  -- info | warn | critical
    detail      JSONB       NOT NULL DEFAULT '{}',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS anomaly_open_idx
    ON anomaly (device_id, detected_at DESC) WHERE resolved_at IS NULL;

-- device heartbeat (offline detection)
CREATE TABLE IF NOT EXISTS device_heartbeat (
    device_id    BIGINT      PRIMARY KEY REFERENCES device(id),
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_offset  BIGINT      NOT NULL
);

-- processor evaluation cursor: the newest sampled_at evaluated per (device,
-- metric), so the processor bounds each rescan to recent readings instead of
-- re-reading full history. See docs/sql-performance.md (Case 4).
CREATE TABLE IF NOT EXISTS processor_checkpoint (
    device_id       BIGINT      NOT NULL REFERENCES device(id),
    metric          TEXT        NOT NULL,
    last_sampled_at TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, metric)
);

-- consumer offset bookkeeping (lag visibility)
CREATE TABLE IF NOT EXISTS ingest_checkpoint (
    consumer    TEXT        NOT NULL,
    topic       TEXT        NOT NULL,
    partition   INT         NOT NULL,
    last_offset BIGINT      NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, topic, partition)
);

COMMIT;
