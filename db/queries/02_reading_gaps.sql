-- Offline investigation: gaps in each device's series larger than its 2 s cadence.
WITH gaps AS (
    SELECT d.external_id,
           r.metric,
           r.sampled_at,
           r.sampled_at - LAG(r.sampled_at) OVER (
               PARTITION BY r.device_id, r.metric
               ORDER BY r.sampled_at
           ) AS gap
    FROM reading r
    JOIN device d ON d.id = r.device_id
)
SELECT external_id,
       metric,
       sampled_at AS resumed_at,
       gap        AS silent_for
FROM gaps
WHERE gap > INTERVAL '20 seconds'
ORDER BY gap DESC;
