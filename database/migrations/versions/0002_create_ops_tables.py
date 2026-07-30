from alembic import op


revision = "0002_create_ops_tables"
down_revision = "0001_create_schemas"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
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
    """)

    op.execute("CREATE INDEX idx_ingestion_batches_source_entity ON ops.ingestion_batches (source_entity);")
    op.execute("CREATE INDEX idx_ingestion_batches_status ON ops.ingestion_batches (status);")
    op.execute("CREATE INDEX idx_ingestion_batches_started_at ON ops.ingestion_batches (started_at);")

    op.execute("""
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
    """)

    op.execute("CREATE INDEX idx_rejected_records_batch_id ON ops.rejected_records (batch_id);")
    op.execute("CREATE INDEX idx_rejected_records_entity_name ON ops.rejected_records (entity_name);")
    op.execute("CREATE INDEX idx_rejected_records_rule_code ON ops.rejected_records (rule_code);")
    op.execute("CREATE INDEX idx_rejected_records_created_at ON ops.rejected_records (created_at);")

    op.execute("""
    CREATE UNIQUE INDEX uq_rejected_records_dedup
        ON ops.rejected_records (
            COALESCE(batch_id, -1),
            source_schema,
            source_table,
            COALESCE(source_record_id, ''),
            rule_code
        );
    """)

    op.execute("""
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
    """)

    op.execute("CREATE INDEX idx_data_quality_results_batch_id ON ops.data_quality_results (batch_id);")
    op.execute("CREATE INDEX idx_data_quality_results_entity_name ON ops.data_quality_results (entity_name);")
    op.execute("CREATE INDEX idx_data_quality_results_check_status ON ops.data_quality_results (check_status);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS ops.data_quality_results CASCADE;")
    op.execute("DROP TABLE IF EXISTS ops.rejected_records CASCADE;")
    op.execute("DROP TABLE IF EXISTS ops.ingestion_batches CASCADE;")