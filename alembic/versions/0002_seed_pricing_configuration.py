"""Create and seed rate cards and the default commission rule."""
from importlib.resources import files

from alembic import op
import sqlalchemy as sa
import yaml

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    rate_cards = op.create_table(
        "rate_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cargo_type", sa.String(50), nullable=False),
        sa.Column("vehicle_type", sa.String(50), nullable=False),
        sa.Column("rate_per_km", sa.BigInteger(), nullable=False),
        sa.Column("extra_stop_fee", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("cargo_type", "vehicle_type", name="uq_rate_cards_cargo_vehicle"),
        sa.CheckConstraint("rate_per_km >= 0", name="ck_rate_cards_rate_nonnegative"),
        sa.CheckConstraint("extra_stop_fee >= 0", name="ck_rate_cards_stop_fee_nonnegative"),
        schema="pricing",
    )
    commission_rules = op.create_table(
        "commission_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("commission_rate_bps", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("name", name="uq_commission_rules_name"),
        sa.CheckConstraint(
            "commission_rate_bps BETWEEN 0 AND 10000",
            name="ck_commission_rules_rate_bps",
        ),
        schema="pricing",
    )
    # Keep this revision's YAML seed values unchanged; later changes need a new revision.
    seed_path = files("app").joinpath("data/rate_cards.yaml")
    rate_card_rows = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    op.bulk_insert(rate_cards, rate_card_rows)
    op.bulk_insert(
        commission_rules,
        [{"name": "default", "commission_rate_bps": 1000, "active": True}],
    )


def downgrade() -> None:
    op.drop_table("commission_rules", schema="pricing")
    op.drop_table("rate_cards", schema="pricing")
