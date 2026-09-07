-- Optimizations from the query-performance study (docs/sql-performance.md).
-- Apply after seeding: psql ... -f db/perf/optimize.sql

-- Case 1: BRIN over the append-only time column. Roughly 70 kB vs ~290 MB for a
-- btree, because telemetry is inserted in sampled_at order (high physical
-- correlation), which is exactly the condition BRIN needs.
CREATE INDEX IF NOT EXISTS reading_sampled_at_brin
    ON reading USING brin (sampled_at) WITH (pages_per_range = 32);

-- Case 4: partial index for the processor's "is this reading evaluated?" check.
-- Only indexes the 'evaluated' stage rows, keeping the EXISTS probe cheap.
CREATE INDEX IF NOT EXISTS reading_stage_evaluated_idx
    ON reading_stage (reading_id) WHERE stage = 'evaluated';

-- Case 3: hourly rollup for dashboard queries. Refresh on a schedule; the unique
-- index lets REFRESH ... CONCURRENTLY run without blocking readers.
CREATE MATERIALIZED VIEW IF NOT EXISTS reading_hourly AS
SELECT device_id,
       date_trunc('hour', sampled_at) AS hour,
       metric,
       avg(value) AS avg_value,
       min(value) AS min_value,
       max(value) AS max_value,
       count(*)   AS n
FROM reading
GROUP BY device_id, date_trunc('hour', sampled_at), metric;

CREATE UNIQUE INDEX IF NOT EXISTS reading_hourly_key
    ON reading_hourly (device_id, metric, hour);
CREATE INDEX IF NOT EXISTS reading_hourly_hour_idx
    ON reading_hourly (hour DESC);

-- Refresh (schedule this; CONCURRENTLY needs the unique index above):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY reading_hourly;
