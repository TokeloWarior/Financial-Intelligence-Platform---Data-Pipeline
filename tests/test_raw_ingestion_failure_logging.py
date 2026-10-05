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