from __future__ import annotations

import math
import signal

from confluent_kafka import Consumer
from prometheus_client import Counter, Gauge, start_http_server

from common import repository as repo
from common.config import load_config
from common.messages import Reading

CONSUMER_NAME = "ingester"

INGESTED = Counter("ingester_readings_ingested_total", "New readings written", ["device"])
DUPLICATE = Counter("ingester_readings_duplicate_total", "Duplicate readings skipped")
REJECTED = Counter("ingester_readings_rejected_total", "Readings failing validation")
LAST_OFFSET = Gauge("ingester_last_offset", "Last committed offset", ["partition"])

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

    repo.upsert_heartbeat(cur, device_id, reading.sampled_at, msg.offset())


def main() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    cfg = load_config()
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
    print(f"ingester consuming '{cfg.topic_readings}' — ctrl-c to stop")

    try:
        while _running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"kafka error: {msg.error()}")
                continue

            with conn.cursor() as cur:
                handle(cur, msg, device_cache)
                repo.upsert_checkpoint(
                    cur, CONSUMER_NAME, msg.topic(), msg.partition(), msg.offset()
                )

            # commit to the DB before acking Kafka, so a crash redelivers rather than loses.
            conn.commit()
            consumer.commit(msg)
            LAST_OFFSET.labels(partition=str(msg.partition())).set(msg.offset())
    finally:
        consumer.close()
        conn.close()
        print("\ningester stopped")


if __name__ == "__main__":
    main()
