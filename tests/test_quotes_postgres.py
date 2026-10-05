import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from app.db.models import CommissionRule, PricingQuote, RateCard
from app.db.session import get_session
from app.main import app

DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason='Set TEST_DATABASE_URL to a dedicated migrated PostgreSQL database')
INPUTS = {'distance_km': 450, 'stop_count': 2, 'cargo_type': 'general', 'vehicle_type': 'trailer'}


@pytest.fixture
def engine():
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def shipment_id(engine):
    shipment_id = f'gate3-test-{uuid4()}'
    yield shipment_id
    with engine.begin() as connection:
        connection.execute(delete(PricingQuote).where(PricingQuote.shipment_id == shipment_id))


@pytest.fixture
def client(engine):
    def session():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def post(client, shipment_id, inputs=None, force=False):
    return client.post(f'/api/v1/pricing/shipments/{shipment_id}/quote', json={
        'inputs': inputs or INPUTS, 'force_recalculate': force,
    })


def test_quote_lifecycle_and_persisted_values(client, engine, shipment_id):
    first_response = post(client, shipment_id)
    assert first_response.status_code == 200
    first = first_response.json()
    UUID(first['quote_id'])
    assert first['shipment_id'] == shipment_id
    assert first['quote_version'] == 1
    assert first['inputs'] == INPUTS
    assert first['currency'] == 'IRR'
    assert first['created_at']
    assert first['gross_amount'] == 5900000
    assert first['commission_amount'] == 590000
    assert first['driver_net_amount'] == 5310000
    assert first['breakdown'] == {
        'base_amount': 5900000, 'distance_amount': 5400000,
        'stop_fee': 500000, 'rate_per_km': 12000, 'commission_rate_bps': 1000,
    }
    assert post(client, shipment_id).json() == first
    second = post(client, shipment_id, force=True).json()
    assert second['quote_id'] != first['quote_id']
    assert second['quote_version'] == 2
    changed_inputs = {**INPUTS, 'distance_km': 451}
    third = post(client, shipment_id, changed_inputs).json()
    assert third['quote_version'] == 3
    assert third['quote_id'] not in {first['quote_id'], second['quote_id']}
    assert client.get(f'/api/v1/pricing/shipments/{shipment_id}/quotes/latest').json() == third
    with Session(engine) as session:
        rows = session.scalars(select(PricingQuote).where(
            PricingQuote.shipment_id == shipment_id,
        ).order_by(PricingQuote.quote_version)).all()
        assert len(rows) == 3
        assert [row.quote_version for row in rows] == [1, 2, 3]
        assert [row.distance_km for row in rows] == [450, 450, 451]
        for row in rows:
            assert row.gross_amount == row.commission_amount + row.driver_net_amount
            assert row.rate_per_km == 12000
            assert row.stop_fee == 500000
            assert row.commission_rate_bps == 1000


def test_business_errors_against_postgres(client, engine, shipment_id):
    response = client.post(f'/api/v1/pricing/shipments/{shipment_id}/quote', json={
        'inputs': {**INPUTS, 'cargo_type': 'unknown'},
    }, headers={'X-Correlation-Id': 'unknown-card-request'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'UNKNOWN_RATE_CARD'
    assert response.json()['error']['correlation_id'] == 'unknown-card-request'
    missing = client.get(f'/api/v1/pricing/shipments/{shipment_id}/quotes/latest')
    assert missing.status_code == 404
    assert missing.json()['error']['code'] == 'QUOTE_NOT_FOUND'
    UUID(missing.json()['error']['correlation_id'])
    with Session(engine) as session:
        assert session.scalar(select(PricingQuote).where(PricingQuote.shipment_id == shipment_id)) is None


def test_quotes_preserve_applied_configuration(client, engine, shipment_id):
    first = post(client, shipment_id).json()
    try:
        with engine.begin() as connection:
            connection.execute(update(RateCard).where(
                RateCard.cargo_type == 'general', RateCard.vehicle_type == 'trailer',
            ).values(rate_per_km=13000, extra_stop_fee=600000))
            connection.execute(update(CommissionRule).where(CommissionRule.name == 'default').values(commission_rate_bps=2000))
        assert post(client, shipment_id).json() == first
        second = post(client, shipment_id, force=True).json()
        assert second['quote_version'] == 2
        assert second['gross_amount'] == 6450000
        assert second['commission_amount'] == 1290000
        assert second['breakdown']['rate_per_km'] == 13000
        assert second['breakdown']['stop_fee'] == 600000
        assert second['breakdown']['commission_rate_bps'] == 2000
        with Session(engine) as session:
            original = session.get(PricingQuote, UUID(first['quote_id']))
            assert original.rate_per_km == 12000
            assert original.stop_fee == 500000
            assert original.commission_rate_bps == 1000
    finally:
        with engine.begin() as connection:
            connection.execute(update(RateCard).where(
                RateCard.cargo_type == 'general', RateCard.vehicle_type == 'trailer',
            ).values(rate_per_km=12000, extra_stop_fee=500000))
            connection.execute(update(CommissionRule).where(CommissionRule.name == 'default').values(commission_rate_bps=1000))


def test_concurrent_reuse_and_force_versioning(client, engine, shipment_id):
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post(client, shipment_id), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()['quote_id'] for response in responses}) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        forced = list(pool.map(lambda _: post(client, shipment_id, force=True), range(4)))
    assert all(response.status_code == 200 for response in forced)
    assert sorted(response.json()['quote_version'] for response in forced) == [2, 3, 4, 5]
    with Session(engine) as session:
        assert len(session.scalars(select(PricingQuote).where(PricingQuote.shipment_id == shipment_id)).all()) == 5


def test_failed_creation_rolls_back_without_fallback(client, engine, shipment_id):
    overflow = post(client, shipment_id, {**INPUTS, 'distance_km': 2**63 - 1})
    assert overflow.status_code == 422
    assert overflow.json()['error']['code'] == 'AMOUNT_OUT_OF_RANGE'
    try:
        with engine.begin() as connection:
            connection.execute(update(CommissionRule).where(CommissionRule.name == 'default').values(active=False))
        missing_rule = post(client, shipment_id)
        assert missing_rule.status_code == 503
        assert missing_rule.json()['error']['code'] == 'COMMISSION_RULE_UNAVAILABLE'
        with Session(engine) as session:
            assert session.scalar(select(PricingQuote).where(PricingQuote.shipment_id == shipment_id)) is None
    finally:
        with engine.begin() as connection:
            connection.execute(update(CommissionRule).where(CommissionRule.name == 'default').values(active=True))
    recovered = post(client, shipment_id)
    assert recovered.status_code == 200
    assert recovered.json()['quote_version'] == 1
