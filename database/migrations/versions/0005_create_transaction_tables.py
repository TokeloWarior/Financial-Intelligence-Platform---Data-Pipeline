from alembic import op


revision = "0005_create_transaction_tables"
down_revision = "0004_create_clean_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE raw.raw_transactions (
        raw_transaction_id BIGSERIAL PRIMARY KEY,
        ingestion_batch_id BIGINT NOT NULL REFERENCES ops.ingestion_batches(batch_id) ON DELETE CASCADE,
        source_system VARCHAR(100) NOT NULL DEFAULT 'synthetic_csv',
        source_file_name TEXT,
        source_row_number INTEGER,
        source_transaction_id VARCHAR(100),
        source_account_id VARCHAR(100),
        account_number VARCHAR(50),
        transaction_timestamp TIMESTAMPTZ,
        transaction_type VARCHAR(40),
        transaction_channel VARCHAR(40),
        transaction_direction VARCHAR(20),
        transaction_amount NUMERIC(18, 2),
        transaction_currency VARCHAR(10),
        counterparty_reference VARCHAR(150),
        merchant_category VARCHAR(100),
        transaction_status VARCHAR(30),
        running_balance NUMERIC(18, 2),
        country_code VARCHAR(3),
        city VARCHAR(100),
        device_id VARCHAR(100),
        is_international BOOLEAN,
        raw_payload JSONB NOT NULL,
        source_record_hash VARCHAR(64),
        validation_status VARCHAR(30) NOT NULL DEFAULT 'pending',
        processed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_raw_transactions_validation_status
            CHECK (validation_status IN ('pending', 'valid', 'rejected', 'processed')),
        CONSTRAINT chk_raw_transactions_source_row_number
            CHECK (source_row_number IS NULL OR source_row_number > 0)
    );
    """)

    op.execute("CREATE INDEX idx_raw_transactions_ingestion_batch_id ON raw.raw_transactions (ingestion_batch_id);")
    op.execute("CREATE INDEX idx_raw_transactions_source_transaction_id ON raw.raw_transactions (source_transaction_id);")
    op.execute("CREATE INDEX idx_raw_transactions_source_account_id ON raw.raw_transactions (source_account_id);")
    op.execute("CREATE INDEX idx_raw_transactions_account_number ON raw.raw_transactions (account_number);")
    op.execute("CREATE INDEX idx_raw_transactions_transaction_timestamp ON raw.raw_transactions (transaction_timestamp);")
    op.execute("CREATE INDEX idx_raw_transactions_validation_status ON raw.raw_transactions (validation_status);")
    op.execute("CREATE INDEX idx_raw_transactions_created_at ON raw.raw_transactions (created_at);")
    op.execute("CREATE INDEX idx_raw_transactions_source_record_hash ON raw.raw_transactions (source_record_hash);")

    op.execute("""
    CREATE UNIQUE INDEX uq_raw_transactions_batch_row
        ON raw.raw_transactions (ingestion_batch_id, source_row_number)
        WHERE source_row_number IS NOT NULL;
    """)

    op.execute("""
    CREATE TABLE clean.transactions (
        transaction_id BIGSERIAL PRIMARY KEY,
        transaction_key UUID NOT NULL DEFAULT gen_random_uuid(),
        account_id BIGINT NOT NULL REFERENCES clean.accounts(account_id) ON DELETE CASCADE,
        customer_id BIGINT NOT NULL REFERENCES clean.customers(customer_id) ON DELETE CASCADE,
        source_transaction_id VARCHAR(100) NOT NULL,
        source_account_id VARCHAR(100),
        account_number VARCHAR(50) NOT NULL,
        transaction_timestamp TIMESTAMPTZ NOT NULL,
        transaction_date DATE NOT NULL,
        transaction_type VARCHAR(40) NOT NULL,
        transaction_channel VARCHAR(40) NOT NULL,
        transaction_direction VARCHAR(20) NOT NULL,
        transaction_amount NUMERIC(18, 2) NOT NULL,
        transaction_currency VARCHAR(10) NOT NULL,
        counterparty_reference VARCHAR(150),
        merchant_category VARCHAR(100),
        transaction_status VARCHAR(30) NOT NULL,
        running_balance NUMERIC(18, 2),
        country_code VARCHAR(3),
        city VARCHAR(100),
        device_id VARCHAR(100),
        is_international BOOLEAN NOT NULL DEFAULT FALSE,
        source_system VARCHAR(100) NOT NULL,
        first_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        last_seen_batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_clean_transactions_source_transaction_id UNIQUE (source_transaction_id),
        CONSTRAINT uq_clean_transactions_transaction_key UNIQUE (transaction_key),
        CONSTRAINT chk_clean_transactions_transaction_type
            CHECK (
                transaction_type IN (
                    'deposit',
                    'withdrawal',
                    'purchase',
                    'transfer_in',
                    'transfer_out',
                    'bill_payment',
                    'cash_withdrawal',
                    'salary',
                    'fee',
                    'interest',
                    'refund'
                )
            ),
        CONSTRAINT chk_clean_transactions_transaction_channel
            CHECK (
                transaction_channel IN (
                    'branch',
                    'atm',
                    'mobile_app',
                    'online_banking',
                    'card_pos',
                    'eft',
                    'merchant_settlement'
                )
            ),
        CONSTRAINT chk_clean_transactions_transaction_direction
            CHECK (transaction_direction IN ('credit', 'debit')),
        CONSTRAINT chk_clean_transactions_transaction_amount
            CHECK (transaction_amount > 0),
        CONSTRAINT chk_clean_transactions_transaction_currency
            CHECK (char_length(transaction_currency) BETWEEN 3 AND 10),
        CONSTRAINT chk_clean_transactions_transaction_status
            CHECK (transaction_status IN ('posted', 'pending', 'reversed')),
        CONSTRAINT chk_clean_transactions_running_balance
            CHECK (running_balance IS NULL OR running_balance >= 0),
        CONSTRAINT chk_clean_transactions_country_code
            CHECK (country_code IS NULL OR char_length(country_code) BETWEEN 2 AND 3)
    );
    """)

    op.execute("CREATE INDEX idx_clean_transactions_account_id ON clean.transactions (account_id);")
    op.execute("CREATE INDEX idx_clean_transactions_customer_id ON clean.transactions (customer_id);")
    op.execute("CREATE INDEX idx_clean_transactions_source_account_id ON clean.transactions (source_account_id);")
    op.execute("CREATE INDEX idx_clean_transactions_account_number ON clean.transactions (account_number);")
    op.execute("CREATE INDEX idx_clean_transactions_transaction_date ON clean.transactions (transaction_date);")
    op.execute("CREATE INDEX idx_clean_transactions_transaction_type ON clean.transactions (transaction_type);")
    op.execute("CREATE INDEX idx_clean_transactions_transaction_channel ON clean.transactions (transaction_channel);")
    op.execute("CREATE INDEX idx_clean_transactions_transaction_status ON clean.transactions (transaction_status);")
    op.execute("CREATE INDEX idx_clean_transactions_last_seen_batch_id ON clean.transactions (last_seen_batch_id);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS clean.transactions CASCADE;")
    op.execute("DROP TABLE IF EXISTS raw.raw_transactions CASCADE;")
