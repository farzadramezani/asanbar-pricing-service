from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from app.db.session import get_engine
from app.main import app


@pytest.fixture
def engine():
    engine = MagicMock(spec=Engine)
    app.dependency_overrides[get_engine] = lambda: engine
    yield engine
    app.dependency_overrides.clear()


def test_health_does_not_use_database(engine):
    engine.connect.side_effect = AssertionError("Database must not be used")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    engine.connect.assert_not_called()


def test_ready_when_database_available(engine):
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    connection = engine.connect.return_value.__enter__.return_value
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


def test_ready_when_database_unavailable(engine):
    engine.connect.side_effect = OperationalError(None, None, Exception("offline"))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "PostgreSQL unavailable"}


def test_ready_does_not_swallow_unrelated_errors(engine):
    engine.connect.side_effect = ValueError("unexpected")
    with TestClient(app) as client, pytest.raises(ValueError, match="unexpected"):
        client.get("/ready")
