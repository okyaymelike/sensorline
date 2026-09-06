from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from confluent_kafka import Producer
from prometheus_client import Counter, start_http_server

from common.config import load_config
from common.messages import Reading

EMITTED = Counter("simulator_readings_emitted_total", "Readings emitted", ["device"])


def load_fleet() -> tuple[list[dict], dict]:
    doc = yaml.safe_load((Path(__file__).parent / "devices.yaml").read_text())
    return doc["devices"], doc.get("scenarios", {})


# Returns (value_offset, suppress). suppress=True means the device is offline.
def fault_offset(dev: dict, scenario: dict | None, elapsed: float) -> tuple[float, bool]:
    if not scenario or scenario.get("device") != dev["external_id"]:
        return 0.0, False
    after = scenario.get("after_seconds", 0)
    if elapsed < after:
        return 0.0, False

    kind = scenario["type"]
    if kind == "drift":
        minutes = (elapsed - after) / 60.0
        return scenario["rate_per_min"] * minutes, False
    if kind == "offline":
        return 0.0, (elapsed - after) < scenario.get("duration_seconds", 60)
    if kind == "spike":
        if 0 <= (elapsed - after) < dev["interval_seconds"]:
            return scenario["magnitude"], False
    return 0.0, False


def make_value(dev: dict, offset: float) -> float:
    return round(dev["baseline"] + random.gauss(0, dev["noise"]) + offset, 3)


def build_reading(dev: dict, value: float, sampled_at: datetime) -> Reading:
    return Reading(
        device_external_id=dev["external_id"],
        device_kind=dev["kind"],
        metric=dev["metric"],
        value=value,
        unit=dev["unit"],
        sampled_at=sampled_at.isoformat(),
        location=dev.get("location"),
        firmware=dev.get("firmware"),
    )


def emit(producer: Producer, topic: str, reading: Reading) -> None:
    # key by device so each device's readings keep order on one partition.
    producer.produce(topic, key=reading.device_external_id.encode(), value=reading.to_bytes())
    EMITTED.labels(device=reading.device_external_id).inc()


def run_backfill(producer, topic, devices, scenario, minutes: int) -> None:
    start = datetime.now(UTC) - timedelta(minutes=minutes)
    now = datetime.now(UTC)
    for dev in devices:
        t = start
        while t <= now:
            elapsed = (t - start).total_seconds()
            offset, suppress = fault_offset(dev, scenario, elapsed)
            if not suppress:
                emit(producer, topic, build_reading(dev, make_value(dev, offset), t))
            t += timedelta(seconds=dev["interval_seconds"])
    producer.flush()
    print(f"backfill complete: {minutes} min of history emitted")


def run_live(producer, topic, devices, scenario) -> None:
    start = datetime.now(UTC)
    next_at = {d["external_id"]: 0.0 for d in devices}
    print("live simulation — ctrl-c to stop")
    while True:
        now = datetime.now(UTC)
        elapsed = (now - start).total_seconds()
        for dev in devices:
            if elapsed >= next_at[dev["external_id"]]:
                offset, suppress = fault_offset(dev, scenario, elapsed)
                if not suppress:
                    emit(producer, topic, build_reading(dev, make_value(dev, offset), now))
                next_at[dev["external_id"]] = elapsed + dev["interval_seconds"]
        producer.poll(0)
        time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-minutes", type=int, default=0)
    ap.add_argument("--scenario", type=str, default=None)
    args = ap.parse_args()

    cfg = load_config()
    devices, scenarios = load_fleet()
    scenario = None
    if args.scenario:
        if args.scenario not in scenarios:
            sys.exit(f"unknown scenario '{args.scenario}'; have: {list(scenarios)}")
        scenario = scenarios[args.scenario]

    start_http_server(cfg.simulator_metrics_port)
    producer = Producer({"bootstrap.servers": cfg.kafka_bootstrap})

    if args.backfill_minutes > 0:
        run_backfill(producer, cfg.topic_readings, devices, scenario, args.backfill_minutes)
    else:
        try:
            run_live(producer, cfg.topic_readings, devices, scenario)
        except KeyboardInterrupt:
            producer.flush()
            print("\nstopped")


if __name__ == "__main__":
    main()
