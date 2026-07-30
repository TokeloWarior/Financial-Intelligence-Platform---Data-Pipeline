from alembic import op


revision = "0004_create_clean_tables"
down_revision = "0003_create_raw_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE clean.customers (
        customer_id BIGSERIAL PRIMARY KEY,
        customer_key UUID NOT NULL DEFAULT gen_random_uuid(),
        source_customer_id VARCHAR(100) NOT NULL,
        customer_type VARCHAR(50) NOT NULL,
        date_of_birth DATE NOT NULL,
        age_group VARCHAR(20) NOT NULL,
        gender VARCHAR(30),
        region VARCHAR(100) NOT NULL,
        city VARCHAR(100),
        employment_type VARCHAR(100),
        income_band VARCHAR(50),
        customer_status VARCHAR(50) NOT NULL,
        onboarding_date DATE,
        kyc_status VARCHAR(50),
        risk_rating VARCHAR(50),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        source_system VARCHAR(100) NOT NULL,
        first_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        last_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_clean_customers_source_customer_id UNIQUE (source_customer_id),
        CONSTRAINT uq_clean_customers_customer_key UNIQUE (customer_key),
        CONSTRAINT chk_clean_customers_customer_type
            CHECK (customer_type IN ('individual', 'business')),
        CONSTRAINT chk_clean_customers_age_group
            CHECK (age_group IN ('under_18', '18-24', '25-34', '35-44', '45-54', '55-64', '65+')),
        CONSTRAINT chk_clean_customers_customer_status
            CHECK (customer_status IN ('active', 'inactive', 'suspended', 'closed')),
        CONSTRAINT chk_clean_customers_kyc_status
            CHECK (kyc_status IS NULL OR kyc_status IN ('not_started', 'pending', 'verified', 'failed', 'expired')),
        CONSTRAINT chk_clean_customers_risk_rating
            CHECK (risk_rating IS NULL OR risk_rating IN ('low', 'medium', 'high')),
        CONSTRAINT chk_clean_customers_income_band
            CHECK (
                income_band IS NULL OR income_band IN (
                    '0-4999',
                    '5000-9999',
                    '10000-19999',
                    '20000-39999',
                    '40000-79999',
                    '80000+',
                    'unknown'
                )
            )
    );
    """)

    op.execute("CREATE INDEX idx_clean_customers_customer_status ON clean.customers (customer_status);")
    op.execute("CREATE INDEX idx_clean_customers_region ON clean.customers (region);")
    op.execute("CREATE INDEX idx_clean_customers_age_group ON clean.customers (age_group);")
    op.execute("CREATE INDEX idx_clean_customers_income_band ON clean.customers (income_band);")
    op.execute("CREATE INDEX idx_clean_customers_risk_rating ON clean.customers (risk_rating);")
    op.execute("CREATE INDEX idx_clean_customers_last_seen_batch_id ON clean.customers (last_seen_batch_id);")

    op.execute("""
    CREATE TABLE clean.customer_profiles (
        customer_profile_id BIGSERIAL PRIMARY KEY,
        customer_profile_key UUID NOT NULL DEFAULT gen_random_uuid(),
        customer_id BIGINT NOT NULL REFERENCES clean.customers(customer_id) ON DELETE CASCADE,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        full_name VARCHAR(250) NOT NULL,
        identity_document_type VARCHAR(30) NOT NULL,
        id_number VARCHAR(30),
        passport_number VARCHAR(50),
        country_of_birth VARCHAR(100) NOT NULL,
        primary_phone_number VARCHAR(30) NOT NULL,
        secondary_phone_number VARCHAR(30),
        source_system VARCHAR(100) NOT NULL,
        first_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        last_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_customer_profiles_customer_id UNIQUE (customer_id),
        CONSTRAINT uq_customer_profiles_profile_key UNIQUE (customer_profile_key),
        CONSTRAINT chk_customer_profiles_identity_document_type
            CHECK (identity_document_type IN ('national_id', 'passport')),
        CONSTRAINT chk_customer_profiles_identity_document_present
            CHECK (id_number IS NOT NULL OR passport_number IS NOT NULL),
        CONSTRAINT chk_customer_profiles_primary_identifier_present
            CHECK (first_name IS NOT NULL AND last_name IS NOT NULL)
    );
    """)

    op.execute("CREATE INDEX idx_customer_profiles_customer_id ON clean.customer_profiles (customer_id);")
    op.execute("CREATE INDEX idx_customer_profiles_country_of_birth ON clean.customer_profiles (country_of_birth);")
    op.execute("CREATE INDEX idx_customer_profiles_primary_phone_number ON clean.customer_profiles (primary_phone_number);")

    op.execute("""
    CREATE UNIQUE INDEX uq_customer_profiles_id_number
        ON clean.customer_profiles (id_number)
        WHERE id_number IS NOT NULL;
    """)

    op.execute("""
    CREATE UNIQUE INDEX uq_customer_profiles_passport_number
        ON clean.customer_profiles (passport_number)
        WHERE passport_number IS NOT NULL;
    """)

    op.execute("""
    CREATE TABLE clean.accounts (
        account_id BIGSERIAL PRIMARY KEY,
        account_key UUID NOT NULL DEFAULT gen_random_uuid(),
        customer_id BIGINT NOT NULL REFERENCES clean.customers(customer_id) ON DELETE CASCADE,
        customer_profile_id BIGINT NOT NULL REFERENCES clean.customer_profiles(customer_profile_id) ON DELETE CASCADE,
        source_account_id VARCHAR(100) NOT NULL,
        source_customer_id VARCHAR(100),
        customer_link_type VARCHAR(30) NOT NULL,
        customer_link_key VARCHAR(200) NOT NULL,
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
        source_system VARCHAR(100) NOT NULL,
        first_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        last_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_clean_accounts_source_account_id UNIQUE (source_account_id),
        CONSTRAINT uq_clean_accounts_account_key UNIQUE (account_key),
        CONSTRAINT uq_clean_accounts_account_number UNIQUE (account_number),
        CONSTRAINT chk_clean_accounts_account_type
            CHECK (
                account_type IN (
                    'savings',
                    'transactional',
                    'cash_management',
                    'premium_current',
                    'business_current',
                    'business_savings',
                    'merchant_settlement'
                )
            ),
        CONSTRAINT chk_clean_accounts_account_status
            CHECK (account_status IN ('active', 'dormant', 'restricted', 'closed')),
        CONSTRAINT chk_clean_accounts_account_age_months
            CHECK (account_age_months >= 0),
        CONSTRAINT chk_clean_accounts_account_balance
            CHECK (account_balance >= 0),
        CONSTRAINT chk_clean_accounts_monthly_deposits
            CHECK (monthly_deposits >= 0),
        CONSTRAINT chk_clean_accounts_monthly_withdrawals
            CHECK (monthly_withdrawals >= 0),
        CONSTRAINT chk_clean_accounts_overdraft_limit
            CHECK (overdraft_limit >= 0),
        CONSTRAINT chk_clean_accounts_customer_link_type
            CHECK (customer_link_type IN ('source_customer_id', 'id_number', 'passport_number'))
    );
    """)

    op.execute("CREATE INDEX idx_clean_accounts_customer_id ON clean.accounts (customer_id);")
    op.execute("CREATE INDEX idx_clean_accounts_customer_profile_id ON clean.accounts (customer_profile_id);")
    op.execute("CREATE INDEX idx_clean_accounts_source_customer_id ON clean.accounts (source_customer_id);")
    op.execute("CREATE INDEX idx_clean_accounts_customer_link_key ON clean.accounts (customer_link_key);")
    op.execute("CREATE INDEX idx_clean_accounts_account_status ON clean.accounts (account_status);")
    op.execute("CREATE INDEX idx_clean_accounts_account_type ON clean.accounts (account_type);")
    op.execute("CREATE INDEX idx_clean_accounts_last_seen_batch_id ON clean.accounts (last_seen_batch_id);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS clean.accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS clean.customer_profiles CASCADE;")
    op.execute("DROP TABLE IF EXISTS clean.customers CASCADE;")