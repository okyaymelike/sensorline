include .env
export

.PHONY: up down logs db-init simulate ingest process test web seed

up:
	docker compose up -d --build

# run the React dashboard dev server (proxies /api to the read API on :8080)
web:
	cd web && npm install && npm run dev

# seed a few minutes of history with faults (idempotent sink, safe to re-run)
seed:
	docker compose run --rm simulator python -m simulator --config devices.demo.yaml \
	  --backfill-minutes 5 --scenario drift,spike,current_surge,flow_spike,pressure_drift,co2_offline

down:
	docker compose down

logs:
	docker compose logs -f

db-init:
	psql "$(DATABASE_URL)" -f db/schema.sql

ingest:
	python -m ingester

simulate:
	python -m simulator

process:
	python -m processor

test:
	python -m pytest
