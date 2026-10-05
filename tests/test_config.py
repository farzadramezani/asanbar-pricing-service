from app.core.config import Settings


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/1")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://test:test@localhost/test"
    assert settings.redis_url == "redis://localhost:6380/1"
