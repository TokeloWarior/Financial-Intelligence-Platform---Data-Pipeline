import csv
import hashlib
import json
from datetime import datetime
from io import StringIO
from pathlib import Path

from sqlalchemy import text

from pipeline.common.database import engine
from pipeline.common.pipeline_logging import logger
from pipeline.common.s3_storage import S3StorageClient


CUSTOMERS_FILE_PATH = Path("data/synthetic/customers.csv")
PIPELINE_NAME = "customer_raw_ingestion"
SOURCE_SYSTEM = "synthetic_csv"
SOURCE_ENTITY = "customers"


def blank_to_none(value: str | None) -> str | None:
    """
    Convert blank CSV values to None.

    Non-blank values are preserved as received as much as possible.
    For example, " CUST-999999 " remains " CUST-999999 ".
    """

    if value is None:
        return None

    if value.strip() == "":
        return None

    return value


def parse_date_safely(value: str | None):
    """
    Safely parse a date string.

    If blank or invalid, return None.
    The original bad value remains preserved in raw_payload.
    """

    value = blank_to_none(value)

    if value is None:
        return None

    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_source_record_hash(record: dict) -> str:
    """
    Create a stable SHA-256 hash for the raw source record.
    """

    canonical_record = json.dumps(
        record,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()


def read_customer_csv(file_path: Path) -> list[dict]:
    """
    Read customer records from CSV.
    """

    if not file_path.exists():
        raise FileNotFoundError(f"Customer file not found: {file_path}")

    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def read_customer_csv_from_s3(bucket_name: str, object_key: str) -> list[dict]:
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
    """
    Create an ingestion batch record and return the batch id.
    """

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
        "ingestion_mode": "raw_preserve_with_safe_type_parsing",
        "profile_fields_included": True,
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
    """
    Update the ingestion batch after processing.
    """

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


def insert_raw_customer(
    batch_id: int,
    source_row_number: int,
    record: dict,
    source_file_name: str,
) -> bool:
    """
    Insert one raw customer record.

    Business-invalid values are allowed into raw.
    Invalid dates are stored as NULL in typed date columns,
    while the original values remain in raw_payload.
    """

    query = text(
        """
        INSERT INTO raw.raw_customers (
            ingestion_batch_id,
            source_system,
            source_file_name,
            source_row_number,

            source_customer_id,
            customer_type,

            first_name,
            last_name,
            id_number,
            passport_number,
            country_of_birth,
            primary_phone_number,
            secondary_phone_number,

            date_of_birth,
            gender,
            region,
            city,
            employment_status,
            income_band,
            customer_status,
            onboarding_date,
            kyc_status,
            risk_rating,

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

            :source_customer_id,
            :customer_type,

            :first_name,
            :last_name,
            :id_number,
            :passport_number,
            :country_of_birth,
            :primary_phone_number,
            :secondary_phone_number,

            :date_of_birth,
            :gender,
            :region,
            :city,
            :employment_status,
            :income_band,
            :customer_status,
            :onboarding_date,
            :kyc_status,
            :risk_rating,

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
        "source_file_name": source_file_name,
        "source_row_number": source_row_number,

        "source_customer_id": blank_to_none(record.get("source_customer_id")),
        "customer_type": blank_to_none(record.get("customer_type")),

        "first_name": blank_to_none(record.get("first_name")),
        "last_name": blank_to_none(record.get("last_name")),
        "id_number": blank_to_none(record.get("id_number")),
        "passport_number": blank_to_none(record.get("passport_number")),
        "country_of_birth": blank_to_none(record.get("country_of_birth")),
        "primary_phone_number": blank_to_none(record.get("primary_phone_number")),
        "secondary_phone_number": blank_to_none(record.get("secondary_phone_number")),

        "date_of_birth": parse_date_safely(record.get("date_of_birth")),
        "gender": blank_to_none(record.get("gender")),
        "region": blank_to_none(record.get("region")),
        "city": blank_to_none(record.get("city")),
        "employment_status": blank_to_none(record.get("employment_status")),
        "income_band": blank_to_none(record.get("income_band")),
        "customer_status": blank_to_none(record.get("customer_status")),
        "onboarding_date": parse_date_safely(record.get("onboarding_date")),
        "kyc_status": blank_to_none(record.get("kyc_status")),
        "risk_rating": blank_to_none(record.get("risk_rating")),

        "raw_payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
        "source_record_hash": source_record_hash,
    }

    with engine.begin() as connection:
        existing_record = connection.execute(
            text(
                """
                SELECT 1
                FROM raw.raw_customers
                WHERE source_record_hash = :source_record_hash
                LIMIT 1;
                """
            ),
            {"source_record_hash": source_record_hash},
        ).first()

        if existing_record is not None:
            return False

        connection.execute(query, parameters)

    return True


def ingest_raw_customers(
    file_path: Path | str | None = None,
    bucket_name: str | None = None,
    object_key: str | None = None,
) -> None:
    """
    Main customer raw ingestion function.
    """

    logger.info("Starting customer raw ingestion")

    if bucket_name is not None or object_key is not None:
        if not bucket_name or not object_key:
            raise ValueError("Both bucket_name and object_key are required for S3 ingestion.")

        customer_records = read_customer_csv_from_s3(bucket_name=bucket_name, object_key=object_key)
        source_file_name = Path(object_key).name
        source_file_path = S3StorageClient.build_s3_uri(bucket_name, object_key)
        metadata_overrides = {
            "storage_provider": "aws_s3",
            "bucket_name": bucket_name,
            "object_key": object_key,
            "s3_uri": source_file_path,
        }
    else:
        resolved_file_path = Path(file_path) if file_path is not None else CUSTOMERS_FILE_PATH
        customer_records = read_customer_csv(resolved_file_path)
        source_file_name = resolved_file_path.name
        source_file_path = str(resolved_file_path)
        metadata_overrides = {
            "storage_provider": "local_filesystem",
        }

    records_expected = len(customer_records)

    batch_id = start_ingestion_batch(
        records_expected=records_expected,
        source_file_name=source_file_name,
        source_file_path=source_file_path,
        metadata_overrides=metadata_overrides,
    )

    print(f"Started ingestion batch: {batch_id}")
    print(f"Records expected: {records_expected}")
    logger.info(
        "Customer ingestion batch started: batch_id=%s records_expected=%s source=%s",
        batch_id,
        records_expected,
        source_file_path,
    )

    records_inserted = 0

    try:
        for source_row_number, record in enumerate(customer_records, start=1):
            inserted = insert_raw_customer(
                batch_id=batch_id,
                source_row_number=source_row_number,
                record=record,
                source_file_name=source_file_name,
            )
            records_inserted += int(inserted)

        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=0,
            status="completed",
        )

        print("Customer raw ingestion finished")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted: {records_inserted}")
        logger.info(
            "Completed customer raw ingestion: batch_id=%s records_inserted=%s records_skipped=%s",
            batch_id,
            records_inserted,
            records_expected - records_inserted,
        )

    except Exception as error:
        finish_ingestion_batch(
            batch_id=batch_id,
            records_inserted=records_inserted,
            records_rejected=records_expected - records_inserted,
            status="failed",
            error_message=str(error),
        )

        print("Customer raw ingestion failed")
        print(f"Batch id: {batch_id}")
        print(f"Records inserted before failure: {records_inserted}")
        print(f"Error: {error}")
        logger.exception(
            "Customer raw ingestion failed: batch_id=%s records_inserted=%s",
            batch_id,
            records_inserted,
        )

        raise


if __name__ == "__main__":
    ingest_raw_customers()