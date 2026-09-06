-- Genealogy: every stage a single reading passed through. Replace 123 with a reading id.
SELECT r.id AS reading_id,
       d.external_id,
       r.metric,
       r.value,
       r.sampled_at,
       s.stage,
       s.status,
       s.detail,
       s.at
FROM reading r
JOIN device d ON d.id = r.device_id
JOIN reading_stage s ON s.reading_id = r.id
WHERE r.id = 123
ORDER BY s.at;
