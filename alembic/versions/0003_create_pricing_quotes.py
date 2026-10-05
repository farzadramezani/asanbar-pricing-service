"""Create pricing quotes, preserving their inputs and applied configuration."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pricing_quotes",
        sa.Column("quote_id", sa.Uuid(), primary_key=True),
        sa.Column("shipment_id", sa.Text(), nullable=False),
        sa.Column("quote_version", sa.Integer(), nullable=False),
        sa.Column("distance_km", sa.BigInteger(), nullable=False),
        sa.Column("stop_count", sa.Integer(), nullable=False),
        sa.Column("cargo_type", sa.String(50), nullable=False),
        sa.Column("vehicle_type", sa.String(50), nullable=False),
        sa.Column("gross_amount", sa.BigInteger(), nullable=False),
        sa.Column("commission_amount", sa.BigInteger(), nullable=False),
        sa.Column("driver_net_amount", sa.BigInteger(), nullable=False),
        sa.Column("distance_amount", sa.BigInteger(), nullable=False),
        sa.Column("stop_fee", sa.BigInteger(), nullable=False),
        sa.Column("rate_per_km", sa.BigInteger(), nullable=False),
        sa.Column("commission_rate_bps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("shipment_id", "quote_version", name="uq_pricing_quotes_shipment_version"),
        sa.CheckConstraint("quote_version > 0", name="ck_pricing_quotes_version_positive"),
        sa.CheckConstraint("distance_km > 0", name="ck_pricing_quotes_distance_positive"),
        sa.CheckConstraint("stop_count >= 1", name="ck_pricing_quotes_stop_count_positive"),
        sa.CheckConstraint(
            "gross_amount >= 0 AND commission_amount >= 0 AND driver_net_amount >= 0",
            name="ck_pricing_quotes_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "driver_net_amount + commission_amount = gross_amount",
            name="ck_pricing_quotes_amount_balance",
        ),
        schema="pricing",
    )


def downgrade() -> None:
    op.drop_table("pricing_quotes", schema="pricing")
