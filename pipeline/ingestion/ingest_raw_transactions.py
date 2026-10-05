import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

from sqlalchemy import text

from pipeline.common.database import engine
from pipeline.common.pipeline_logging import logger
from pipeline.common.s3_storage import S3StorageClient


TRANSACTIONS_FILE_PATH = Path("data/synthetic/transactions.csv")
PIPELINE_NAME = "transaction_raw_ingestion"
SOURCE_SYSTEM = "synthetic_csv"
SOURCE_ENTITY = "transactions"


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    if value.strip() == "":
        return None

    return value


def parse_timestamp_safely(value: str | None):
    value = blank_to_none(value)

    if value is None:
        return None

    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_decimal_safely(value: str | None):
    value = blank_to_none(value)

    if value is None:
        return None

    try:
        return Decimal(value.strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_boolean_safely(value: str | None):
    value = blank_to_none(value)

    if value is None:
        return None

    normalized = value.strip().lower()

    if normalized in {"true", "1", "yes", "y"}:
        return True

    if normalized in {"false", "0", "no", "n"}:
        return False

    return None


def calculate_source_record_hash(record: dict) -> str:
    canonical_record = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()


def read_transaction_csv(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Transaction file not found: {file_path}")

    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def read_transaction_csv_from_s3(bucket_name: str, object_key: str) -> list[dict]:
    storage = S3StorageClient()
    csv_text = storage.get_object_text(bucket_name=bucket_name, object_key=object_key)
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader)


def start_ingestion_batch(
    records_expected: int,
    source_file_name: str,
    source_file_path: str,
    metadata_overrides: dict | None = None,
) -> int:
    query = text(
        """
        INSERT INTO ops.ingestion_batches (
            pipeline_name,
            source_system,
            source_entity,
            source_file_name,
            source_file_path,
            status,
            records_expected,
            records_inserted,
            records_rejected,
            started_at,
            metadata
        )
        VALUES (
            :pipeline_name,
            :source_system,
            :source_entity,
            :source_file_name,
            :source_file_path,
            'started',
            :records_expected,
            0,
            0,
            NOW(),
            CAST(:metadata AS JSONB)
        )
        RETURNING batch_id;
        """
    )

    metadata = {
        "file_type": "csv",
        "ingestion_mode": "raw_preserve_transaction_data",
        "linked_to_accounts": True,
    }

    if metadata_overrides:
        metadata.update(metadata_overrides)

    with engine.begin() as connection:
        batch_id = connection.execute(
            query,
            {
                "pipeline_name": PIPELINE_NAME,
                "source_system": SOURCE_SYSTEM,
                "source_entity": SOURCE_ENTITY,
                "source_file_name": source_file_name,
                "source_file_path": source_file_path,
                "records_expected": records_expected,
                "metadata": json.dumps(metadata),
            },
        ).scalar_one()

    return batch_id


def finish_ingestion_batch(
    batch_id: int,
    records_inserted: int,
    records_rejected: int = 0,
    status: str = "completed",
    error_message: str | None = None,
) -> None:
    query = text(
        """
        UPDATE ops.ingestion_batches
        SET
            status = :status,
            records_inserted = :records_inserted,
            records_rejected = :records_rejected,
            finished_at = NOW(),
            error_message = :error_message
        WHERE batch_id = :batch_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "batch_id": batch_id,
                "status": status,
                "records_inserted": records_inserted,
                "records_rejected": records_rejected,
                "error_message": error_message,
            },
        )


def insert_raw_transaction(
    batch_id: int,
    source_row_number: int,
    record: dict,
    source_file_name: str,
) -> bool:
    query = text(
        """
        INSERT INTO raw.raw_transactions (
            ingestion_batch_id,
            source_system,
            source_file_name,
            source_row_number,
            source_transaction_id,
            source_account_id,
            account_number,
            transaction_timestamp,
            transaction_type,
            transaction_channel,
            transaction_direction,
            transaction_amount,
            transaction_currency,
            counterparty_reference,
            merchant_category,
            transaction_status,
            running_balance,
            country_code,
            city,
            device_id,
            is_international,
            raw_payload,
            source_record_hash,
            validation_status,
            created_at
        )
        VALUES (
            :ingestion_batch_id,
            :source_system,
            :source_file_name,
            :source_row_number,
            :source_transaction_id,
            :source_account_id,
            :account_number,
            :transaction_timestamp,
            :transaction_type,
            :transaction_channel,
            :transaction_direction,
            :transaction_amount,
            :transaction_currency,
            :counterparty_reference,
            :merchant_category,
            :transaction_status,
            :running_balance,
            :country_code,
            :city,
            :device_id,
            :is_international,
            CAST(:raw_payload AS JSONB),
            :source_record_hash,
            'pending',
            NOW()
        )
        ON CONFLICT DO NOTHING;
        """
    )

    raw_payload = dict(record)
    source_record_hash = calculate_source_record_hash(raw_payload)

    parameters = {
        "ingestion_batch_id": batch_id,
        "source_system": SOURCE_SYSTEM,
        "source_file_name": source_file_name,
        "source_row_number": source_row_number,
        "source_transaction_id": blank_to_none(record.get("source_transaction_id")),
        "source_account_id": blank_to_none(record.get("source_account_id")),
        "account_number": blank_to_none(record.get("account_number")),
        "transaction_timestamp": parse_timestamp_safely(record.get("transaction_timestamp")),
        "transaction_type": blank_to_none(record.get("transaction_type")),
        "transaction_channel": blank_to_none(record.get("transaction_channel")),
        "transaction_direction": blank_to_none(record.get("transaction_direction")),
        "transaction_amount": parse_decimal_safely(record.get("transaction_amount")),
        "transaction_currency": blank_to_none(record.get("transaction_currency")),
        "counterparty_reference": blank_to_none(record.get("counterparty_reference")),
        "merchant_category": blank_to_none(record.get("merchant_category")),
        "transaction_status": blank_to_none(record.get("transaction_status")),
        "running_balance": parse_decimal_safely(record.get("running_balance")),
        "country_code": blank_to_none(record.get("country_code")),
        "city": blank_to_none(record.get("city")),
        "device_id": blank_to_none(record.get("device_id")),
        "is_international": parse_boolean_safely(record.get("is_international")),
        "raw_payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
        "source_record_hash": source_record_hash,
    }

    with engine.begin() as connection:
        result = connection.execute(query, parameters)

    return result.rowcount == 1


def ingest_raw_transactions(
    file_path: Path | str | None = None,
    bucket_name: str | None = None,
    object_key: str | None = None,
) -> None:
    logger.info("Starting transaction raw ingestion")
    if bucket_name is not None or object_key is not None:
        if not bucket_name or not object_key:
            raise ValueError("Both bucket_name and object_key are required for S3 ingestion.")

        transaction_records = read_transaction_csv_from_s3(
            bucket_name=bucket_name,
            object_key=object_key,
        )
        source_file_name = Path(object_key).name
        source_file_path = S3StorageClient.build_s3_uri(bucket_name, object_key)
        metadata_overrides = {
            "storage_provider": "aws_s3",
            "bucket_name": bucket_name,
            "object_key": object_key,
            "s3_uri": source_file_path,
        }
    else:
        resolved_file_path = Path(file_path) if file_path is not None else TRANSACTIONS_FILE_PATH
        transaction_records = read_transaction_csv(resolved_file_path)
        source_file_name = resolved_file_path.name
        source_file_path = str(resolved_file_path)
        metadata_overrides = {
            "storage_provider": "local_filesystem",
        }

    records_expected = len(transaction_records)

    batch_id = start_ingestion_batch(
        records_expected=records_expected,
        source_file_name=source_file_name,
        source_file_path=source_file_path,
        metadata_overrides=metadata_overrides,
    )

    print(f"Started transaction ingestion batch: {batch_id}")
    print(f"Records expected: {records_expected}")
    logger.info(
        "Transaction ingestion batch started: batch_id=%s records_expected=%s source=%s",
        batch_id,
        records_expected,
        source_file_path,
    )

    records_inserted = 0

    records_processed = 0
    record_in_progress = False

    try:
        for source_row_number, record in enumerate(transaction_records, start=1):
            record_in_progress = True
            inserted = insert_raw_transaction(
                batch_id=batch_id,
                source_row_number=source_row_number,
                record=record,
                source_file_name=source_file_name,
            )
            records_inserted += int(inserted)
            records_processed += 1
            record_in_progress = False

        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=0,
            status="completed",
        )

        print("Raw transaction ingestion finished")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted: {records_inserted}")
        logger.info(
            "Completed transaction raw ingestion: batch_id=%s records_inserted=%s records_skipped=%s",
            batch_id,
            records_inserted,
            records_expected - records_inserted,
        )

    except Exception as error:
        records_skipped = records_processed - records_inserted
        records_failed = int(record_in_progress)
        records_unprocessed = records_expected - records_processed - records_failed

        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=0,
            status="failed",
            error_message=str(error),
        )

        print("Raw transaction ingestion failed")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted before failure: {records_inserted}")
        print(f"Error: {error}")
        logger.exception(
            "Transaction raw ingestion failed: batch_id=%s records_expected=%s "
            "records_inserted=%s records_skipped=%s records_failed=%s "
            "records_unprocessed=%s",
            batch_id,
            records_expected,
            records_inserted,
            records_skipped,
            records_failed,
            records_unprocessed,
        )

        raise


if __name__ == "__main__":
    ingest_raw_transactions()
