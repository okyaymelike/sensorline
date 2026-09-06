-- Ingestion health: per-device staleness, and consumer offsets.
SELECT d.external_id,
       hb.last_seen_at,
       now() - hb.last_seen_at AS staleness
FROM device d
LEFT JOIN device_heartbeat hb ON hb.device_id = d.id
ORDER BY staleness DESC NULLS FIRST;

SELECT consumer, topic, partition, last_offset, updated_at
FROM ingest_checkpoint
ORDER BY topic, partition;
