"""Create the pricing schema without business tables."""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA pricing")


def downgrade() -> None:
    op.execute("DROP SCHEMA pricing")
