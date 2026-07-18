PG_CONTAINER ?= pg-trial-query-engine-compose
PG_USER ?= postgres
PG_DB ?= hcp_clinical_trial_assistant
MONGO_CONTAINER ?= mongo-trial-query-engine-compose
MONGO_PORT ?= 27018
LOCAL_COMPOSE_DATABASE_URL ?= postgresql+asyncpg://postgres:postgres@localhost:15432/hcp_clinical_trial_assistant
LOCAL_COMPOSE_MONGO_URL ?= mongodb://localhost:27018
CONDITION ?= Type 2 Diabetes
MAX_STUDIES ?= 100
CONDITIONS ?= Type 2 Diabetes|Breast Cancer|Hypertension|Asthma
MAX_STUDIES_PER_CONDITION ?= 75

.PHONY: db-ping ping-db db-current db-upgrade db-downgrade db-revision db-tables db-extensions db-counts db-smoke-test mongo-up mongo-ping mongo-indexes mongo-smoke-test ingest-studies ingest-condition-set ingest-smoke-test query-smoke-test test test-unit test-integration check run dev-server docker-build docker-up docker-down docker-logs docker-migrate docker-mongo-indexes docker-db-smoke-test docker-mongo-smoke-test docker-ingest-studies docker-ingest-condition-set docker-ingest-smoke-test docker-query-smoke-test docker-test-integration
db-ping:
	docker compose exec postgres pg_isready -U $(PG_USER)

ping-db: db-ping

db-current:
	uv run alembic current

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1

db-revision:
	uv run alembic revision --autogenerate -m "$(m)"

db-tables:
	docker compose exec postgres psql -U $(PG_USER) -d $(PG_DB) -c "\dt"

db-extensions:
	docker compose exec postgres psql -U $(PG_USER) -d $(PG_DB) -c "\dx"

db-counts:
	docker compose exec postgres psql -U $(PG_USER) -d $(PG_DB) -c "SELECT count(*) AS documents FROM documents; SELECT count(*) AS chunks FROM document_chunks;"

db-smoke-test:
	uv run python -m scripts.db_smoke_test

mongo-up:
	docker inspect $(MONGO_CONTAINER) >/dev/null 2>&1 && docker start $(MONGO_CONTAINER) || docker run -d --name $(MONGO_CONTAINER) -p $(MONGO_PORT):27017 mongo:latest

mongo-ping:
	uv run python -m scripts.mongo_ping

mongo-indexes:
	uv run python -m scripts.mongo_create_indexes

mongo-smoke-test:
	uv run python -m scripts.mongo_smoke_test

ingest-studies:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) CONDITION="$(CONDITION)" MAX_STUDIES=$(MAX_STUDIES) uv run python -m scripts.ingest_studies

ingest-condition-set:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) CONDITIONS="$(CONDITIONS)" MAX_STUDIES_PER_CONDITION=$(MAX_STUDIES_PER_CONDITION) uv run python -m scripts.ingest_condition_set

ingest-smoke-test:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run python -m scripts.ingest_smoke_test

query-smoke-test:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run python -m scripts.query_smoke_test

test:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run pytest tests/integration

check:
	$(MAKE) test
	uv run python -m compileall app scripts tests
	uv run alembic check

run:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run fastapi dev

dev-server:
	DATABASE_URL=$(LOCAL_COMPOSE_DATABASE_URL) MONGO_URL=$(LOCAL_COMPOSE_MONGO_URL) uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-migrate:
	docker compose run --rm api uv run alembic upgrade head

docker-mongo-indexes:
	docker compose run --rm api uv run python -m scripts.mongo_create_indexes

docker-db-smoke-test:
	docker compose run --rm api uv run python -m scripts.db_smoke_test

docker-mongo-smoke-test:
	docker compose run --rm api uv run python -m scripts.mongo_smoke_test

docker-ingest-studies:
	docker compose run --rm -e CONDITION="$(CONDITION)" -e MAX_STUDIES="$(MAX_STUDIES)" api uv run python -m scripts.ingest_studies

docker-ingest-condition-set:
	docker compose run --rm -e CONDITIONS="$(CONDITIONS)" -e MAX_STUDIES_PER_CONDITION="$(MAX_STUDIES_PER_CONDITION)" api uv run python -m scripts.ingest_condition_set

docker-ingest-smoke-test:
	docker compose run --rm api uv run python -m scripts.ingest_smoke_test

docker-query-smoke-test:
	docker compose run --rm api uv run python -m scripts.query_smoke_test

docker-test-integration:
	docker compose run --rm api uv run --with pytest pytest tests/integration
