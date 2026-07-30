from alembic import op


revision = "0001_create_schemas"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    op.execute("CREATE SCHEMA IF NOT EXISTS clean;")
    op.execute("CREATE SCHEMA IF NOT EXISTS gold;")
    op.execute("CREATE SCHEMA IF NOT EXISTS ml;")
    op.execute("CREATE SCHEMA IF NOT EXISTS fip;")
    op.execute("CREATE SCHEMA IF NOT EXISTS ops;")

    op.execute("COMMENT ON SCHEMA gold IS 'Reserved for analytics-ready outputs and gold tables.';")
    op.execute("COMMENT ON SCHEMA ml IS 'Reserved for feature stores, models, and ML outputs.';")
    op.execute("COMMENT ON SCHEMA fip IS 'Reserved for application-facing decisioning tables and services.';")


def downgrade():
    op.execute("DROP SCHEMA IF EXISTS fip CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS ml CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS gold CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS clean CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS ops CASCADE;")