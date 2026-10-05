import importlib
from unittest.mock import Mock

import pytest


INGESTION_MODULES = [
    (
        "pipeline.ingestion.ingest_raw_customers",
        "ingest_raw_customers",
        "read_customer_csv",
        "insert_raw_customer",
        "customers.csv",
        "Customer raw ingestion failed",
    ),
    (
        "pipeline.ingestion.ingest_raw_accounts",
        "ingest_raw_accounts",
        "read_account_csv",
        "insert_raw_account",
        "accounts.csv",
        "Account raw ingestion failed",
    ),
    (
        "pipeline.ingestion.ingest_raw_transactions",
        "ingest_raw_transactions",
        "read_transaction_csv",
        "insert_raw_transaction",
        "transactions.csv",
        "Transaction raw ingestion failed",
    ),
]


SOURCE_ID_INGESTION_MODULES = [
    (
        "pipeline.ingestion.ingest_raw_customers",
        "insert_raw_customer",
        "source_customer_id",
    ),
    (
        "pipeline.ingestion.ingest_raw_transactions",
        "insert_raw_transaction",
        "source_transaction_id",
    ),
]


class FakeResult:
    def __init__(self, exists=False, rowcount=1):
        self.exists = exists
        self.rowcount = rowcount

    def first(self):
        return (1,) if self.exists else None


class FakeConnection:
    def __init__(self, existing_id):
        self.existing_id = existing_id
        self.statements = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.statements.append((sql, parameters))
        if sql.lstrip().startswith("SELECT 1"):
            return FakeResult(exists=self.existing_id)
        return FakeResult()


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.mark.parametrize(
    "module_name,insert_name,id_field",
    SOURCE_ID_INGESTION_MODULES,
)
@pytest.mark.parametrize("existing_id,expected_inserted", [(True, False), (False, True)])
def test_source_id_duplicate_check_uses_other_batches_only(
    monkeypatch,
    module_name,
    insert_name,
    id_field,
    existing_id,
    expected_inserted,
):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module(module_name)
    connection = FakeConnection(existing_id=existing_id)
    monkeypatch.setattr(module, "engine", FakeEngine(connection))
    record = {
        id_field: " SOURCE-001 ",
        "transaction_timestamp": "2026-10-05T12:00:00",
    }

    inserted = getattr(module, insert_name)(
        batch_id=42,
        source_row_number=1,
        record=record,
        source_file_name="input.csv",
    )

    assert inserted is expected_inserted
    lookup_sql, lookup_parameters = connection.statements[0]
    assert "ingestion_batch_id <> :batch_id" in lookup_sql
    assert lookup_parameters["batch_id"] == 42
    assert lookup_parameters[id_field] == "SOURCE-001"
    assert len(connection.statements) == (1 if existing_id else 2)


@pytest.mark.parametrize(
    "module_name,ingest_name,reader_name,insert_name,file_name,error_message",
    INGESTION_MODULES,
)
def test_failed_ingestion_logs_skipped_failed_and_unprocessed_counts(
    monkeypatch,
    module_name,
    ingest_name,
    reader_name,
    insert_name,
    file_name,
    error_message,
):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module(module_name)
    finish_calls = []
    insert_calls = 0
    log_exception = Mock()

    monkeypatch.setattr(
        module,
        reader_name,
        lambda file_path: [{"row": row_number} for row_number in range(1, 5)],
    )
    monkeypatch.setattr(module, "start_ingestion_batch", lambda **kwargs: 42)
    monkeypatch.setattr(
        module,
        "finish_ingestion_batch",
        lambda **kwargs: finish_calls.append(kwargs),
    )
    monkeypatch.setattr(module.logger, "exception", log_exception)

    def insert_record(**kwargs):
        nonlocal insert_calls
        insert_calls += 1
        if insert_calls == 3:
            raise RuntimeError("forced row failure")
        return insert_calls == 1

    monkeypatch.setattr(module, insert_name, insert_record)

    with pytest.raises(RuntimeError, match="forced row failure"):
        getattr(module, ingest_name)(file_path=file_name)

    assert finish_calls[-1]["status"] == "failed"
    assert finish_calls[-1]["records_inserted"] == 1
    assert finish_calls[-1]["records_rejected"] == 0
    assert "records_expected=%s" in log_exception.call_args.args[0]
    assert log_exception.call_args.args[1:] == (42, 4, 1, 1, 1, 1)
    assert error_message in log_exception.call_args.args[0]