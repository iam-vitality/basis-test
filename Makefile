.PHONY: up down logs test coverage lint format-check

up:
	docker compose up --build -d --wait

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --build --rm --no-deps checks pytest tests/unit -q

coverage:
	docker compose run --build --rm --no-deps checks pytest tests/unit --cov=payment_service --cov-report=term-missing --cov-fail-under=90

lint:
	docker compose run --build --rm --no-deps checks ruff check src tests alembic

format-check:
	docker compose run --build --rm --no-deps checks ruff format --check src tests alembic
