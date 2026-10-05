from datetime import UTC, datetime
import json
from uuid import UUID, uuid4

from fakeredis import FakeRedis
import pytest
from fastapi.testclient import TestClient

from app.db.models import PriceSnapshot
from app.db.session import get_session
from app.events import get_redis, publish_snapshot_created
from app.main import app


@pytest.mark.parametrize('correlation_id', [None, 'client-correlation'])
def test_snapshot_event_has_exact_stream_and_payload(correlation_id):
    redis = FakeRedis(decode_responses=True)
    snapshot = PriceSnapshot(
        snapshot_id=uuid4(), shipment_id='opaque-shipment', quote_id=uuid4(),
        quote_version=3, gross_amount=5900000, commission_amount=590000,
        driver_net_amount=5310000, confirmed_at=datetime.now(UTC),
    )
    before = datetime.now(UTC)
    publish_snapshot_created(redis, snapshot, correlation_id)
    after = datetime.now(UTC)
    assert list(redis.scan_iter()) == ['asanbar:events']
    entries = redis.xrange('asanbar:events')
    assert len(entries) == 1
    assert set(entries[0][1]) == {'payload'}
    payload = json.loads(entries[0][1]['payload'])
    assert set(payload) == {'event_id', 'event_type', 'occurred_at', 'correlation_id', 'data'}
    UUID(payload['event_id'])
    assert before <= datetime.fromisoformat(payload['occurred_at']) <= after
    assert payload['event_type'] == 'price_snapshot.created'
    assert payload['correlation_id'] == correlation_id
    assert payload['data'] == {
        'shipment_id': 'opaque-shipment', 'price_snapshot_id': str(snapshot.snapshot_id),
        'quote_id': str(snapshot.quote_id), 'gross_amount': 5900000,
        'commission_amount': 590000, 'driver_net_amount': 5310000, 'currency': 'IRR',
    }
    redis.close()


@pytest.mark.parametrize('key', [None, '', 'k' * 256])
def test_idempotency_header_validation_uses_pricing_error_shape(key):
    redis = FakeRedis()
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        with TestClient(app) as client:
            headers = {'X-Correlation-Id': 'header-validation'}
            if key is not None:
                headers['Idempotency-Key'] = key
            response = client.post('/api/v1/pricing/shipments/test/confirm-snapshot', headers=headers)
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'VALIDATION_ERROR'
        assert response.json()['error']['correlation_id'] == 'header-validation'
        assert redis.xlen('asanbar:events') == 0
    finally:
        app.dependency_overrides.clear()
        redis.close()
