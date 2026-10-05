from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from common.telemetry import init_logging, init_tracing

from . import queries
from .db import close_pool, get_pool

CADENCE_S = 2  # default device reporting interval; status thresholds derive from it


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing("sensorline-api")  # OTLP traces -> Jaeger
    init_logging("sensorline-api")
    get_pool()  # open the connection pool at startup
    yield
    close_pool()


app = FastAPI(title="Sensorline API", version="0.1.0", lifespan=lifespan)

# RED metrics at /metrics (Prometheus scrapes this) + a span per request -> Jaeger
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
FastAPIInstrumentor.instrument_app(app)

# read-only API; the Vite dev server is the only browser origin that calls it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _status(staleness_s: float | None) -> str:
    if staleness_s is None:
        return "offline"
    if staleness_s <= CADENCE_S * 3:
        return "online"
    if staleness_s <= 60:
        return "stale"
    return "offline"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/devices")
def devices() -> list[dict]:
    return queries.list_devices()


@app.get("/api/fleet")
def fleet() -> list[dict]:
    rows = queries.fleet()
    for r in rows:
        r["status"] = _status(r.get("staleness_s"))
    return rows


@app.get("/api/devices/{external_id}/series")
def device_series(
    external_id: str,
    metric: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=2000),
) -> dict:
    metric = metric or queries.default_metric(external_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="No readings for this device")
    return {
        "external_id": external_id,
        "metric": metric,
        "points": queries.series(external_id, metric, limit),
    }


@app.get("/api/devices/{external_id}/anomalies")
def device_anomalies(external_id: str) -> list[dict]:
    return queries.device_anomalies(external_id)


@app.get("/api/readings/{reading_id}/genealogy")
def genealogy(reading_id: int) -> list[dict]:
    rows = queries.genealogy(reading_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Reading not found")
    return rows


@app.get("/api/anomalies/pareto")
def anomaly_pareto() -> list[dict]:
    return queries.anomaly_pareto()


@app.get("/api/anomalies/recent")
def recent_anomalies(limit: int = Query(default=20, ge=1, le=200)) -> list[dict]:
    return queries.recent_anomalies(limit)


@app.get("/api/freshness")
def freshness() -> dict:
    return queries.freshness()
