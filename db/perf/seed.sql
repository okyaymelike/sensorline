-- Synthetic bulk data for the query-performance study. NOT real device data.
-- 40 devices, ~30 days of readings at 30s cadence (~3.45M rows), inserted in
-- time order to model append-only telemetry ingestion (needed for BRIN to work).

INSERT INTO device (external_id, kind, location, firmware)
SELECT
    'seed-' || lpad(g::text, 4, '0'),
    CASE WHEN g % 3 = 0 THEN 'vibration' ELSE 'temp-probe' END,
    'rack-' || chr(65 + (g % 8)),
    '1.4.2'
FROM generate_series(1, 40) AS g
ON CONFLICT (external_id) DO NOTHING;

INSERT INTO reading (device_id, metric, value, unit, sampled_at, source_topic, source_offset)
SELECT
    d.id,
    CASE WHEN d.kind = 'vibration' THEN 'vibration_mm_s' ELSE 'temperature_c' END,
    CASE WHEN d.kind = 'vibration' THEN 1.2 + random() ELSE 22 + (random() * 4 - 2) END,
    CASE WHEN d.kind = 'vibration' THEN 'mm/s' ELSE 'C' END,
    ts,
    'telemetry.readings',
    0
FROM device d
CROSS JOIN generate_series(now() - interval '30 days', now(), interval '30 seconds') AS ts
WHERE d.external_id LIKE 'seed-%'
ORDER BY ts;

ANALYZE reading;
ANALYZE device;
