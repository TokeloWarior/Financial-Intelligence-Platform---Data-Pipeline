from alembic import op


revision = "0003_create_raw_tables"
down_revision = "0002_create_ops_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE raw.raw_customers (
        raw_customer_id BIGSERIAL PRIMARY KEY,
        ingestion_batch_id BIGINT NOT NULL REFERENCES ops.ingestion_batches(batch_id) ON DELETE CASCADE,
        source_system VARCHAR(100) NOT NULL DEFAULT 'synthetic_csv',
        source_file_name TEXT,
        source_row_number INTEGER,
        source_customer_id VARCHAR(100),
        customer_type VARCHAR(50),
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        id_number VARCHAR(30),
        passport_number VARCHAR(50),
        country_of_birth VARCHAR(100),
        primary_phone_number VARCHAR(30),
        secondary_phone_number VARCHAR(30),
        date_of_birth DATE,
        gender VARCHAR(30),
        region VARCHAR(100),
        city VARCHAR(100),
        employment_status VARCHAR(100),
        income_band VARCHAR(50),
        customer_status VARCHAR(50),
        onboarding_date DATE,
        kyc_status VARCHAR(50),
        risk_rating VARCHAR(50),
        raw_payload JSONB NOT NULL,
        source_record_hash VARCHAR(64),
        validation_status VARCHAR(30) NOT NULL DEFAULT 'pending',
        processed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_raw_customers_validation_status
            CHECK (validation_status IN ('pending', 'valid', 'rejected', 'processed')),
        CONSTRAINT chk_raw_customers_source_row_number
            CHECK (source_row_number IS NULL OR source_row_number > 0)
    );
    """)

    op.execute("CREATE INDEX idx_raw_customers_ingestion_batch_id ON raw.raw_customers (ingestion_batch_id);")
    op.execute("CREATE INDEX idx_raw_customers_source_customer_id ON raw.raw_customers (source_customer_id);")
    op.execute("CREATE INDEX idx_raw_customers_validation_status ON raw.raw_customers (validation_status);")
    op.execute("CREATE INDEX idx_raw_customers_created_at ON raw.raw_customers (created_at);")
    op.execute("CREATE INDEX idx_raw_customers_source_record_hash ON raw.raw_customers (source_record_hash);")

    op.execute("""
    CREATE UNIQUE INDEX uq_raw_customers_batch_row
        ON raw.raw_customers (ingestion_batch_id, source_row_number)
        WHERE source_row_number IS NOT NULL;
    """)

    op.execute("""
    CREATE TABLE raw.raw_accounts (
        raw_account_id BIGSERIAL PRIMARY KEY,
        ingestion_batch_id BIGINT NOT NULL REFERENCES ops.ingestion_batches(batch_id) ON DELETE CASCADE,
        source_system VARCHAR(100) NOT NULL DEFAULT 'synthetic_csv',
        source_file_name TEXT,
        source_row_number INTEGER,
        source_account_id VARCHAR(100) NOT NULL,
        source_customer_id VARCHAR(100),
        customer_link_type VARCHAR(30) NOT NULL,
        customer_link_key VARCHAR(200) NOT NULL,
        id_number VARCHAR(30),
        passport_number VARCHAR(50),
        country_of_birth VARCHAR(100),
        bank_name VARCHAR(120) NOT NULL,
        bank_code VARCHAR(20) NOT NULL,
        branch_name VARCHAR(120),
        account_number VARCHAR(50) NOT NULL,
        account_type VARCHAR(50) NOT NULL,
        account_currency VARCHAR(10) NOT NULL,
        account_status VARCHAR(30) NOT NULL,
        account_age_months INTEGER NOT NULL,
        opened_date DATE NOT NULL,
        account_balance NUMERIC(18, 2) NOT NULL,
        monthly_deposits NUMERIC(18, 2) NOT NULL,
        monthly_withdrawals NUMERIC(18, 2) NOT NULL,
        overdraft_limit NUMERIC(18, 2) NOT NULL DEFAULT 0,
        mobile_banking_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        raw_payload JSONB NOT NULL,
        source_record_hash VARCHAR(64),
        validation_status VARCHAR(30) NOT NULL DEFAULT 'pending',
        processed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_raw_accounts_validation_status
            CHECK (validation_status IN ('pending', 'valid', 'rejected', 'processed')),
        CONSTRAINT chk_raw_accounts_source_row_number
            CHECK (source_row_number IS NULL OR source_row_number > 0),
        CONSTRAINT chk_raw_accounts_account_age_months
            CHECK (account_age_months >= 0),
        CONSTRAINT chk_raw_accounts_account_balance
            CHECK (account_balance >= 0),
        CONSTRAINT chk_raw_accounts_monthly_deposits
            CHECK (monthly_deposits >= 0),
        CONSTRAINT chk_raw_accounts_monthly_withdrawals
            CHECK (monthly_withdrawals >= 0),
        CONSTRAINT chk_raw_accounts_overdraft_limit
            CHECK (overdraft_limit >= 0),
        CONSTRAINT chk_raw_accounts_customer_link_type
            CHECK (customer_link_type IN ('source_customer_id', 'id_number', 'passport_number'))
    );
    """)

    op.execute("CREATE INDEX idx_raw_accounts_ingestion_batch_id ON raw.raw_accounts (ingestion_batch_id);")
    op.execute("CREATE INDEX idx_raw_accounts_source_account_id ON raw.raw_accounts (source_account_id);")
    op.execute("CREATE INDEX idx_raw_accounts_source_customer_id ON raw.raw_accounts (source_customer_id);")
    op.execute("CREATE INDEX idx_raw_accounts_customer_link_key ON raw.raw_accounts (customer_link_key);")
    op.execute("CREATE INDEX idx_raw_accounts_account_number ON raw.raw_accounts (account_number);")
    op.execute("CREATE INDEX idx_raw_accounts_validation_status ON raw.raw_accounts (validation_status);")
    op.execute("CREATE INDEX idx_raw_accounts_created_at ON raw.raw_accounts (created_at);")

    op.execute("CREATE UNIQUE INDEX uq_raw_accounts_source_account_id ON raw.raw_accounts (source_account_id);")
    op.execute("CREATE UNIQUE INDEX uq_raw_accounts_customer_link_key ON raw.raw_accounts (customer_link_key);")
    op.execute("CREATE UNIQUE INDEX uq_raw_accounts_account_number ON raw.raw_accounts (account_number);")

    op.execute("""
    CREATE UNIQUE INDEX uq_raw_accounts_batch_row
        ON raw.raw_accounts (ingestion_batch_id, source_row_number)
        WHERE source_row_number IS NOT NULL;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS raw.raw_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw.raw_customers CASCADE;")