from alembic import context
from recipe_app_v2.models import Base

# Schema DDL may be reviewed offline, but no upgrade, downgrade or stamp may
# connect or write in milestone 1. There is intentionally no configured DB URL.
if not context.is_offline_mode():
    raise RuntimeError("Online Alembic operations are disabled during the read-only milestone. Use upgrade head --sql for review.")

context.configure(url="mysql+pymysql://", target_metadata=Base.metadata,
                  version_table="recipe_v2_alembic_version", literal_binds=True)
with context.begin_transaction():
    context.run_migrations()
