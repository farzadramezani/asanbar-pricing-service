# Asanbar Pricing Service

Python 3.12 / FastAPI backend take-home assignment. Gate 1 provides configuration,
PostgreSQL connectivity, migrations, and health checks. Gate 2 adds persisted rate
cards and the default commission rule. Gate 3 adds integer pricing calculation
and persisted, versioned shipment quotes.

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
migration to create `pricing` without bootstrap SQL. The next migration creates
`pricing.rate_cards` and `pricing.commission_rules`, seeds the three rate cards
from `app/data/rate_cards.yaml` (integer IRR amounts), and inserts the active
`default` commission rule at 1000 basis points (10%). These YAML seed values are
part of migration history; future changes require a new migration.
Apply migrations before starting the application.
Revision `0003` creates `pricing.pricing_quotes`, storing inputs, amounts, and
the applied rate and commission values so existing quotes retain their values.

## Endpoints and tests

- `GET /health`: HTTP 200 with `{"status":"ok"}`, independent of PostgreSQL and Redis.
- `GET /ready`: PostgreSQL `SELECT 1`; HTTP 200 with `{"status":"ready"}` or
  HTTP 503 with `{"detail":"PostgreSQL unavailable"}` on database connection failure.
  Redis is not checked.
- `POST /api/v1/pricing/shipments/{shipment_id}/quote`: create or reuse a quote
  (HTTP 200). Shipment identifiers are opaque strings, not necessarily UUIDs.
- `GET /api/v1/pricing/shipments/{shipment_id}/quotes/latest`: return the highest
  quote version, or HTTP 404 / `QUOTE_NOT_FOUND`.

Example quote request:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/pricing/shipments/shipment-123/quote \
  -H 'Content-Type: application/json' \
  -d '{"inputs":{"distance_km":450,"stop_count":2,"cargo_type":"general","vehicle_type":"trailer"},"force_recalculate":false}'
```

Distance must be a positive integer and stop count an integer of at least one.
The example yields 5,900,000 IRR gross, 590,000 IRR commission, and 5,310,000 IRR
driver net. Commission uses integer arithmetic with nearest-integer rounding;
exact halves round to even. Breakdown `stop_fee` is the configured fee per extra
stop, and `base_amount` equals gross.

Identical inputs reuse the latest quote unless `force_recalculate` is true.
Changed inputs or forced recalculation create the next version starting at one.
Configuration changes alone do not replace an existing quote; force recalculation
to apply current configuration. A PostgreSQL transaction lock per shipment
serializes creation and version assignment.

Unknown cargo/vehicle combinations return HTTP 422 / `UNKNOWN_RATE_CARD`.
Pricing errors, including invalid requests, use
`{"error":{"code":"...","message":"...","correlation_id":"..."}}`.
Errors preserve `X-Correlation-Id` when supplied, otherwise generate a UUID.

```sh
pytest
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

The default test run covers health/readiness, configuration, YAML seeds, pricing
math, and error responses without infrastructure. PostgreSQL integration tests
are skipped unless `TEST_DATABASE_URL` is set. Use a dedicated, disposable database
with migrations applied; these tests temporarily change seeded configuration and
restore it afterward:

```sh
DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing alembic upgrade head
TEST_DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing pytest
```
