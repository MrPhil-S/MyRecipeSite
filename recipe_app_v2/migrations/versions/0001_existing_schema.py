"""Existing legacy schema baseline; offline review only in milestone 1.

Describes creating the existing schema in an empty database. Do not apply to an
existing database. A future approved write milestone must verify schema parity
and stamp this baseline, after backup and restore validation.
"""
from alembic import op
from recipe_app_v2.migrations.baseline_schema import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Destructive baseline downgrades are disabled.")
