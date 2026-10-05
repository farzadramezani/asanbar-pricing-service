# Asanbar Pricing Service

Python 3.12 / FastAPI backend take-home assignment. Gate 1 provides configuration,
PostgreSQL connectivity, migrations, and health checks. Gate 2 adds persisted rate
cards and the default commission rule. Gate 3 adds integer pricing calculation
and persisted, versioned shipment quotes. Gate 4 adds immutable price snapshots,
confirmation idempotency, and Redis Stream publishing.

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
| `REDIS_URL` | Redis connection URL for snapshot event publishing |

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
Revision `0004` adds `pricing.price_snapshots` and `pricing.idempotency_keys`.

## Endpoints and tests

- `GET /health`: HTTP 200 with `{"status":"ok"}`, independent of PostgreSQL and Redis.
- `GET /ready`: PostgreSQL `SELECT 1`; HTTP 200 with `{"status":"ready"}` or
  HTTP 503 with `{"detail":"PostgreSQL unavailable"}` on database connection failure.
  Redis is not checked.
- `POST /api/v1/pricing/shipments/{shipment_id}/quote`: create or reuse a quote
  (HTTP 200). Shipment identifiers are opaque strings, not necessarily UUIDs.
- `GET /api/v1/pricing/shipments/{shipment_id}/quotes/latest`: return the highest
  quote version, or HTTP 404 / `QUOTE_NOT_FOUND`.
- `POST /api/v1/pricing/shipments/{shipment_id}/confirm-snapshot`: confirm the
  latest quote with a required `Idempotency-Key` header and no request body.
- `GET /api/v1/pricing/shipments/{shipment_id}/snapshot`: return the immutable
  snapshot, or HTTP 404 / `SNAPSHOT_NOT_FOUND`.

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

Confirm a shipment's latest quote:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/pricing/shipments/shipment-123/confirm-snapshot \
  -H 'Idempotency-Key: confirmation-123'
```

First confirmation returns HTTP 201. Reusing the same key for the same shipment
and operation returns HTTP 200 with the same snapshot and no new event. Keys are
opaque, nonempty strings of at most 255 characters. Reuse in another context
returns HTTP 409 / `IDEMPOTENCY_CONFLICT`; confirming an existing snapshot with a
different key returns HTTP 409 / `SNAPSHOT_ALREADY_EXISTS`. Without a quote,
confirmation returns HTTP 404 / `QUOTE_NOT_FOUND` and reserves no key. Later quotes
do not change the confirmed snapshot.

After PostgreSQL commits a first confirmation, Redis `XADD` appends to
`asanbar:events`, with exactly one field, `payload`, containing JSON for
`price_snapshot.created`. It includes a UUID event ID, creation time, persisted
snapshot values, and the supplied `X-Correlation-Id` or JSON `null` if absent.

If Redis publication fails after the database commit, HTTP 503 /
`EVENT_PUBLISH_FAILED` explicitly reports that the snapshot was committed.
The snapshot and key remain stored; replay returns the snapshot without publishing
again. No compensation or event retry is attempted. This PostgreSQL/Redis dual-write
window can leave an event missing; a transactional outbox is deferred production
hardening.

```sh
pytest
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
```

The default test run covers health/readiness, configuration, YAML seeds, pricing
math, error responses, and Redis payloads without infrastructure. Redis tests use
`fakeredis`, including snapshot integration tests; they require no Redis server.
PostgreSQL integration tests are skipped unless `TEST_DATABASE_URL` is set.
Use a dedicated, disposable database
with migrations applied; these tests temporarily change seeded configuration and
restore it afterward:

```sh
DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing alembic upgrade head
TEST_DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing pytest
```
