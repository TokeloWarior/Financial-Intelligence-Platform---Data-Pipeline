-- =====================================================
-- Initial Pipeline Tables
-- Purpose:
-- 1. Track ingestion batches
-- 2. Store rejected records
-- 3. Store raw customer records
-- 4. Store clean customer records
-- =====================================================


-- =====================================================
-- Enable UUID generation
-- =====================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- =====================================================
-- OPS: Ingestion Batches
-- Tracks every pipeline ingestion run.
-- =====================================================
CREATE TABLE IF NOT EXISTS ops.ingestion_batches (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_name TEXT,

    records_received INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'running',

    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,

    error_message TEXT,

    CONSTRAINT chk_ingestion_batch_status
        CHECK (status IN ('running', 'successful', 'partial_success', 'failed'))
);


-- =====================================================
-- OPS: Rejected Records
-- Stores records that failed validation.
-- =====================================================
CREATE TABLE IF NOT EXISTS ops.rejected_records (
    rejected_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    batch_id UUID NOT NULL REFERENCES ops.ingestion_batches(batch_id)
        ON DELETE CASCADE,

    source_table TEXT NOT NULL,
    record_payload JSONB NOT NULL,
    rejection_reason TEXT NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);


-- =====================================================
-- RAW: Raw Customers
-- Stores customer records exactly as received.
-- =====================================================
CREATE TABLE IF NOT EXISTS raw.raw_customers (
    raw_customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_system TEXT NOT NULL,
    source_customer_id TEXT NOT NULL,

    full_name TEXT,
    date_of_birth DATE,
    gender TEXT,
    region TEXT,
    employment_status TEXT,
    income_band TEXT,
    customer_status TEXT,

    ingestion_batch_id UUID NOT NULL REFERENCES ops.ingestion_batches(batch_id)
        ON DELETE CASCADE,

    raw_payload JSONB NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);


-- =====================================================
-- CLEAN: Customers
-- Stores standardized and validated customer records.
-- =====================================================
CREATE TABLE IF NOT EXISTS clean.customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_customer_id TEXT UNIQUE NOT NULL,

    age_group TEXT,
    region TEXT,
    employment_type TEXT,
    income_band TEXT,
    customer_status TEXT NOT NULL,

    onboarded_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);


-- =====================================================
-- Indexes for performance
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_raw_customers_batch_id
ON raw.raw_customers(ingestion_batch_id);

CREATE INDEX IF NOT EXISTS idx_raw_customers_source_customer_id
ON raw.raw_customers(source_customer_id);

CREATE INDEX IF NOT EXISTS idx_clean_customers_source_customer_id
ON clean.customers(source_customer_id);

CREATE INDEX IF NOT EXISTS idx_rejected_records_batch_id
ON ops.rejected_records(batch_id);