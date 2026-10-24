"""Track when a cooked event was recorded, separately from its cooked date."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("recipe_cooked_date", sa.Column(
        "recorded_dt", sa.DateTime(), nullable=False,
        server_default=sa.func.current_timestamp()))
    # For existing rows, the cooked timestamp is the best available estimate
    # of when they were recorded.
    op.execute("UPDATE recipe_cooked_date SET recorded_dt = recipe_cooked_dt")


def downgrade():
    raise RuntimeError("Downgrades discard cooked-record timestamps and are disabled.")
