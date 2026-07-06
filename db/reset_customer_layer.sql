-- ============================================================
-- Reset and rebuild the customer data layer from scratch.
-- This script is intended for local development and fresh starts.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
q
DROP SCHEMA IF EXISTS raw CASCADE;
DROP SCHEMA IF EXISTS ops CASCADE;

CREATE SCHEMA raw;
CREATE SCHEMA clean;
CREATE SCHEMA gold;
CREATE SCHEMA ml;
CREATE SCHEMA fip;
CREATE SCHEMA ops;

-- ============================================================
-- OPS: Ingestion batches
-- ============================================================

CREATE TABLE ops.ingestion_batches (
    batch_id BIGSERIAL PRIMARY KEY,
    pipeline_name VARCHAR(100) NOT NULL,
    source_system VARCHAR(100) NOT NULL,
    source_entity VARCHAR(100) NOT NULL,
    source_file_name TEXT,
    source_file_path TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'started',
    records_expected INTEGER,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    CONSTRAINT chk_ingestion_batches_status
        CHECK (status IN ('started', 'completed', 'failed', 'completed_with_rejections')),
    CONSTRAINT chk_ingestion_batches_counts
        CHECK (
            records_inserted >= 0
            AND records_rejected >= 0
            AND (records_expected IS NULL OR records_expected >= 0)
        )
);

CREATE INDEX idx_ingestion_batches_source_entity
    ON ops.ingestion_batches (source_entity);

CREATE INDEX idx_ingestion_batches_status
    ON ops.ingestion_batches (status);

CREATE INDEX idx_ingestion_batches_started_at
    ON ops.ingestion_batches (started_at);

-- ============================================================
-- OPS: Rejected records
-- ============================================================

CREATE TABLE ops.rejected_records (
    rejected_record_id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id) ON DELETE CASCADE,
    source_schema VARCHAR(100) NOT NULL,
    source_table VARCHAR(100) NOT NULL,
    source_record_id TEXT,
    entity_name VARCHAR(100) NOT NULL,
    rule_code VARCHAR(100) NOT NULL,
    rule_description TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    severity VARCHAR(30) NOT NULL DEFAULT 'error',
    record_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_rejected_records_severity
        CHECK (severity IN ('warning', 'error', 'critical'))
);

CREATE INDEX idx_rejected_records_batch_id
    ON ops.rejected_records (batch_id);

CREATE INDEX idx_rejected_records_entity_name
    ON ops.rejected_records (entity_name);

CREATE INDEX idx_rejected_records_rule_code
    ON ops.rejected_records (rule_code);

CREATE INDEX idx_rejected_records_created_at
    ON ops.rejected_records (created_at);

CREATE UNIQUE INDEX uq_rejected_records_dedup
    ON ops.rejected_records (
        COALESCE(batch_id, -1),
        source_schema,
        source_table,
        COALESCE(source_record_id, ''),
        rule_code
    );

-- ============================================================
-- OPS: Data quality results
-- ============================================================

CREATE TABLE ops.data_quality_results (
    dq_result_id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT REFERENCES ops.ingestion_batches(batch_id),
    entity_name VARCHAR(100) NOT NULL,
    check_name VARCHAR(150) NOT NULL,
    check_status VARCHAR(30) NOT NULL,
    records_checked INTEGER NOT NULL DEFAULT 0,
    records_failed INTEGER NOT NULL DEFAULT 0,
    check_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_data_quality_results_status
        CHECK (check_status IN ('passed', 'failed', 'warning')),
    CONSTRAINT chk_data_quality_results_counts
        CHECK (records_checked >= 0 AND records_failed >= 0)
);

CREATE INDEX idx_data_quality_results_batch_id
    ON ops.data_quality_results (batch_id);

CREATE INDEX idx_data_quality_results_entity_name
    ON ops.data_quality_results (entity_name);

CREATE INDEX idx_data_quality_results_check_status
    ON ops.data_quality_results (check_status);

-- ============================================================
-- RAW: Customer records
-- ============================================================

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

CREATE INDEX idx_raw_customers_ingestion_batch_id
    ON raw.raw_customers (ingestion_batch_id);

CREATE INDEX idx_raw_customers_source_customer_id
    ON raw.raw_customers (source_customer_id);

CREATE INDEX idx_raw_customers_validation_status
    ON raw.raw_customers (validation_status);

CREATE INDEX idx_raw_customers_created_at
    ON raw.raw_customers (created_at);

CREATE INDEX idx_raw_customers_source_record_hash
    ON raw.raw_customers (source_record_hash);

CREATE UNIQUE INDEX uq_raw_customers_batch_row
    ON raw.raw_customers (ingestion_batch_id, source_row_number)
    WHERE source_row_number IS NOT NULL;

-- ============================================================
-- CLEAN: Customer dimension
-- ============================================================

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

CREATE INDEX idx_clean_customers_customer_status
    ON clean.customers (customer_status);

CREATE INDEX idx_clean_customers_region
    ON clean.customers (region);

CREATE INDEX idx_clean_customers_age_group
    ON clean.customers (age_group);

CREATE INDEX idx_clean_customers_income_band
    ON clean.customers (income_band);

CREATE INDEX idx_clean_customers_risk_rating
    ON clean.customers (risk_rating);

CREATE INDEX idx_clean_customers_last_seen_batch_id
    ON clean.customers (last_seen_batch_id);

-- ============================================================
-- CLEAN: Customer profiles
-- ============================================================

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

CREATE INDEX idx_customer_profiles_customer_id
    ON clean.customer_profiles (customer_id);

CREATE INDEX idx_customer_profiles_country_of_birth
    ON clean.customer_profiles (country_of_birth);

CREATE INDEX idx_customer_profiles_primary_phone_number
    ON clean.customer_profiles (primary_phone_number);

CREATE UNIQUE INDEX uq_customer_profiles_id_number
    ON clean.customer_profiles (id_number)
    WHERE id_number IS NOT NULL;

CREATE UNIQUE INDEX uq_customer_profiles_passport_number
    ON clean.customer_profiles (passport_number)
    WHERE passport_number IS NOT NULL;

-- ============================================================
-- Future analytics schemas reserved for later phases
-- ============================================================

COMMENT ON SCHEMA gold IS 'Reserved for analytics-ready outputs and gold tables.';
COMMENT ON SCHEMA ml IS 'Reserved for feature stores, models, and ML outputs.';
COMMENT ON SCHEMA fip IS 'Reserved for application-facing decisioning tables and services.';
