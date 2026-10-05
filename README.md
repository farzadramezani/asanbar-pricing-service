# Asanbar Pricing Service

Python 3.12 / FastAPI backend take-home assignment. Gate 1 provides configuration,
PostgreSQL connectivity, migrations, and health checks. Pricing functionality and
Redis Streams integration belong to later gates.

## Setup

Prerequisites: Python 3.12, Docker, and Docker Compose v2.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

Configuration comes from environment variables or the root `.env` file;
environment variables take precedence. Local defaults match `.env.example`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL URL using the `postgresql+psycopg` driver |
| `REDIS_URL` | Redis connection URL reserved for later gates |

Compose exposes PostgreSQL on localhost:5432 and Redis on localhost:6379.
Example credentials are for local development only. PostgreSQL data persists in
a named volume. Stop infrastructure with `docker compose down`.

The initial migration creates only the `pricing` schema. Application metadata
targets that schema; Alembic's version table stays in `public`, allowing the first
migration to create `pricing` without bootstrap SQL. No business tables exist.
Apply migrations before starting the application.

## Endpoints and tests

- `GET /health`: HTTP 200 with `{"status":"ok"}`, independent of PostgreSQL and Redis.
- `GET /ready`: PostgreSQL `SELECT 1`; HTTP 200 with `{"status":"ready"}` or
  HTTP 503 with `{"detail":"PostgreSQL unavailable"}` on database connection failure.
  Redis is not checked.

```sh
pytest
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

Tests substitute the database engine and require no running infrastructure.
