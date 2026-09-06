# Architecture & design decisions

This document explains *why* the pipeline is built the way it is — the parts
that aren't obvious from reading the code.

## Delivery semantics: at-least-once + idempotent write

Kafka gives at-least-once delivery: after a crash or rebalance, the last
message can be redelivered. Rather than chase exactly-once at the broker (which
is expensive and still needs idempotent sinks), the pipeline **makes the write
idempotent** and accepts redelivery.

The idempotency key is the `reading (device_id, metric, sampled_at)` unique
constraint. Ingest is `INSERT ... ON CONFLICT DO NOTHING RETURNING id`:

- returns an id → first time we've seen this reading; record its genealogy.
- returns nothing → a duplicate; count it and move on.

So replaying a partition never double-counts and never double-stages.

## Commit ordering

Per message the ingester does:

1. write the reading + genealogy inside one DB transaction,
2. `conn.commit()` — durable,
3. `consumer.commit(msg)` — acknowledge to Kafka.

The order is deliberate. If the process dies between (2) and (3), Kafka
redelivers and step 1 hits the `ON CONFLICT` no-op — safe. If we committed to
Kafka *first* and then crashed before the DB write, the reading would be lost.
Durable-store-before-acknowledge is the rule.

## Why split ingester and processor

The ingester is the hot path: it must keep up with the topic, so it only does
cheap, per-message work (write + structural validation + heartbeat). Anything
that needs **history** — rolling statistics, drift, gap detection — needs a
window of prior readings and is pushed to the processor, which runs on its own
cadence and can fall behind without backpressuring ingestion.

This also keeps the genealogy honest: `ingested`/`validated` are stamped by the
ingester, `enriched`/`evaluated` by the processor. The stage trail shows which
component touched each reading and when.

## Idempotent detection

Re-evaluating the same readings must not spam anomalies. Two guards:

- the processor only enriches/evaluates readings that lack an `evaluated`
  stage, so backlog is processed once.
- window-level detectors (drift, offline gap) check for a still-open anomaly of
  the same type before raising a new one.

Running the processor repeatedly over the same data is therefore a no-op after
the first pass — important for a worker that restarts.

## Backpressure & ordering

Readings are keyed by `device_external_id`, so all readings from one device
land on the same partition and stay ordered per device. Across devices, order
is not guaranteed and does not need to be. Scaling out is a matter of adding
partitions and ingester instances in the same consumer group; the DB unique
constraint keeps them from stepping on each other.

## Failure modes considered

| Failure | Behaviour |
|---|---|
| Ingester crash mid-message | Kafka redelivers; `ON CONFLICT` absorbs the duplicate. |
| Duplicate delivery | Counted (`ingester_readings_duplicate_total`), not re-stored. |
| Malformed / non-finite value | Stored, staged `validated=reject` with a reason — visible, not silently dropped. |
| Device goes silent | Gap surfaces via `02_reading_gaps.sql`; processor raises `offline_gap`. |
| Slow calibration drift | Rolling mean diverges from baseline; processor raises `drift` before any single reading is out of range. |
| Processor restart | Only unevaluated readings are picked up; open anomalies are not re-raised. |

## What is deliberately out of scope (for now)

- Exactly-once via Kafka transactions — the idempotent sink makes it
  unnecessary at this scale.
- Auto-resolution of anomalies — they're raised and left open; closing them is
  a follow-up once the UI exists.
- Horizontal processor sharding — single processor is sufficient for the
  current fleet; the device-keyed partitioning already allows it later.
