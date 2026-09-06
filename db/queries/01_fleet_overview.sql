-- Fleet health: latest value, last seen, and open anomalies per device.
SELECT d.external_id,
       d.kind,
       d.location,
       lr.metric,
       lr.value            AS last_value,
       lr.sampled_at       AS last_reading,
       hb.last_seen_at,
       COUNT(a.id) FILTER (WHERE a.resolved_at IS NULL) AS open_anomalies
FROM device d
LEFT JOIN device_heartbeat hb ON hb.device_id = d.id
LEFT JOIN LATERAL (
    SELECT metric, value, sampled_at
    FROM reading
    WHERE device_id = d.id
    ORDER BY sampled_at DESC
    LIMIT 1
) lr ON true
LEFT JOIN anomaly a ON a.device_id = d.id
GROUP BY d.id, d.external_id, d.kind, d.location,
         lr.metric, lr.value, lr.sampled_at, hb.last_seen_at
ORDER BY open_anomalies DESC, d.external_id;
