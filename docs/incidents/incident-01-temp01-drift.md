# Incident 01 — temp-01 reading high (calibration drift)

**Reproduce:** `python -m simulator --backfill-minutes 15 --scenario drift`
(then run the ingester and processor over the backfilled data).

## Symptom

`01_fleet_overview.sql` showed `temp-01` with an open anomaly and a last value
around 28–30 °C while `temp-02`, same rack type, sat near 21.5 °C. No single
reading was wildly wrong, so nothing tripped a hard range check at first.

## Investigation

Ran `03_drift_vs_baseline.sql` for temp-01. The raw values were noisy but the
**rolling 10-sample mean climbed steadily** away from the 22.0 °C baseline:

```
sampled_at            value   rolling_mean_10
...:30                22.1    22.0
...:60                23.6    22.7
...:90                25.0    23.9
...:120               26.7    25.2
```

The climb is monotonic and roughly linear — the signature of drift, not a
transient. temp-02 over the same window stayed flat, ruling out an
environmental cause common to the rack.

Genealogy on the first flagged reading (`04_reading_genealogy.sql`) confirmed it
passed `validated=ok` (the value was in range) but `evaluated` recorded the
window mean already sitting above baseline.

## Root cause

Simulated calibration drift on temp-01 beginning ~30 s in, +1.5 °C/min. In the
real world this is the classic "sensor warms up and reads high" fault — the
reason a single-threshold alarm is not enough and you need drift-against-baseline.

## Resolution

The processor raised a `drift` anomaly once the rolling mean exceeded baseline by
the 3 °C threshold — **before** any reading became individually out-of-range,
which is the point. Action in production would be to recalibrate or swap the
probe; the anomaly stays open until the mean returns to baseline.

## Takeaway

Point checks alone miss slow faults. The window detector plus the
baseline-vs-rolling-mean query is what catches drift while it's still small.
