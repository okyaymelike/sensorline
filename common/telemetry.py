from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_initialised = False


def init_tracing(service_name: str) -> None:
    """Wire the OTLP exporter once. Endpoint comes from OTEL_EXPORTER_OTLP_ENDPOINT
    (default localhost:4317 for host runs; jaeger:4317 in compose)."""
    global _initialised
    if _initialised:
        return
    raw = (
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or "localhost:4317"
    )
    endpoint = raw.replace("https://", "").replace("http://", "")
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    _initialised = True


def get_tracer(name: str = "sensorline"):
    return trace.get_tracer(name)


# --- Kafka header propagation. Kafka headers are a list of (str, bytes). ---


def inject_trace_headers() -> list[tuple[str, bytes]]:
    carrier: dict[str, str] = {}
    inject(carrier)
    return [(k, v.encode()) for k, v in carrier.items()]


def extract_context(headers: Sequence[tuple[str, bytes]] | None) -> Context:
    carrier: dict[str, str] = {}
    for key, value in headers or []:
        carrier[key] = value.decode() if isinstance(value, (bytes, bytearray)) else str(value)
    return extract(carrier)


# --- Structured JSON logging, with trace/span ids injected when a span is active. ---


class _JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%03d%z"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def init_logging(service_name: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter(service_name))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
