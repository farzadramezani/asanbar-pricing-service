import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from fakeredis import FakeRedis
from fastapi.testclient import TestClient
import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from app.db.models import IdempotencyKey, PriceSnapshot, PricingQuote
from app.db.session import get_session
from app.events import get_redis
from app.main import app

DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason='Set TEST_DATABASE_URL to a dedicated migrated PostgreSQL database')
INPUTS = {'distance_km': 450, 'stop_count': 2, 'cargo_type': 'general', 'vehicle_type': 'trailer'}


@pytest.fixture
def context():
    engine = create_engine(DATABASE_URL)
    redis = FakeRedis(decode_responses=True)
    prefix = f'gate4-test-{uuid4()}'
    shipments = [prefix + '-a', prefix + '-b']

    def session():
        with Session(engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        with TestClient(app) as client:
            yield client, engine, redis, shipments
    finally:
        app.dependency_overrides.clear()
        with engine.begin() as connection:
            connection.execute(delete(IdempotencyKey).where(IdempotencyKey.shipment_id.in_(shipments)))
            connection.execute(delete(PriceSnapshot).where(PriceSnapshot.shipment_id.in_(shipments)))
            connection.execute(delete(PricingQuote).where(PricingQuote.shipment_id.in_(shipments)))
        redis.close()
        engine.dispose()


def quote(client, shipment, distance=450):
    response = client.post(f'/api/v1/pricing/shipments/{shipment}/quote', json={
        'inputs': {**INPUTS, 'distance_km': distance},
    })
    assert response.status_code == 200
    return response.json()


def confirm(client, shipment, key, correlation_id=None):
    headers = {'Idempotency-Key': key}
    if correlation_id is not None:
        headers['X-Correlation-Id'] = correlation_id
    return client.post(f'/api/v1/pricing/shipments/{shipment}/confirm-snapshot', headers=headers)


def assert_counts(engine, shipments, snapshots, keys):
    with Session(engine) as session:
        assert len(session.scalars(select(PriceSnapshot).where(PriceSnapshot.shipment_id.in_(shipments))).all()) == snapshots
        assert len(session.scalars(select(IdempotencyKey).where(IdempotencyKey.shipment_id.in_(shipments))).all()) == keys


def test_confirm_latest_replay_conflicts_and_immutable_snapshot(context):
    client, engine, redis, shipments = context
    shipment, other = shipments
    key = str(uuid4())
    quote(client, shipment)
    latest = quote(client, shipment, distance=451)
    response = confirm(client, shipment, key, 'confirm-correlation')
    assert response.status_code == 201
    snapshot = response.json()
    assert set(snapshot) == {
        'snapshot_id', 'shipment_id', 'quote_id', 'quote_version', 'gross_amount',
        'commission_amount', 'driver_net_amount', 'currency', 'confirmed_at',
    }
    UUID(snapshot['snapshot_id'])
    assert snapshot['quote_id'] == latest['quote_id']
    assert snapshot['quote_version'] == 2
    assert snapshot['shipment_id'] == shipment
    for field in ['gross_amount', 'commission_amount', 'driver_net_amount']:
        assert snapshot[field] == latest[field]
    assert snapshot['currency'] == 'IRR'
    assert snapshot['confirmed_at']
    assert_counts(engine, shipments, 1, 1)
    replay = confirm(client, shipment, key, 'different-replay-correlation')
    assert replay.status_code == 200
    assert replay.json() == snapshot
    duplicate = confirm(client, shipment, str(uuid4()))
    assert duplicate.status_code == 409
    assert duplicate.json()['error']['code'] == 'SNAPSHOT_ALREADY_EXISTS'
    conflict = confirm(client, other, key, 'conflict-correlation')
    assert conflict.status_code == 409  # Conflict wins even though other has no quote.
    assert conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert conflict.json()['error']['correlation_id'] == 'conflict-correlation'
    quote(client, shipment, distance=452)
    assert client.get(f'/api/v1/pricing/shipments/{shipment}/snapshot').json() == snapshot
    assert confirm(client, shipment, key).json() == snapshot
    assert_counts(engine, shipments, 1, 1)
    entries = redis.xrange('asanbar:events')
    assert len(entries) == 1
    assert set(entries[0][1]) == {'payload'}
    event = json.loads(entries[0][1]['payload'])
    assert event['correlation_id'] == 'confirm-correlation'
    assert event['data']['quote_id'] == latest['quote_id']
    assert event['data']['price_snapshot_id'] == snapshot['snapshot_id']


def test_missing_quote_and_snapshot_create_nothing(context):
    client, engine, redis, shipments = context
    key = str(uuid4())
    missing = confirm(client, shipments[0], key)
    assert missing.status_code == 404
    assert missing.json()['error']['code'] == 'QUOTE_NOT_FOUND'
    UUID(missing.json()['error']['correlation_id'])
    response = client.get(f'/api/v1/pricing/shipments/{shipments[0]}/snapshot')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'SNAPSHOT_NOT_FOUND'
    assert_counts(engine, shipments, 0, 0)
    assert redis.xlen('asanbar:events') == 0
    quote(client, shipments[0])
    assert confirm(client, shipments[0], key).status_code == 201  # Failed attempts don't reserve keys.
    event = json.loads(redis.xrange('asanbar:events')[0][1]['payload'])
    assert event['correlation_id'] is None


def test_conflicting_operation_is_not_a_replay(context):
    client, engine, redis, shipments = context
    key = str(uuid4())
    quote(client, shipments[0])
    assert confirm(client, shipments[0], key).status_code == 201
    with engine.begin() as connection:
        connection.execute(update(IdempotencyKey).where(IdempotencyKey.key == key).values(operation='different_operation'))
    conflict = confirm(client, shipments[0], key)
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert_counts(engine, shipments, 1, 1)
    assert redis.xlen('asanbar:events') == 1


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_confirms_same_shipment(context, same_key):
    client, engine, redis, shipments = context
    quote(client, shipments[0])
    key = str(uuid4())
    keys = [key] * 4 if same_key else [str(uuid4()) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda key: confirm(client, shipments[0], key), keys))
    if same_key:
        assert sorted(response.status_code for response in responses) == [200, 200, 200, 201]
        assert len({response.json()['snapshot_id'] for response in responses}) == 1
    else:
        assert sorted(response.status_code for response in responses) == [201, 409, 409, 409]
        assert all(response.json()['error']['code'] == 'SNAPSHOT_ALREADY_EXISTS' for response in responses if response.status_code == 409)
    assert_counts(engine, shipments, 1, 1)
    assert redis.xlen('asanbar:events') == 1


def test_concurrent_same_key_different_shipments(context):
    client, engine, redis, shipments = context
    for shipment in shipments:
        quote(client, shipment)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda shipment: confirm(client, shipment, key), shipments))
    assert sorted(response.status_code for response in responses) == [201, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert_counts(engine, shipments, 1, 1)
    assert redis.xlen('asanbar:events') == 1


@pytest.mark.parametrize('event_accepted', [False, True])
def test_database_commit_precedes_publication_and_redis_failure_is_explicit(context, monkeypatch, event_accepted):
    client, engine, redis, shipments = context
    shipment = shipments[0]
    key = str(uuid4())
    quote(client, shipment)

    original_xadd = redis.xadd

    def failed_xadd(*args, **kwargs):
        # A separate connection must see both records before any Redis command.
        assert_counts(engine, shipments, 1, 1)
        if event_accepted:
            original_xadd(*args, **kwargs)
        raise ConnectionError('Redis unavailable')
    monkeypatch.setattr(redis, 'xadd', failed_xadd)
    failure = confirm(client, shipment, key)
    assert failure.status_code == 503
    assert failure.json()['error']['code'] == 'EVENT_PUBLISH_FAILED'
    assert 'committed' in failure.json()['error']['message']
    assert_counts(engine, shipments, 1, 1)
    replay = confirm(client, shipment, key)
    assert replay.status_code == 200
    assert redis.xlen('asanbar:events') == int(event_accepted)
    assert client.get(f'/api/v1/pricing/shipments/{shipment}/snapshot').json() == replay.json()
