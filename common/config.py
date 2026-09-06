import os
from dataclasses import dataclass

from dotenv import load_dotenv

# load .env if present; real environment variables still take precedence.
load_dotenv()


@dataclass(frozen=True)
class Config:
    database_url: str
    kafka_bootstrap: str
    topic_readings: str
    ingester_metrics_port: int
    simulator_metrics_port: int
    processor_metrics_port: int


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env (or export {name}) before running."
        )
    return value


def load_config() -> Config:
    return Config(
        database_url=_require("DATABASE_URL"),
        kafka_bootstrap=_require("KAFKA_BOOTSTRAP"),
        topic_readings=os.environ.get("KAFKA_TOPIC_READINGS", "telemetry.readings"),
        ingester_metrics_port=int(os.environ.get("INGESTER_METRICS_PORT", "8001")),
        simulator_metrics_port=int(os.environ.get("SIMULATOR_METRICS_PORT", "8002")),
        processor_metrics_port=int(os.environ.get("PROCESSOR_METRICS_PORT", "8003")),
    )
