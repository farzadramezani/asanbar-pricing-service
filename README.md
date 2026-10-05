# Asanbar Pricing Service

## Overview

A standalone shipment pricing service: shipment inputs produce a quote with
commission and driver net amounts; confirmation creates an immutable price
snapshot and publishes a `price_snapshot.created` Redis Stream event.

## Tech Stack

Python 3.12, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis Streams, pytest,
and Docker Compose.

## Setup

Prerequisites: Python 3.12, Docker, and Docker Compose v2. Run from the project root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
docker compose up -d
```

Compose exposes PostgreSQL on `localhost:5432` and Redis on `localhost:6379`.
PostgreSQL data persists in a named volume. Stop infrastructure with
`docker compose down`.

## Environment Variables

Use `.env.example` for local example configuration. Settings load from the root
`.env` file, with environment variables taking precedence. Example credentials
are for local development only.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL using the `postgresql+psycopg` driver |
| `REDIS_URL` | Redis connection URL for snapshot event publishing |

## Database / Migrations

Business tables live in PostgreSQL schema `pricing`:

| Table | Purpose |
| --- | --- |
| `rate_cards` | Rates by cargo and vehicle type |
| `commission_rules` | Named commission configuration |
| `pricing_quotes` | Versioned inputs, amounts, and applied pricing configuration |
| `price_snapshots` | Immutable confirmed amounts, limited to one snapshot per shipment |
| `idempotency_keys` | Confirmation keys linked to their operation, shipment, and snapshot |

Alembic seeds the rate cards from `app/data/rate_cards.yaml` and the active
`default` commission rule. YAML seed values are migration history; later changes
require a new migration. Alembic's version table remains in `public`.
Apply migrations before starting the application:

```sh
alembic upgrade head
```

## Running the Application

With the virtual environment active:

```sh
uvicorn app.main:app --reload
```

## API Endpoints

Shipment identifiers are opaque strings, not necessarily UUIDs.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Process health; HTTP 200, independent of PostgreSQL and Redis |
| GET | `/ready` | PostgreSQL `SELECT 1`; HTTP 200 when reachable, 503 otherwise; Redis is not checked |
| POST | `/api/v1/pricing/shipments/{shipment_id}/quote` | Create or reuse a quote; HTTP 200 |
| GET | `/api/v1/pricing/shipments/{shipment_id}/quotes/latest` | Latest quote, or 404 / `QUOTE_NOT_FOUND` |
| POST | `/api/v1/pricing/shipments/{shipment_id}/confirm-snapshot` | Confirm the latest quote; requires `Idempotency-Key`, no request body |
| GET | `/api/v1/pricing/shipments/{shipment_id}/snapshot` | Confirmed snapshot, or 404 / `SNAPSHOT_NOT_FOUND` |

Pricing errors use
`{"error":{"code":"...","message":"...","correlation_id":"..."}}`.
Errors preserve `X-Correlation-Id` when supplied, otherwise generate a UUID.

## Pricing Rules

All monetary amounts are integer IRR. Distance must be a positive integer;
stop count must be an integer of at least one. Rates and commission are read
from PostgreSQL, with no fallback for unknown combinations.

| Cargo | Vehicle | IRR/km | IRR per extra stop |
| --- | --- | ---: | ---: |
| general | trailer | 12,000 | 500,000 |
| general | single | 10,000 | 400,000 |
| refrigerated | trailer | 15,000 | 600,000 |

Default commission: **1000 basis points = 10%**.

```text
base = distance_km * rate_per_km + stop_fee * max(0, stop_count - 1)
gross = base
commission = round(gross * commission_rate_bps / 10_000)
driver_net = gross - commission
```

Commission rounding uses integer-only arithmetic; exact halves round to even.
The invariant is `driver_net_amount + commission_amount == gross_amount`.
Breakdown `base_amount` equals gross, and `stop_fee` is the configured fee per
extra stop. Unknown combinations return HTTP 422 / `UNKNOWN_RATE_CARD`.

## Quote Behavior

Identical latest inputs with `force_recalculate=false` reuse the quote.
`force_recalculate=true` or changed inputs create the next version, starting at
one. Existing quotes retain the pricing configuration used when calculated;
configuration changes alone do not replace them.

```sh
curl -X POST http://127.0.0.1:8000/api/v1/pricing/shipments/shipment-123/quote \
  -H 'Content-Type: application/json' \
  -d '{"inputs":{"distance_km":450,"stop_count":2,"cargo_type":"general","vehicle_type":"trailer"},"force_recalculate":false}'
```

This example yields 5,900,000 IRR gross, 590,000 IRR commission, and 5,310,000 IRR
driver net.

## Snapshot & Idempotency

Confirmation copies the latest quote into a snapshot that is immutable through
the API. Later quotes do not change it. `Idempotency-Key` is required: an opaque,
nonempty string of at most 255 characters.

| Confirmation case | Result |
| --- | --- |
| First successful confirmation | HTTP 201 |
| Same key, operation, and shipment | HTTP 200; same snapshot, no additional rows or event |
| Existing snapshot with a different key | HTTP 409 / `SNAPSHOT_ALREADY_EXISTS` |
| Key reused in a conflicting context | HTTP 409 / `IDEMPOTENCY_CONFLICT` |
| No quote | HTTP 404 / `QUOTE_NOT_FOUND`; no snapshot, idempotency record, or event |

Replay/conflict checks precede snapshot and quote checks. PostgreSQL transaction
locks protect the key and shipment; unique constraints enforce one snapshot per
shipment and one record per key.

```sh
curl -X POST http://127.0.0.1:8000/api/v1/pricing/shipments/shipment-123/confirm-snapshot \
  -H 'Idempotency-Key: confirmation-123'
```

## Redis Event

After committing the snapshot and idempotency record, the service uses `XADD` on
`asanbar:events`. Each entry contains exactly one field, `payload`, holding JSON
with `event_id` (UUID), `event_type` (`price_snapshot.created`), `occurred_at`,
`correlation_id`, and `data`. Data includes the shipment, snapshot and quote IDs,
gross, commission, driver net, and `IRR` currency.

The supplied `X-Correlation-Id` is copied into the event; without the header,
`correlation_id` is JSON `null`.

If publication fails, HTTP 503 / `EVENT_PUBLISH_FAILED` explicitly reports that
PostgreSQL has already committed. The snapshot and key remain stored. Same-key
replay returns the snapshot without attempting another publication. No
compensation or event retry occurs; this dual-write limitation can leave an
event missing.

## Testing

```sh
pytest
```

The default tests cover health/readiness, configuration, YAML seeds, pricing
math, error responses, and Redis payloads. Redis-focused automated tests use
`fakeredis`, including snapshot integration tests, so no Redis server is needed.

PostgreSQL integration tests require `TEST_DATABASE_URL`; otherwise they are
skipped. Use a dedicated disposable database with migrations applied. Tests
temporarily change seeded configuration and restore it afterward:

```sh
DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing alembic upgrade head
TEST_DATABASE_URL=postgresql+psycopg://pricing:pricing@localhost:5432/pricing pytest
```

## Production Hardening

The main production improvement would be a transactional outbox: persist the
snapshot, idempotency state, and outbox event in the same PostgreSQL transaction.
A reliable asynchronous publisher could deliver events to Redis with retries
and idempotent delivery, removing the current dual-write failure window.
This is not implemented.

## Time Spent

Approximately 4.5 hours, including implementation and final end-to-end verification.
