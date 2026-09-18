.PHONY: up down logs ps migrate test lint fmt check

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

migrate:
	docker compose exec api alembic upgrade head

test:
	pytest -q

lint:
	ruff check backend tests
	ruff format --check backend tests

fmt:
	ruff format backend tests
	ruff check --fix backend tests
