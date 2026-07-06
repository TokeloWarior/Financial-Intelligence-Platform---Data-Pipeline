import json
from datetime import date, datetime

from sqlalchemy import text

from pipeline.common.database import engine
from pipeline.validation.customer_validators import validate_raw_customer


def calculate_age(date_of_birth: date) -> int:
    """
    Calculate a customer's age from date_of_birth.
    """

    today = date.today()

    age = today.year - date_of_birth.year

    has_not_had_birthday_this_year = (today.month, today.day) < (
        date_of_birth.month,
        date_of_birth.day,
    )

    if has_not_had_birthday_this_year:
        age -= 1

    return age


def derive_age_group(date_of_birth: date) -> str:
    """
    Convert date_of_birth into an analytics-friendly age group.
    """

    age = calculate_age(date_of_birth)

    if age < 18:
        return "under_18"
    if age <= 24:
        return "18-24"
    if age <= 34:
        return "25-34"
    if age <= 44:
        return "35-44"
    if age <= 54:
        return "45-54"
    if age <= 64:
        return "55-64"

    return "65+"


def standardize_text(value: str | None) -> str | None:
    """
    Trim string values before loading into the clean layer.
    """

    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    return value


def standardize_employment_type(employment_status: str | None) -> str | None:
    """
    Standardize raw employment_status into clean employment_type.
    """

    employment_status = standardize_text(employment_status)

    if employment_status is None:
        return None

    value = employment_status.lower()

    mapping = {
        "employed": "employed",
        "self_employed": "self_employed",
        "self-employed": "self_employed",
        "unemployed": "unemployed",
        "student": "student",
        "retired": "retired",
    }

    return mapping.get(value, "unknown")


def is_active_customer(customer_status: str) -> bool:
    """
    Derive active customer flag from customer_status.
    """

    return customer_status == "active"


def fetch_pending_raw_customers() -> list[dict]:
    """
    Fetch raw customer records that have not yet been validated/processed.
    """

    query = text(
        """
        SELECT
            raw_customer_id,
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
        FROM raw.raw_customers
        WHERE validation_status = 'pending'
        ORDER BY ingestion_batch_id, source_row_number, raw_customer_id;
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query)
        rows = result.mappings().all()

    return [dict(row) for row in rows]


def find_duplicate_source_customer_ids(raw_customers: list[dict]) -> set[str]:
    """
    Find source_customer_id values that appear more than once in the pending records.

    The comparison uses trimmed values so that accidental whitespace does not hide duplicates.
    """

    counts: dict[str, int] = {}

    for raw_customer in raw_customers:
        source_customer_id = raw_customer.get("source_customer_id")

        if source_customer_id is None:
            continue

        trimmed_customer_id = str(source_customer_id).strip()

        if trimmed_customer_id == "":
            continue

        counts[trimmed_customer_id] = counts.get(trimmed_customer_id, 0) + 1

    return {
        source_customer_id
        for source_customer_id, count in counts.items()
        if count > 1
    }


def build_full_name(first_name: str | None, last_name: str | None) -> str:
    """
    Build a display name from first and last name parts.
    """

    name_parts = [part for part in [standardize_text(first_name), standardize_text(last_name)] if part]

    return " ".join(name_parts)


def determine_identity_document_type(raw_customer: dict) -> str:
    """
    Determine the profile identity document type from available source fields.
    """

    if standardize_text(raw_customer.get("passport_number")) is not None:
        return "passport"

    return "national_id"


def insert_clean_customer(raw_customer: dict) -> int:
    """
    Insert or update a validated customer into clean.customers.

    Uses ON CONFLICT so the pipeline can be safely re-run.
    """

    source_customer_id = standardize_text(raw_customer["source_customer_id"])
    customer_type = standardize_text(raw_customer["customer_type"])
    gender = standardize_text(raw_customer["gender"])
    region = standardize_text(raw_customer["region"])
    city = standardize_text(raw_customer["city"])
    employment_type = standardize_employment_type(raw_customer["employment_status"])
    income_band = standardize_text(raw_customer["income_band"])
    customer_status = standardize_text(raw_customer["customer_status"])
    kyc_status = standardize_text(raw_customer["kyc_status"])
    risk_rating = standardize_text(raw_customer["risk_rating"])

    age_group = derive_age_group(raw_customer["date_of_birth"])
    is_active = is_active_customer(customer_status)

    query = text(
        """
        INSERT INTO clean.customers (
            source_customer_id,
            customer_type,
            date_of_birth,
            age_group,
            gender,
            region,
            city,
            employment_type,
            income_band,
            customer_status,
            onboarding_date,
            kyc_status,
            risk_rating,
            is_active,
            source_system,
            first_seen_batch_id,
            last_seen_batch_id,
            created_at,
            updated_at
        )
        VALUES (
            :source_customer_id,
            :customer_type,
            :date_of_birth,
            :age_group,
            :gender,
            :region,
            :city,
            :employment_type,
            :income_band,
            :customer_status,
            :onboarding_date,
            :kyc_status,
            :risk_rating,
            :is_active,
            :source_system,
            :first_seen_batch_id,
            :last_seen_batch_id,
            NOW(),
            NOW()
        )
        ON CONFLICT (source_customer_id)
        DO UPDATE SET
            customer_type = EXCLUDED.customer_type,
            date_of_birth = EXCLUDED.date_of_birth,
            age_group = EXCLUDED.age_group,
            gender = EXCLUDED.gender,
            region = EXCLUDED.region,
            city = EXCLUDED.city,
            employment_type = EXCLUDED.employment_type,
            income_band = EXCLUDED.income_band,
            customer_status = EXCLUDED.customer_status,
            onboarding_date = EXCLUDED.onboarding_date,
            kyc_status = EXCLUDED.kyc_status,
            risk_rating = EXCLUDED.risk_rating,
            is_active = EXCLUDED.is_active,
            source_system = EXCLUDED.source_system,
            last_seen_batch_id = EXCLUDED.last_seen_batch_id,
            updated_at = NOW()
        RETURNING customer_id;
        """
    )

    with engine.begin() as connection:
        customer_id = connection.execute(
            query,
            {
                "source_customer_id": source_customer_id,
                "customer_type": customer_type,
                "date_of_birth": raw_customer["date_of_birth"],
                "age_group": age_group,
                "gender": gender,
                "region": region,
                "city": city,
                "employment_type": employment_type,
                "income_band": income_band,
                "customer_status": customer_status,
                "onboarding_date": raw_customer["onboarding_date"],
                "kyc_status": kyc_status,
                "risk_rating": risk_rating,
                "is_active": is_active,
                "source_system": raw_customer["source_system"],
                "first_seen_batch_id": raw_customer["ingestion_batch_id"],
                "last_seen_batch_id": raw_customer["ingestion_batch_id"],
            },
        ).scalar_one()

    return customer_id


def insert_clean_customer_profile(raw_customer: dict, customer_id: int) -> None:
    """
    Insert or update the customer's profile row.
    """

    first_name = standardize_text(raw_customer.get("first_name"))
    last_name = standardize_text(raw_customer.get("last_name"))
    id_number = standardize_text(raw_customer.get("id_number"))
    passport_number = standardize_text(raw_customer.get("passport_number"))
    country_of_birth = standardize_text(raw_customer.get("country_of_birth"))
    primary_phone_number = standardize_text(raw_customer.get("primary_phone_number"))
    secondary_phone_number = standardize_text(raw_customer.get("secondary_phone_number"))

    query = text(
        """
        INSERT INTO clean.customer_profiles (
            customer_id,
            first_name,
            last_name,
            full_name,
            identity_document_type,
            id_number,
            passport_number,
            country_of_birth,
            primary_phone_number,
            secondary_phone_number,
            source_system,
            first_seen_batch_id,
            last_seen_batch_id,
            created_at,
            updated_at
        )
        VALUES (
            :customer_id,
            :first_name,
            :last_name,
            :full_name,
            :identity_document_type,
            :id_number,
            :passport_number,
            :country_of_birth,
            :primary_phone_number,
            :secondary_phone_number,
            :source_system,
            :first_seen_batch_id,
            :last_seen_batch_id,
            NOW(),
            NOW()
        )
        ON CONFLICT (customer_id)
        DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            full_name = EXCLUDED.full_name,
            identity_document_type = EXCLUDED.identity_document_type,
            id_number = EXCLUDED.id_number,
            passport_number = EXCLUDED.passport_number,
            country_of_birth = EXCLUDED.country_of_birth,
            primary_phone_number = EXCLUDED.primary_phone_number,
            secondary_phone_number = EXCLUDED.secondary_phone_number,
            source_system = EXCLUDED.source_system,
            last_seen_batch_id = EXCLUDED.last_seen_batch_id,
            updated_at = NOW();
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "customer_id": customer_id,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": build_full_name(first_name, last_name),
                "identity_document_type": determine_identity_document_type(raw_customer),
                "id_number": id_number,
                "passport_number": passport_number,
                "country_of_birth": country_of_birth,
                "primary_phone_number": primary_phone_number,
                "secondary_phone_number": secondary_phone_number,
                "source_system": raw_customer["source_system"],
                "first_seen_batch_id": raw_customer["ingestion_batch_id"],
                "last_seen_batch_id": raw_customer["ingestion_batch_id"],
            },
        )


def insert_rejected_record(raw_customer: dict, validation_issue) -> None:
    """
    Insert one validation issue into ops.rejected_records.

    ON CONFLICT DO NOTHING prevents duplicate rejection rows if the script is rerun.
    """

    query = text(
        """
        INSERT INTO ops.rejected_records (
            batch_id,
            source_schema,
            source_table,
            source_record_id,
            entity_name,
            rule_code,
            rule_description,
            rejection_reason,
            severity,
            record_payload,
            created_at
        )
        VALUES (
            :batch_id,
            :source_schema,
            :source_table,
            :source_record_id,
            :entity_name,
            :rule_code,
            :rule_description,
            :rejection_reason,
            :severity,
            CAST(:record_payload AS JSONB),
            NOW()
        )
        ON CONFLICT DO NOTHING;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "batch_id": raw_customer["ingestion_batch_id"],
                "source_schema": "raw",
                "source_table": "raw_customers",
                "source_record_id": str(raw_customer["raw_customer_id"]),
                "entity_name": "customers",
                "rule_code": validation_issue.rule_code,
                "rule_description": validation_issue.rule_description,
                "rejection_reason": validation_issue.rejection_reason,
                "severity": validation_issue.severity,
                "record_payload": json.dumps(
                    raw_customer["raw_payload"],
                    ensure_ascii=False,
                    default=str,
                ),
            },
        )


def update_raw_customer_status(
    raw_customer_id: int,
    validation_status: str,
) -> None:
    """
    Update validation_status for one raw customer.
    """

    query = text(
        """
        UPDATE raw.raw_customers
        SET
            validation_status = :validation_status,
            processed_at = NOW()
        WHERE raw_customer_id = :raw_customer_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "raw_customer_id": raw_customer_id,
                "validation_status": validation_status,
            },
        )


def update_batch_validation_summary() -> None:
    """
    Update ingestion batch records with validation rejection counts.

    If a batch has rejected raw customer records, mark it as completed_with_rejections.
    """

    query = text(
        """
        WITH batch_counts AS (
            SELECT
                ingestion_batch_id AS batch_id,
                COUNT(*) FILTER (WHERE validation_status = 'rejected') AS rejected_count
            FROM raw.raw_customers
            GROUP BY ingestion_batch_id
        )
        UPDATE ops.ingestion_batches b
        SET
            records_rejected = batch_counts.rejected_count,
            status = CASE
                WHEN batch_counts.rejected_count > 0 THEN 'completed_with_rejections'
                ELSE b.status
            END
        FROM batch_counts
        WHERE b.batch_id = batch_counts.batch_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(query)


def clean_customers() -> None:
    """
    Validate raw customers and load valid records into clean.customers.
    """

    raw_customers = fetch_pending_raw_customers()

    print(f"Pending raw customers found: {len(raw_customers)}")

    if not raw_customers:
        print("No pending customer records to process")
        return

    duplicate_source_customer_ids = find_duplicate_source_customer_ids(raw_customers)

    print(f"Duplicate source_customer_id values found: {len(duplicate_source_customer_ids)}")

    records_cleaned = 0
    records_rejected = 0
    validation_issues_written = 0

    for raw_customer in raw_customers:
        validation_issues = validate_raw_customer(
            raw_customer=raw_customer,
            duplicate_source_customer_ids=duplicate_source_customer_ids,
        )

        if validation_issues:
            for validation_issue in validation_issues:
                insert_rejected_record(raw_customer, validation_issue)
                validation_issues_written += 1

            update_raw_customer_status(
                raw_customer_id=raw_customer["raw_customer_id"],
                validation_status="rejected",
            )

            records_rejected += 1
            continue

        customer_id = insert_clean_customer(raw_customer)
        insert_clean_customer_profile(raw_customer, customer_id)

        update_raw_customer_status(
            raw_customer_id=raw_customer["raw_customer_id"],
            validation_status="processed",
        )

        records_cleaned += 1

    update_batch_validation_summary()

    print("Customer cleaning finished")
    print(f"Records cleaned/upserted: {records_cleaned}")
    print(f"Records rejected: {records_rejected}")
    print(f"Validation issues written: {validation_issues_written}")


if __name__ == "__main__":
    clean_customers()