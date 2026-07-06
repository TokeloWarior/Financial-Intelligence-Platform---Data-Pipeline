import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text

from pipeline.common.database import engine


ACCOUNTS_FILE_PATH = Path("data/synthetic/accounts.csv")
PIPELINE_NAME = "account_raw_ingestion"
SOURCE_SYSTEM = "synthetic_csv"
SOURCE_ENTITY = "accounts"


def blank_to_none(value):
    if value is None:
        return None

    if isinstance(value, str):
        if value.strip() == "":
            return None

    return value


def parse_date_safely(value: str | None):
    value = blank_to_none(value)

    if value is None:
        return None

    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_integer_safely(value):
    value = blank_to_none(value)

    if value is None:
        return None

    if isinstance(value, int):
        return value

    try:
        return int(value.strip())
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


def read_account_csv(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Account file not found: {file_path}")

    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def start_ingestion_batch(records_expected: int) -> int:
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
        "ingestion_mode": "raw_preserve_account_data",
        "linked_to_customer_profiles": True,
    }

    with engine.begin() as connection:
        batch_id = connection.execute(
            query,
            {
                "pipeline_name": PIPELINE_NAME,
                "source_system": SOURCE_SYSTEM,
                "source_entity": SOURCE_ENTITY,
                "source_file_name": ACCOUNTS_FILE_PATH.name,
                "source_file_path": str(ACCOUNTS_FILE_PATH),
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


def insert_raw_account(batch_id: int, source_row_number: int, record: dict) -> None:
    query = text(
        """
        INSERT INTO raw.raw_accounts (
            ingestion_batch_id,
            source_system,
            source_file_name,
            source_row_number,
            source_account_id,
            source_customer_id,
            customer_link_type,
            customer_link_key,
            id_number,
            passport_number,
            country_of_birth,
            bank_name,
            bank_code,
            branch_name,
            account_number,
            account_type,
            account_currency,
            account_status,
            account_age_months,
            opened_date,
            account_balance,
            monthly_deposits,
            monthly_withdrawals,
            overdraft_limit,
            mobile_banking_enabled,
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
            :source_account_id,
            :source_customer_id,
            :customer_link_type,
            :customer_link_key,
            :id_number,
            :passport_number,
            :country_of_birth,
            :bank_name,
            :bank_code,
            :branch_name,
            :account_number,
            :account_type,
            :account_currency,
            :account_status,
            :account_age_months,
            :opened_date,
            :account_balance,
            :monthly_deposits,
            :monthly_withdrawals,
            :overdraft_limit,
            :mobile_banking_enabled,
            CAST(:raw_payload AS JSONB),
            :source_record_hash,
            'pending',
            NOW()
        );
        """
    )

    raw_payload = dict(record)
    source_record_hash = calculate_source_record_hash(raw_payload)

    parameters = {
        "ingestion_batch_id": batch_id,
        "source_system": SOURCE_SYSTEM,
        "source_file_name": ACCOUNTS_FILE_PATH.name,
        "source_row_number": parse_integer_safely(record.get("source_row_number")),
        "source_account_id": blank_to_none(record.get("source_account_id")),
        "source_customer_id": blank_to_none(record.get("source_customer_id")),
        "customer_link_type": blank_to_none(record.get("customer_link_type")),
        "customer_link_key": blank_to_none(record.get("customer_link_key")),
        "id_number": blank_to_none(record.get("id_number")),
        "passport_number": blank_to_none(record.get("passport_number")),
        "country_of_birth": blank_to_none(record.get("country_of_birth")),
        "bank_name": blank_to_none(record.get("bank_name")),
        "bank_code": blank_to_none(record.get("bank_code")),
        "branch_name": blank_to_none(record.get("branch_name")),
        "account_number": blank_to_none(record.get("account_number")),
        "account_type": blank_to_none(record.get("account_type")),
        "account_currency": blank_to_none(record.get("account_currency")),
        "account_status": blank_to_none(record.get("account_status")),
        "account_age_months": parse_integer_safely(record.get("account_age_months")),
        "opened_date": parse_date_safely(record.get("opened_date")),
        "account_balance": parse_decimal_safely(record.get("account_balance")),
        "monthly_deposits": parse_decimal_safely(record.get("monthly_deposits")),
        "monthly_withdrawals": parse_decimal_safely(record.get("monthly_withdrawals")),
        "overdraft_limit": parse_decimal_safely(record.get("overdraft_limit")),
        "mobile_banking_enabled": parse_boolean_safely(record.get("mobile_banking_enabled")),
        "raw_payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
        "source_record_hash": source_record_hash,
    }

    with engine.begin() as connection:
        connection.execute(query, parameters)


def ingest_raw_accounts() -> None:
    account_records = read_account_csv(ACCOUNTS_FILE_PATH)
    records_expected = len(account_records)

    batch_id = start_ingestion_batch(records_expected)

    print(f"Started account ingestion batch: {batch_id}")
    print(f"Records expected: {records_expected}")

    records_inserted = 0

    try:
        for source_row_number, record in enumerate(account_records, start=1):
            record = {
                **record,
                "source_row_number": source_row_number,
            }
            insert_raw_account(batch_id, source_row_number, record)
            records_inserted += 1

        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=0,
            status="completed",
        )

        print("Raw account ingestion finished")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted: {records_inserted}")

    except Exception as error:
        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=records_expected - records_inserted,
            status="failed",
            error_message=str(error),
        )

        print("Raw account ingestion failed")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted before failure: {records_inserted}")
        print(f"Error: {error}")

        raise


if __name__ == "__main__":
    ingest_raw_accounts()
