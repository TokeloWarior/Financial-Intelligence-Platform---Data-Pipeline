# Financial & Mobility Intelligence Platform

This repository is a public portfolio project that demonstrates data engineering, analytics, and software development skills through a layered customer-data pipeline.

It is published for showcasing capability, architecture thinking, and implementation style. It is not intended to be used as a production service, and it is not maintained as a supported public application for reuse as someone else’s own project.

The README is aligned to the platform plan in [documents/Financial_&_Mobility_Intelligence_Platform.docx](documents/Financial_&_Mobility_Intelligence_Platform.docx).

## What This Project Shows

This codebase demonstrates how to design and implement a small but realistic data platform that:

- generates synthetic customer, account, and transaction data
- uploads generated files to AWS S3 with date-partitioned object keys
- ingests raw records into a PostgreSQL raw layer with full traceability
- validates records against business and data-quality rules, rejecting bad records to an audit table
- cleans and standardizes valid records into a curated layer
- runs automated data-quality checks against the clean layer
- orchestrates the full pipeline end-to-end using Prefect flows
- prepares the foundation for analytics, reporting, and downstream decision support

The goal is to show end-to-end data engineering practice rather than a toy script or a single isolated transformation.

## Platform Summary

The platform plan describes a layered flow from source systems to business insight.

```mermaid
flowchart LR

A[External Data Sources] --> B[Ingestion Layer]
B --> C[Raw Data Layer]
C --> D[Validation Layer]
D --> E[Clean Data Layer]
E --> F[Feature Engineering Layer]
F --> G[Analytics Gold Layer]

G --> H[Financial Intelligence Platform]

subgraph FIP [Financial Intelligence Platform]
        H --> I[Decision Engine]
        H --> J[Machine Learning Models]
        H --> K[Customer Segmentation]
        H --> L[Dashboards & APIs]
end
```

## How The Flow Works

### 1. Synthetic Data Generation

Generators produce realistic but fake data for customers, accounts, and transactions. Each generator deliberately includes a percentage of invalid records to exercise the validation and rejection logic downstream.

### 2. S3 Upload

Generated CSV files are uploaded to AWS S3 using date-partitioned object keys (`entity/year=YYYY/month=MM/day=DD/filename.csv`). Upload metadata including bucket, key, size, and ETag is tracked per dataset.

### 3. Ingestion Layer

The ingestion step reads files from S3 (or locally for manual runs) and writes every row into the raw PostgreSQL layer. Ingestion is tracked through `ops.ingestion_batches`, which records expected and inserted counts, status, and metadata.

### 4. Raw Data Layer

Raw records are preserved in their original form so the pipeline can audit, reprocess, and troubleshoot without losing the original payload. Every raw table stores `raw_payload` as JSONB alongside typed columns. Validation status is tracked per record (`pending`, `processed`, `rejected`).

### 5. Validation and Cleaning Layer

The cleaning step runs validation rules against each pending raw record before inserting into the clean layer:

- required field presence
- ID and date format checks
- region and city name validation
- duplicate detection (within batch and against existing clean records)
- passport number uniqueness enforcement
- age and onboarding date constraints
- phone number format checks

Records that fail any rule are written to `ops.rejected_records` with the rule code, description, and full rejection reason. Records that pass all rules are upserted into the clean layer.

### 6. Clean Data Layer

Cleaned records are standardized for analytics by normalizing text, converting empty optional fields to `NULL`, deriving age groups, mapping employment types, and upserting curated rows. The clean layer enforces stricter constraints than the raw layer (e.g. unique passport numbers, check constraints on country codes).

### 7. Data Quality Checks

After cleaning, automated DQ checks run against the clean layer and write results to `ops.data_quality_results`. Checks cover row counts, null rates, referential integrity, and domain coverage.

### 8. Prefect Orchestration

A single Prefect flow (`run_synthetic_ingestion_flow`) coordinates all steps end-to-end for every registered dataset:

```
generate → upload to S3 → ingest → clean → DQ checks → cleanup local files
```

New datasets can be added by registering one entry in `pipeline/common/synthetic_pipeline_registry.py`.

## Data Flow

```mermaid
sequenceDiagram
        participant Gen as Generator
        participant S3 as AWS S3
        participant Raw as Raw Layer (PostgreSQL)
        participant Clean as Clean Layer (PostgreSQL)
        participant Ops as Ops Layer (PostgreSQL)

        Gen->>S3: Upload date-partitioned CSV
        S3->>Raw: Ingest raw records (batch tracked)
        Raw->>Clean: Validate → reject or upsert
        Clean->>Ops: Write DQ check results
        Raw->>Ops: Write rejected records with rule codes
        Raw->>Ops: Update ingestion batch status
```

## Database Schema

The pipeline uses three PostgreSQL schemas:

| Schema | Purpose |
|--------|---------|
| `ops`  | Pipeline operations: `ingestion_batches`, `rejected_records`, `data_quality_results` |
| `raw`  | Raw ingested records: `raw_customers`, `raw_accounts`, `raw_transactions` |
| `clean` | Curated records: `customers`, `customer_profiles`, `accounts`, `transactions` |

Migrations are managed with Alembic. Migration files live in `database/migrations/versions/`.

## What Runs In This Repository

The current codebase includes the following runnable pieces:

- synthetic customer generation in `pipeline/ingestion/generate_customers.py`
- synthetic account generation in `pipeline/ingestion/generate_accounts.py`
- synthetic transaction generation in `pipeline/ingestion/generate_transactions.py`
- S3 upload for all synthetic files in `pipeline/ingestion/upload_synthetic_to_s3.py`
- raw customer ingestion in `pipeline/ingestion/ingest_raw_customers.py`
- raw account ingestion in `pipeline/ingestion/ingest_raw_accounts.py`
- raw transaction ingestion in `pipeline/ingestion/ingest_raw_transactions.py`
- customer cleaning and validation in `pipeline/cleaning/clean_customers.py`
- account cleaning in `pipeline/cleaning/clean_accounts.py`
- transaction cleaning in `pipeline/cleaning/clean_transactions.py`
- customer data-quality checks in `pipeline/validation/customer_data_quality.py`
- transaction data-quality checks in `pipeline/validation/transaction_data_quality.py`
- dataset registry in `pipeline/common/synthetic_pipeline_registry.py`
- Prefect orchestration flow in `pipeline/flows/run_synthetic_ingestion_flow.py`
- database connection smoke test in `pipeline/utils/db.py`

## Requirements

You will need:

- Python 3.10 or newer
- Docker and Docker Compose
- PostgreSQL 17 (via Docker)
- AWS credentials with S3 access
- a local `.env` file with database and AWS settings

The Python dependencies are listed in [requirements.txt](requirements.txt).

## Configuration

The code loads environment variables through `python-dotenv`. Create a `.env` file in the project root with the following variables:

```env
# PostgreSQL
DATABASE_URL=postgresql+psycopg://fip_user:fip_password@localhost:5432/fip_db
POSTGRES_USER=fip_user
POSTGRES_PASSWORD=fip_password
POSTGRES_DB=fip_db
POSTGRES_HOST=localhost
POSTGRES_PORT1=5432
POSTGRES_PORT2=5432
CONTAINER_NAME=fip_postgres

# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=your_region

# S3 Buckets
FIP_ENV=dev
S3_SYNTHETIC_DATA_BUCKET=your-synthetic-data-bucket
```

## Local Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start PostgreSQL
docker compose up -d

# 4. Apply all database migrations
alembic upgrade head
```

## Running The Pipeline

### Option A — Automated Flow (recommended)

Run the full pipeline for all datasets in one command:

```bash
python -m pipeline.flows.run_synthetic_ingestion_flow
```

This generates data, uploads to S3, ingests, cleans, and runs DQ checks for customers, accounts, and transactions automatically. Local CSV files are deleted after a successful run.

### Option B — Manual Step-by-Step

Run each step individually in this order:

```bash
# Generate synthetic data
python -m pipeline.ingestion.generate_customers
python -m pipeline.ingestion.generate_accounts
python -m pipeline.ingestion.generate_transactions

# Upload to S3
python -m pipeline.ingestion.upload_synthetic_to_s3

# Ingest raw records
python -m pipeline.ingestion.ingest_raw_customers
python -m pipeline.ingestion.ingest_raw_accounts
python -m pipeline.ingestion.ingest_raw_transactions

# Clean and validate
python -m pipeline.cleaning.clean_customers
python -m pipeline.cleaning.clean_accounts
python -m pipeline.cleaning.clean_transactions

# Run data quality checks
python -m pipeline.validation.customer_data_quality
python -m pipeline.validation.transaction_data_quality
```

## Verifying The Pipeline After A Run

Connect to the database and run these queries to confirm the pipeline completed correctly:

```sql
-- Batch status for all 3 entities
SELECT batch_id, source_entity, status, records_expected,
       records_inserted, records_rejected
FROM ops.ingestion_batches
ORDER BY batch_id;

-- Raw layer: confirm no records left pending
SELECT 'customers' AS entity, COUNT(*),
       COUNT(*) FILTER (WHERE validation_status = 'processed') AS processed,
       COUNT(*) FILTER (WHERE validation_status = 'rejected') AS rejected,
       COUNT(*) FILTER (WHERE validation_status = 'pending') AS pending
FROM raw.raw_customers
UNION ALL
SELECT 'accounts', COUNT(*),
       COUNT(*) FILTER (WHERE validation_status = 'processed'),
       COUNT(*) FILTER (WHERE validation_status = 'rejected'),
       COUNT(*) FILTER (WHERE validation_status = 'pending')
FROM raw.raw_accounts
UNION ALL
SELECT 'transactions', COUNT(*),
       COUNT(*) FILTER (WHERE validation_status = 'processed'),
       COUNT(*) FILTER (WHERE validation_status = 'rejected'),
       COUNT(*) FILTER (WHERE validation_status = 'pending')
FROM raw.raw_transactions;

-- Clean layer record counts
SELECT 'customers' AS entity, COUNT(*) FROM clean.customers
UNION ALL
SELECT 'customer_profiles', COUNT(*) FROM clean.customer_profiles
UNION ALL
SELECT 'accounts', COUNT(*) FROM clean.accounts
UNION ALL
SELECT 'transactions', COUNT(*) FROM clean.transactions;

-- Top rejection reasons by entity
SELECT source_table, rule_code, COUNT(*) AS total
FROM ops.rejected_records
GROUP BY source_table, rule_code
ORDER BY source_table, total DESC;

-- Referential integrity: no orphaned transactions or accounts
SELECT COUNT(*) AS orphaned_transactions
FROM clean.transactions t
LEFT JOIN clean.accounts a ON t.account_id = a.account_id
WHERE a.account_id IS NULL;

SELECT COUNT(*) AS orphaned_accounts
FROM clean.accounts a
LEFT JOIN clean.customers c ON a.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

**Expected results:**
- All batches: `completed` or `completed_with_rejections` (never `failed`)
- `pending` count: `0` across all raw tables
- Orphaned records: `0` for both queries
- Approximately 272/300 customers and accounts pass cleaning (30 deliberately invalid)
- Approximately 2900+/3302 transactions pass cleaning

## Project Structure

```text
pipeline/
    cleaning/           # Per-entity cleaning scripts (validate → reject or upsert)
    common/             # Shared utilities: database, registry
    features/           # Feature engineering (planned)
    flows/              # Prefect orchestration flows
    ingestion/          # Generators and raw ingestion scripts
    utils/              # Database connection helpers
    validation/         # Validators, DQ checks, smoke tests
database/
    migrations/         # Alembic migration files
data/
    processed/
    synthetic/          # Generated CSV files (deleted after successful flow run)
documents/              # Platform plan document
docker-compose.yml
requirements.txt
alembic.ini
```

## Adding A New Data Domain

To add a new synthetic dataset to the automated flow:

1. Create a generator in `pipeline/ingestion/generate_<entity>.py`
2. Create an ingestion script in `pipeline/ingestion/ingest_raw_<entity>.py`
3. Create a cleaning script in `pipeline/cleaning/clean_<entity>.py`
4. Create validators in `pipeline/validation/<entity>_validators.py`
5. Create DQ checks in `pipeline/validation/<entity>_data_quality.py`
6. Add a migration for the raw and clean tables in `database/migrations/versions/`
7. Register the dataset in `pipeline/common/synthetic_pipeline_registry.py`

The Prefect flow picks up the new entry automatically — no changes to the flow itself are needed.

## Skill Signals This Project Demonstrates

This repository highlights practical experience in:

- data pipeline design and layered architecture
- Python application structure and module organization
- PostgreSQL-backed workflows with schema separation
- Alembic database migration management
- validation, data quality control, and rejection auditing
- AWS S3 integration with date-partitioned storage
- Prefect orchestration with reusable task patterns
- reproducible synthetic data generation
- environment-driven configuration
- documentation and portfolio presentation

## Business And Engineering Value

From a portfolio perspective, this project demonstrates that you can build a realistic engineering workflow that supports business analysis, not just isolated scripts.


- data engineering system design
- pipeline implementation
- SQL and database interaction
- validation logic
- maintainable code organization
- technical documentation

## Future Improvements

The platform plan also leaves room for future work such as:

- feature store integration
- streaming ingestion
- model scoring services
- automated orchestration
- richer data lineage and observability
- production-grade deployment patterns

## Reference Material

- [Platform plan source document](documents/Financial_&_Mobility_Intelligence_Platform.docx)
- [Repository README](README.md)

## Project Positioning

This repository is public for portfolio and skill-advertising purposes only. The design, wording, and structure are intended to show how I approach data engineering and software development work.

It should be treated as a demonstration repository, not as a supported product, hosted service, or turnkey business solution.