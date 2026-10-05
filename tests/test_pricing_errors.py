from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import pricing
from app.api.errors import PricingError
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client():
    # Validation/error tests never need to connect to a database.
    app.dependency_overrides[get_session] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize('inputs', [
    {'distance_km': 0, 'stop_count': 1},
    {'distance_km': -1, 'stop_count': 1},
    {'distance_km': 1, 'stop_count': 0},
    {'distance_km': 1, 'stop_count': -1},
    {'distance_km': 1.5, 'stop_count': 1},
    {'distance_km': True, 'stop_count': 1},
])
def test_invalid_inputs_use_pricing_error_shape(client, inputs):
    response = client.post('/api/v1/pricing/shipments/non-uuid/quote', json={
        'inputs': {**inputs, 'cargo_type': 'general', 'vehicle_type': 'trailer'},
    }, headers={'X-Correlation-Id': 'validation-request'})
    assert response.status_code == 422
    assert response.json() == {'error': {
        'code': 'VALIDATION_ERROR',
        'message': 'Invalid pricing request.',
        'correlation_id': 'validation-request',
    }}


def test_missing_body_generates_correlation_id(client):
    response = client.post('/api/v1/pricing/shipments/test/quote')
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    UUID(response.json()['error']['correlation_id'])


def test_unknown_card_passes_business_error_and_correlation_id(client, monkeypatch):
    def unknown(*args):
        raise PricingError(422, 'UNKNOWN_RATE_CARD', 'Unknown rate card.')
    monkeypatch.setattr(pricing, 'create_quote', unknown)
    response = client.post('/api/v1/pricing/shipments/test/quote', json={
        'inputs': {'distance_km': 1, 'stop_count': 1, 'cargo_type': 'unknown', 'vehicle_type': 'single'},
    }, headers={'X-Correlation-Id': 'client-supplied-id'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'UNKNOWN_RATE_CARD'
    assert response.json()['error']['correlation_id'] == 'client-supplied-id'


def test_missing_quote_uses_required_error_contract(client, monkeypatch):
    monkeypatch.setattr(pricing, 'latest_quote', lambda *_: None)
    response = client.get('/api/v1/pricing/shipments/test/quotes/latest')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'QUOTE_NOT_FOUND'
    UUID(response.json()['error']['correlation_id'])


def test_unexpected_pricing_errors_do_not_expose_details(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('private database detail')
    monkeypatch.setattr(pricing, 'latest_quote', fail)
    response = client.get('/api/v1/pricing/shipments/test/quotes/latest', headers={'X-Correlation-Id': 'failure'})
    assert response.status_code == 500
    assert response.json() == {'error': {
        'code': 'INTERNAL_ERROR',
        'message': 'Unable to process pricing request.',
        'correlation_id': 'failure',
    }}


def test_http_errors_are_scoped_to_pricing(client):
    response = client.get('/api/v1/pricing/nonexistent')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'HTTP_ERROR'
    assert client.get('/nonexistent').json() == {'detail': 'Not Found'}
