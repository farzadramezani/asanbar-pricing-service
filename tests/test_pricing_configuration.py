from importlib.resources import files

from alembic import command
from alembic.config import Config
import yaml


def test_yaml_contains_exact_assignment_rate_cards():
    rows = yaml.safe_load(files("app").joinpath("data/rate_cards.yaml").read_text())
    assert rows == [
        {
            "cargo_type": "general",
            "vehicle_type": "trailer",
            "rate_per_km": 12000,
            "extra_stop_fee": 500000,
        },
        {
            "cargo_type": "general",
            "vehicle_type": "single",
            "rate_per_km": 10000,
            "extra_stop_fee": 400000,
        },
        {
            "cargo_type": "refrigerated",
            "vehicle_type": "trailer",
            "rate_per_km": 15000,
            "extra_stop_fee": 600000,
        },
    ]
    assert all(
        type(row[field]) is int
        for row in rows
        for field in ("rate_per_km", "extra_stop_fee")
    )


def test_migration_uses_yaml_seed_values(monkeypatch, capsys):
    # Different fixture values prove the migration actually reads YAML.
    fixture_rows = [{
        "cargo_type": "test_cargo",
        "vehicle_type": "test_vehicle",
        "rate_per_km": 123,
        "extra_stop_fee": 456,
    }]
    monkeypatch.setattr(yaml, "safe_load", lambda _: fixture_rows)
    command.upgrade(Config("alembic.ini"), "head", sql=True)
    sql = capsys.readouterr().out
    assert "INSERT INTO pricing.rate_cards" in sql
    assert "'test_cargo', 'test_vehicle', 123, 456" in sql
    assert "INSERT INTO pricing.commission_rules" in sql
    assert "'default', 1000, true" in sql
