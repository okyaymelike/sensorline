include .env
export

.PHONY: up down logs db-init simulate ingest process test

up:
	docker compose up -d --build

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
