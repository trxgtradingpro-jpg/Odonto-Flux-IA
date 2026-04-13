SHELL := /bin/bash

.PHONY: up down logs migrate seed test lint format clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.scripts.seed

test:
	docker compose exec api pytest -q
	docker compose exec web pnpm test

lint:
	docker compose exec api ruff check app tests
	docker compose exec web pnpm lint

format:
	docker compose exec api ruff format app tests
	docker compose exec web pnpm format

clean:
	docker compose down -v
