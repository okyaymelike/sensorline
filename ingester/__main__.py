from __future__ import annotations

import math
import signal
import time
from datetime import UTC, datetime

from confluent_kafka import Consumer, TopicPartition
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from common import repository as repo
from common.config import load_config
from common.messages import Reading
from common.telemetry import extract_context, get_logger, get_tracer, init_logging, init_tracing

CONSUMER_NAME = "ingester"

INGESTED = Counter("ingester_readings_ingested_total", "New readings written", ["device"])
DUPLICATE = Counter("ingester_readings_duplicate_total", "Duplicate readings skipped")
REJECTED = Counter("ingester_readings_rejected_total", "Readings failing validation")
LAST_OFFSET = Gauge("ingester_last_offset", "Last committed offset", ["partition"])
CONSUMER_LAG = Gauge("ingester_consumer_lag", "High watermark minus committed offset", ["partition"])
PROCESS_SECONDS = Histogram(
    "ingester_process_seconds",
    "Time to handle and commit one message",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
INGEST_LAG = Histogram(
    "ingester_ingest_lag_seconds",
    "Platform clock minus device sampled_at at ingest",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
_tracer = get_tracer("sensorline-ingester")
log = get_logger("ingester")

_running = True


def _stop(*_):
    global _running
    _running = False


def valid(reading: Reading) -> tuple[bool, str]:
    if reading.value is None or not math.isfinite(reading.value):
        return False, "non_finite_value"
    if not reading.metric or not reading.unit:
        return False, "missing_metric_or_unit"
    return True, "ok"


def handle(cur, msg, device_cache: dict[str, int]) -> None:
    reading = Reading.from_bytes(msg.value())

    try:
        lag = (datetime.now(UTC) - datetime.fromisoformat(reading.sampled_at)).total_seconds()
        INGEST_LAG.observe(max(0.0, lag))
    except ValueError:
        pass

    device_id = device_cache.get(reading.device_external_id)
    if device_id is None:
        device_id = repo.upsert_device(
            cur,
            reading.device_external_id,
            reading.device_kind,
            reading.location,
            reading.firmware,
        )
        device_cache[reading.device_external_id] = device_id

    reading_id = repo.insert_reading(
        cur,
        device_id,
        reading.metric,
        reading.value,
        reading.unit,
        reading.sampled_at,
        msg.topic(),
        msg.offset(),
    )
    if reading_id is None:
        DUPLICATE.inc()  # duplicate delivery, already stored
        return

    repo.add_stage(cur, reading_id, "ingested", "ok", {"offset": msg.offset()})

    ok, reason = valid(reading)
    if ok:
        repo.add_stage(cur, reading_id, "validated", "ok")
        INGESTED.labels(device=reading.device_external_id).inc()
    else:
        repo.add_stage(cur, reading_id, "validated", "reject", {"reason": reason})
        REJECTED.inc()
        log.warning("reading rejected: device=%s reason=%s", reading.device_external_id, reason)

    repo.upsert_heartbeat(cur, device_id, reading.sampled_at, msg.offset())


def main() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    cfg = load_config()
    init_tracing("sensorline-ingester")
    init_logging("sensorline-ingester")
    start_http_server(cfg.ingester_metrics_port)

    consumer = Consumer(
        {
            "bootstrap.servers": cfg.kafka_bootstrap,
            "group.id": CONSUMER_NAME,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([cfg.topic_readings])

    conn = repo.connect(cfg.database_url)
    device_cache: dict[str, int] = {}
    log.info("ingester consuming topic=%s", cfg.topic_readings)

    try:
        while _running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.error("kafka error: %s", msg.error())
                continue

            # continue the producer's trace: the context rides in the Kafka headers.
            ctx = extract_context(msg.headers())
            started = time.perf_counter()
            with _tracer.start_as_current_span("ingest reading", context=ctx) as span:
                span.set_attribute("partition", msg.partition())
                span.set_attribute("offset", msg.offset())
                with conn.cursor() as cur:
                    handle(cur, msg, device_cache)
                    repo.upsert_checkpoint(
                        cur, CONSUMER_NAME, msg.topic(), msg.partition(), msg.offset()
                    )

                # commit to the DB before acking Kafka, so a crash redelivers rather than loses.
                conn.commit()
                consumer.commit(msg)
                LAST_OFFSET.labels(partition=str(msg.partition())).set(msg.offset())

            PROCESS_SECONDS.observe(time.perf_counter() - started)
            try:
                _, high = consumer.get_watermark_offsets(
                    TopicPartition(msg.topic(), msg.partition()), cached=True
                )
                CONSUMER_LAG.labels(partition=str(msg.partition())).set(
                    max(0, high - (msg.offset() + 1))
                )
            except Exception:
                pass
    finally:
        consumer.close()
        conn.close()
        log.info("ingester stopped")


if __name__ == "__main__":
    main()
