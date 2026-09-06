-- Drift investigation: rolling 10-sample mean vs the raw value for temp-01.
SELECT d.external_id,
       r.sampled_at,
       r.value,
       ROUND(AVG(r.value) OVER (
           PARTITION BY r.device_id
           ORDER BY r.sampled_at
           ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
       )::numeric, 3) AS rolling_mean_10
FROM reading r
JOIN device d ON d.id = r.device_id
WHERE d.external_id = 'temp-01'
  AND r.metric = 'temperature_c'
ORDER BY r.sampled_at;
