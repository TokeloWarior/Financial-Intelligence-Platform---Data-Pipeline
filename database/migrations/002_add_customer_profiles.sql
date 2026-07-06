-- ============================================================
-- 002_add_customer_profiles.sql
-- Purpose:
-- Add production-ready customer profile fields and profile table.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Add customer profile fields to raw.raw_customers
-- ============================================================

ALTER TABLE raw.raw_customers
    ADD COLUMN IF NOT EXISTS first_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS last_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS id_number VARCHAR(30),
    ADD COLUMN IF NOT EXISTS passport_number VARCHAR(50),
    ADD COLUMN IF NOT EXISTS country_of_birth VARCHAR(100),
    ADD COLUMN IF NOT EXISTS primary_phone_number VARCHAR(30),
    ADD COLUMN IF NOT EXISTS secondary_phone_number VARCHAR(30);

CREATE INDEX IF NOT EXISTS idx_raw_customers_id_number
    ON raw.raw_customers (id_number);

CREATE INDEX IF NOT EXISTS idx_raw_customers_passport_number
    ON raw.raw_customers (passport_number);

-- ============================================================
-- Create clean.customer_profiles
-- ============================================================

CREATE TABLE IF NOT EXISTS clean.customer_profiles (
    customer_profile_id BIGSERIAL PRIMARY KEY,
    customer_profile_key UUID NOT NULL DEFAULT gen_random_uuid(),

    customer_id BIGINT NOT NULL
        REFERENCES clean.customers(customer_id)
        ON DELETE CASCADE,

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

    first_seen_batch_id BIGINT
        REFERENCES ops.ingestion_batches(batch_id),

    last_seen_batch_id BIGINT
        REFERENCES ops.ingestion_batches(batch_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_customer_profiles_customer_id
        UNIQUE (customer_id),

    CONSTRAINT uq_customer_profiles_profile_key
        UNIQUE (customer_profile_key),

    CONSTRAINT chk_customer_profiles_identity_document_type
        CHECK (identity_document_type IN ('south_african_id', 'passport')),

    CONSTRAINT chk_customer_profiles_identity_document_present
        CHECK (
            id_number IS NOT NULL
            OR passport_number IS NOT NULL
        ),

    CONSTRAINT chk_customer_profiles_sa_id_when_required
        CHECK (
            identity_document_type <> 'south_african_id'
            OR id_number IS NOT NULL
        ),

    CONSTRAINT chk_customer_profiles_passport_when_required
        CHECK (
            identity_document_type <> 'passport'
            OR passport_number IS NOT NULL
        )
);

-- ============================================================
-- Indexes for profile lookups
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_customer_profiles_customer_id
    ON clean.customer_profiles (customer_id);

CREATE INDEX IF NOT EXISTS idx_customer_profiles_country_of_birth
    ON clean.customer_profiles (country_of_birth);

CREATE INDEX IF NOT EXISTS idx_customer_profiles_primary_phone_number
    ON clean.customer_profiles (primary_phone_number);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_profiles_id_number
    ON clean.customer_profiles (id_number)
    WHERE id_number IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_profiles_passport_number
    ON clean.customer_profiles (passport_number)
    WHERE passport_number IS NOT NULL;