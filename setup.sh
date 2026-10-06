#!/usr/bin/env bash
# Bring up the whole stack (infra + pipeline + API + observability), wait for it
# to be healthy, and seed a few minutes of history with faults.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || cp .env.example .env

echo "building and starting the stack..."
docker compose up -d --build

echo "waiting for Postgres and Kafka to be healthy..."
for _ in $(seq 1 60); do
  pg=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null || echo starting)
  kf=$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q kafka)" 2>/dev/null || echo starting)
  [ "$pg" = healthy ] && [ "$kf" = healthy ] && break
  sleep 2
done

echo "seeding backfill history (idempotent, safe to re-run)..."
docker compose run --rm simulator python -m simulator --config devices.demo.yaml \
  --backfill-minutes 5 \
  --scenario drift,spike,current_surge,flow_spike,pressure_drift,co2_offline || true

cat <<'EOF'

Sensorline is up. The live fleet streams automatically.

  Dashboard                                                       http://localhost:5173
  API                                                             http://localhost:8080/api/fleet
  Jaeger      traces (simulate -> ingest across Kafka)            http://localhost:16686
  Grafana     RED/USE observability dashboard                     http://localhost:3001/d/sensorline-obs
  Prometheus                                                      http://localhost:9091
  Alertmanager                                                    http://localhost:9093

  Trigger an alert:  docker compose stop ingester   (fires after ~1-2m; start it again to resolve)

starting the dashboard (ctrl-c stops it; the Docker stack keeps running)...
EOF

cd web && npm install && npm run dev
