"""Create immutable application snapshots and confirmation idempotency records."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_snapshots",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column("shipment_id", sa.Text(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), sa.ForeignKey("pricing.pricing_quotes.quote_id"), nullable=False),
        sa.Column("quote_version", sa.Integer(), nullable=False),
        sa.Column("gross_amount", sa.BigInteger(), nullable=False),
        sa.Column("commission_amount", sa.BigInteger(), nullable=False),
        sa.Column("driver_net_amount", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("shipment_id", name="uq_price_snapshots_shipment"),
        sa.CheckConstraint("quote_version > 0", name="ck_price_snapshots_version_positive"),
        sa.CheckConstraint(
            "gross_amount >= 0 AND commission_amount >= 0 AND driver_net_amount >= 0",
            name="ck_price_snapshots_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "driver_net_amount + commission_amount = gross_amount",
            name="ck_price_snapshots_amount_balance",
        ),
        schema="pricing",
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("shipment_id", sa.Text(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("pricing.price_snapshots.snapshot_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="pricing",
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys", schema="pricing")
    op.drop_table("price_snapshots", schema="pricing")
