# Incident 02 — temp-02 stopped reporting

**Reproduce:** `python -m simulator --backfill-minutes 15 --scenario offline_gap`
(then run the ingester and processor).

## Symptom

`01_fleet_overview.sql` showed `temp-02` with a `last_reading` timestamp well
behind the rest of the fleet, and an open `offline_gap` anomaly. The device was
not producing — but the question is always *when, and for how long*.

## Investigation

Ran `02_reading_gaps.sql`, which uses `LAG` over each device's series to measure
the interval between consecutive readings:

```
external_id   metric           resumed_at        silent_for
temp-02       temperature_c    ...:01:42         00:01:00
```

One gap of ~60 s against a 2 s nominal cadence — the device went quiet and then
resumed cleanly, so this was an outage, not a permanent failure.

Cross-checked with `06_ingest_freshness.sql`: during the gap, temp-02's
`staleness` grew while temp-01 and vib-01 stayed fresh. That isolates the fault
to the device, **not** the ingester or Kafka — a pipeline-side stall would have
made *every* device stale at once.

## Root cause

Simulated device offline for 60 s starting ~40 s in. In the field this is a
dropped network link or a device reboot.

## Resolution

The processor raised a critical `offline_gap` anomaly with the gap duration in
its detail. Because ingestion is idempotent and offset-tracked, readings
produced after the device came back were ingested normally with no duplicates
and no manual replay.

## Takeaway

The per-device staleness comparison is what separates "one device is down" from
"the pipeline is down" — the first question to answer in any missing-data page,
and it's a single query.
