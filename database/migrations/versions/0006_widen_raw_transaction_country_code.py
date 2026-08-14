from alembic import op


revision = "0006_widen_raw_txn_country_code"
down_revision = "0005_create_transaction_tables"
branch_labels = None
depends_on = None


def upgrade():
    # Raw layer should accept dirty/oversized values — cleaning rejects invalid ones.
    op.execute("""
        ALTER TABLE raw.raw_transactions
        ALTER COLUMN country_code TYPE VARCHAR(100);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE raw.raw_transactions
        ALTER COLUMN country_code TYPE VARCHAR(3);
    """)
