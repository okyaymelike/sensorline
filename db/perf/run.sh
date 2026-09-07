#!/usr/bin/env bash
# Reproduces the query-performance study against the docker compose Postgres.
# Run from the sensorline repo root with the stack up: bash db/perf/run.sh
set -euo pipefail

DB_USER="${POSTGRES_USER:-telemetry}"
DB_NAME="${POSTGRES_DB:-telemetry}"
run() { docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" "$@"; }
explain() { run -c "EXPLAIN (ANALYZE, BUFFERS) $1" >/dev/null; run -c "EXPLAIN (ANALYZE, BUFFERS) $1" | grep -E "$2|Execution Time" || true; }

rows=$(run -tA -c "SELECT count(*) FROM reading;")
if [ "$rows" -lt 1000000 ]; then
    echo ">> seeding bulk data (~30-90s)..."
    run -q -f - < db/perf/seed.sql
fi
echo ">> readings: $(run -tA -c 'SELECT count(*) FROM reading;')"

echo; echo "=== Case 1: fleet-wide time-range aggregate (BRIN) ==="
Q1="SELECT metric, count(*), avg(value) FROM reading WHERE sampled_at BETWEEN now() - interval '3 days' AND now() - interval '2 days' GROUP BY metric;"
run -c "DROP INDEX IF EXISTS reading_sampled_at_brin;" >/dev/null
echo "-- before --"; explain "$Q1" "Seq Scan|Bitmap"
run -c "CREATE INDEX reading_sampled_at_brin ON reading USING brin (sampled_at) WITH (pages_per_range=32);" >/dev/null
run -c "ANALYZE reading;" >/dev/null
echo "-- after --"; explain "$Q1" "Seq Scan|Bitmap"

echo; echo "=== Case 2: latest reading per device (rewrite) ==="
Q2A="SELECT r.device_id, r.metric, r.value, r.sampled_at FROM reading r WHERE r.sampled_at = (SELECT max(r2.sampled_at) FROM reading r2 WHERE r2.device_id = r.device_id AND r2.metric = r.metric);"
Q2C="SELECT d.id, lr.metric, lr.value, lr.sampled_at FROM device d CROSS JOIN LATERAL (SELECT metric, value, sampled_at FROM reading r WHERE r.device_id = d.id ORDER BY sampled_at DESC LIMIT 1) lr;"
echo "-- 2a correlated subquery --"; explain "$Q2A" "Seq Scan|SubPlan"
echo "-- 2c LATERAL index-seek --"; explain "$Q2C" "Nested Loop|Index Scan"

echo; echo "=== Case 3: hourly rollup (materialized view) ==="
Q3A="SELECT device_id, date_trunc('hour', sampled_at) AS hour, metric, avg(value), min(value), max(value), count(*) FROM reading WHERE sampled_at >= now() - interval '7 days' GROUP BY device_id, hour, metric;"
Q3B="SELECT device_id, hour, metric, avg_value FROM reading_hourly WHERE hour >= now() - interval '7 days';"
echo "-- before (on-the-fly) --"; explain "$Q3A" "Aggregate|Bitmap|Seq Scan"
run -f - < db/perf/optimize.sql >/dev/null
run -c "ANALYZE reading_hourly;" >/dev/null
echo "-- after (materialized view) --"; explain "$Q3B" "reading_hourly|Index"

echo; echo "=== Case 4: processor evaluation query (real hot path) ==="
DEV=$(run -tA -c "SELECT id FROM device WHERE external_id='seed-0001';")
MET="temperature_c"
if [ -n "$DEV" ]; then
    # model steady state: evaluate all but this device's most recent 100 readings
    run -c "INSERT INTO reading_stage (reading_id, stage, status)
            SELECT r.id, 'evaluated', 'ok' FROM reading r
            WHERE r.device_id=$DEV AND r.metric='$MET'
              AND NOT EXISTS (SELECT 1 FROM reading_stage s WHERE s.reading_id=r.id AND s.stage='evaluated')
              AND r.id NOT IN (SELECT id FROM reading WHERE device_id=$DEV AND metric='$MET' ORDER BY sampled_at DESC LIMIT 100);" >/dev/null
    run -f - < db/perf/optimize.sql >/dev/null
    run -c "ANALYZE reading_stage;" >/dev/null
    SINCE=$(run -tA -c "SELECT max(sampled_at) - interval '60 minutes' FROM reading WHERE device_id=$DEV AND metric='$MET';")
    Q4A="SELECT id, value, mean, std, evaluated FROM (SELECT r.id, r.value, AVG(r.value) OVER w AS mean, COALESCE(STDDEV_POP(r.value) OVER w,0) AS std, EXISTS(SELECT 1 FROM reading_stage s WHERE s.reading_id=r.id AND s.stage='evaluated') AS evaluated FROM reading r WHERE r.device_id=$DEV AND r.metric='$MET' WINDOW w AS (ORDER BY r.sampled_at ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)) t ORDER BY id;"
    Q4B="SELECT id, value, mean, std, evaluated FROM (SELECT r.id, r.value, AVG(r.value) OVER w AS mean, COALESCE(STDDEV_POP(r.value) OVER w,0) AS std, EXISTS(SELECT 1 FROM reading_stage s WHERE s.reading_id=r.id AND s.stage='evaluated') AS evaluated FROM reading r WHERE r.device_id=$DEV AND r.metric='$MET' AND r.sampled_at >= TIMESTAMPTZ '$SINCE' WINDOW w AS (ORDER BY r.sampled_at ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)) t ORDER BY id;"
    echo "-- before (full history) --"; explain "$Q4A" "WindowAgg|Seq Scan|Bitmap|Sort"
    echo "-- after (bounded + partial index) --"; explain "$Q4B" "WindowAgg|Index Scan|Index Only"
fi
