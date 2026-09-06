-- Anomaly Pareto: counts by type and severity, open vs total.
SELECT a.type,
       a.severity,
       COUNT(*)                                      AS total,
       COUNT(*) FILTER (WHERE a.resolved_at IS NULL) AS still_open,
       COUNT(DISTINCT a.device_id)                   AS devices_affected
FROM anomaly a
GROUP BY a.type, a.severity
ORDER BY total DESC;
