-- Case-study queries for the performance write-up. Run each under
-- EXPLAIN (ANALYZE, BUFFERS); see docs/sql-performance.md for the numbers.

-- === Case 1: fleet-wide time-range aggregate ===
-- Filters on sampled_at alone (no device/metric), so no leading-column btree
-- helps. Seq scan before BRIN, bitmap scan after.
SELECT metric, count(*), avg(value)
FROM reading
WHERE sampled_at BETWEEN now() - interval '3 days' AND now() - interval '2 days'
GROUP BY metric;

-- === Case 2: latest reading per (device, metric) ===
-- 2a naive: correlated subquery runs a lookup per row.
SELECT r.device_id, r.metric, r.value, r.sampled_at
FROM reading r
WHERE r.sampled_at = (
    SELECT max(r2.sampled_at)
    FROM reading r2
    WHERE r2.device_id = r.device_id AND r2.metric = r.metric
);

-- 2b rewrite: DISTINCT ON. Correct, but sorts the whole table.
SELECT DISTINCT ON (device_id, metric) device_id, metric, value, sampled_at
FROM reading
ORDER BY device_id, metric, sampled_at DESC;

-- 2c best: LATERAL index-seek per device. Few devices x one index seek each,
-- using reading_device_time_idx; never scans the table.
SELECT d.id AS device_id, lr.metric, lr.value, lr.sampled_at
FROM device d
CROSS JOIN LATERAL (
    SELECT metric, value, sampled_at
    FROM reading r
    WHERE r.device_id = d.id
    ORDER BY sampled_at DESC
    LIMIT 1
) lr;

-- === Case 3: hourly rollup for dashboards ===
-- 3a on-the-fly: recomputes every dashboard load.
SELECT device_id, date_trunc('hour', sampled_at) AS hour, metric,
       avg(value), min(value), max(value), count(*)
FROM reading
WHERE sampled_at >= now() - interval '7 days'
GROUP BY device_id, hour, metric;

-- 3b materialized: read precomputed rows (see optimize.sql).
SELECT device_id, hour, metric, avg_value, min_value, max_value, n
FROM reading_hourly
WHERE hour >= now() - interval '7 days';

-- === Case 4: the processor's own evaluation query (readings_with_stats) ===
-- Fill in :device / :metric / :since. 4a is the query as processor/__main__.py
-- issues it (full history); 4b is the bounded form it should issue.

-- 4a as-written: windows the whole per-device history every cycle.
SELECT id, value, mean, std, evaluated FROM (
    SELECT r.id, r.value,
           AVG(r.value) OVER w AS mean,
           COALESCE(STDDEV_POP(r.value) OVER w, 0) AS std,
           EXISTS(SELECT 1 FROM reading_stage s
                  WHERE s.reading_id = r.id AND s.stage = 'evaluated') AS evaluated
    FROM reading r
    WHERE r.device_id = :device AND r.metric = :metric
    WINDOW w AS (ORDER BY r.sampled_at ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
) t ORDER BY id;

-- 4b bounded: pass a concrete `since` (last-evaluated ts or now()-lookback).
-- The bound must be a literal/parameter, NOT a (SELECT max(...)) subquery, or the
-- planner misestimates and adds JIT + a reading_stage seq scan.
SELECT id, value, mean, std, evaluated FROM (
    SELECT r.id, r.value,
           AVG(r.value) OVER w AS mean,
           COALESCE(STDDEV_POP(r.value) OVER w, 0) AS std,
           EXISTS(SELECT 1 FROM reading_stage s
                  WHERE s.reading_id = r.id AND s.stage = 'evaluated') AS evaluated
    FROM reading r
    WHERE r.device_id = :device AND r.metric = :metric
      AND r.sampled_at >= :since
    WINDOW w AS (ORDER BY r.sampled_at ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
) t ORDER BY id;
