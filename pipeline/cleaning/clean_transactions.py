import json

from sqlalchemy import text

from pipeline.common.database import engine
from pipeline.validation.transaction_validators import ValidationIssue, validate_raw_transaction


def standardize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    return value


def fetch_pending_raw_transactions() -> list[dict]:
    query = text(
        """
        SELECT
            raw_transaction_id,
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
        FROM raw.raw_transactions
        WHERE validation_status = 'pending'
        ORDER BY ingestion_batch_id, source_row_number, raw_transaction_id;
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query)
        rows = result.mappings().all()

    return [dict(row) for row in rows]


def find_duplicate_source_transaction_ids(raw_transactions: list[dict]) -> set[str]:
    counts: dict[str, int] = {}

    for raw_transaction in raw_transactions:
        source_transaction_id = standardize_text(raw_transaction.get("source_transaction_id"))

        if source_transaction_id is None:
            continue

        counts[source_transaction_id] = counts.get(source_transaction_id, 0) + 1

    return {
        source_transaction_id
        for source_transaction_id, count in counts.items()
        if count > 1
    }


def resolve_transaction_account(raw_transaction: dict) -> dict | None:
    source_account_id = standardize_text(raw_transaction.get("source_account_id"))
    account_number = standardize_text(raw_transaction.get("account_number"))

    candidate_lookups: list[tuple[str, dict]] = []

    if source_account_id is not None:
        candidate_lookups.append(
            (
                """
                SELECT
                    account_id,
                    customer_id,
                    source_account_id,
                    account_number
                FROM clean.accounts
                WHERE source_account_id = :source_account_id
                LIMIT 1;
                """,
                {"source_account_id": source_account_id},
            )
        )

    if account_number is not None:
        candidate_lookups.append(
            (
                """
                SELECT
                    account_id,
                    customer_id,
                    source_account_id,
                    account_number
                FROM clean.accounts
                WHERE account_number = :account_number
                LIMIT 1;
                """,
                {"account_number": account_number},
            )
        )

    if not candidate_lookups:
        return None

    with engine.connect() as connection:
        for query_text, parameters in candidate_lookups:
            result = connection.execute(text(query_text), parameters).mappings().first()

            if result is not None:
                return dict(result)

    return None


def build_clean_transaction_row(raw_transaction: dict, account_lookup: dict) -> dict:
    transaction_timestamp = raw_transaction["transaction_timestamp"]

    return {
        "account_id": account_lookup["account_id"],
        "customer_id": account_lookup["customer_id"],
        "source_transaction_id": standardize_text(raw_transaction.get("source_transaction_id")),
        "source_account_id": account_lookup["source_account_id"] or standardize_text(raw_transaction.get("source_account_id")),
        "account_number": account_lookup["account_number"] or standardize_text(raw_transaction.get("account_number")),
        "transaction_timestamp": transaction_timestamp,
        "transaction_date": transaction_timestamp.date(),
        "transaction_type": standardize_text(raw_transaction.get("transaction_type")),
        "transaction_channel": standardize_text(raw_transaction.get("transaction_channel")),
        "transaction_direction": standardize_text(raw_transaction.get("transaction_direction")),
        "transaction_amount": raw_transaction["transaction_amount"],
        "transaction_currency": standardize_text(raw_transaction.get("transaction_currency")),
        "counterparty_reference": standardize_text(raw_transaction.get("counterparty_reference")),
        "merchant_category": standardize_text(raw_transaction.get("merchant_category")),
        "transaction_status": standardize_text(raw_transaction.get("transaction_status")),
        "running_balance": raw_transaction.get("running_balance"),
        "country_code": standardize_text(raw_transaction.get("country_code")),
        "city": standardize_text(raw_transaction.get("city")),
        "device_id": standardize_text(raw_transaction.get("device_id")),
        "is_international": bool(raw_transaction["is_international"]),
        "source_system": standardize_text(raw_transaction.get("source_system")),
        "first_seen_batch_id": raw_transaction["ingestion_batch_id"],
        "last_seen_batch_id": raw_transaction["ingestion_batch_id"],
    }


def insert_clean_transaction(clean_transaction: dict) -> None:
    query = text(
        """
        INSERT INTO clean.transactions (
            account_id,
            customer_id,
            source_transaction_id,
            source_account_id,
            account_number,
            transaction_timestamp,
            transaction_date,
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
            source_system,
            first_seen_batch_id,
            last_seen_batch_id,
            created_at,
            updated_at
        )
        VALUES (
            :account_id,
            :customer_id,
            :source_transaction_id,
            :source_account_id,
            :account_number,
            :transaction_timestamp,
            :transaction_date,
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
            :source_system,
            :first_seen_batch_id,
            :last_seen_batch_id,
            NOW(),
            NOW()
        )
        ON CONFLICT (source_transaction_id)
        DO UPDATE SET
            account_id = EXCLUDED.account_id,
            customer_id = EXCLUDED.customer_id,
            source_account_id = EXCLUDED.source_account_id,
            account_number = EXCLUDED.account_number,
            transaction_timestamp = EXCLUDED.transaction_timestamp,
            transaction_date = EXCLUDED.transaction_date,
            transaction_type = EXCLUDED.transaction_type,
            transaction_channel = EXCLUDED.transaction_channel,
            transaction_direction = EXCLUDED.transaction_direction,
            transaction_amount = EXCLUDED.transaction_amount,
            transaction_currency = EXCLUDED.transaction_currency,
            counterparty_reference = EXCLUDED.counterparty_reference,
            merchant_category = EXCLUDED.merchant_category,
            transaction_status = EXCLUDED.transaction_status,
            running_balance = EXCLUDED.running_balance,
            country_code = EXCLUDED.country_code,
            city = EXCLUDED.city,
            device_id = EXCLUDED.device_id,
            is_international = EXCLUDED.is_international,
            source_system = EXCLUDED.source_system,
            last_seen_batch_id = EXCLUDED.last_seen_batch_id,
            updated_at = NOW()
        RETURNING transaction_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(query, clean_transaction)


def insert_rejected_record(raw_transaction: dict, validation_issue: ValidationIssue) -> None:
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
                "batch_id": raw_transaction["ingestion_batch_id"],
                "source_schema": "raw",
                "source_table": "raw_transactions",
                "source_record_id": str(raw_transaction["raw_transaction_id"]),
                "entity_name": "transactions",
                "rule_code": validation_issue.rule_code,
                "rule_description": validation_issue.rule_description,
                "rejection_reason": validation_issue.rejection_reason,
                "severity": validation_issue.severity,
                "record_payload": json.dumps(raw_transaction["raw_payload"], ensure_ascii=False, default=str),
            },
        )


def update_raw_transaction_status(raw_transaction_id: int, validation_status: str) -> None:
    query = text(
        """
        UPDATE raw.raw_transactions
        SET
            validation_status = :validation_status,
            processed_at = NOW()
        WHERE raw_transaction_id = :raw_transaction_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "raw_transaction_id": raw_transaction_id,
                "validation_status": validation_status,
            },
        )


def update_batch_validation_summary() -> None:
    query = text(
        """
        WITH batch_counts AS (
            SELECT
                ingestion_batch_id AS batch_id,
                COUNT(*) FILTER (WHERE validation_status = 'rejected') AS rejected_count
            FROM raw.raw_transactions
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


def clean_transactions() -> None:
    raw_transactions = fetch_pending_raw_transactions()

    print(f"Pending raw transactions found: {len(raw_transactions)}")

    if not raw_transactions:
        print("No pending transaction records to process")
        return

    duplicate_source_transaction_ids = find_duplicate_source_transaction_ids(raw_transactions)

    print(f"Duplicate source_transaction_id values found: {len(duplicate_source_transaction_ids)}")

    records_cleaned = 0
    records_rejected = 0
    validation_issues_written = 0

    for raw_transaction in raw_transactions:
        validation_issues = validate_raw_transaction(
            raw_transaction=raw_transaction,
            duplicate_source_transaction_ids=duplicate_source_transaction_ids,
        )

        if validation_issues:
            for validation_issue in validation_issues:
                insert_rejected_record(raw_transaction, validation_issue)
                validation_issues_written += 1

            update_raw_transaction_status(
                raw_transaction_id=raw_transaction["raw_transaction_id"],
                validation_status="rejected",
            )
            records_rejected += 1
            continue

        account_lookup = resolve_transaction_account(raw_transaction)

        if account_lookup is None:
            insert_rejected_record(
                raw_transaction,
                ValidationIssue(
                    rule_code="TRANSACTION_ACCOUNT_LINK_NOT_FOUND",
                    rule_description="Transaction could not be linked to a clean account.",
                    rejection_reason="Transaction could not be linked to a clean account.",
                ),
            )
            update_raw_transaction_status(
                raw_transaction_id=raw_transaction["raw_transaction_id"],
                validation_status="rejected",
            )
            records_rejected += 1
            validation_issues_written += 1
            continue

        clean_transaction = build_clean_transaction_row(raw_transaction, account_lookup)
        insert_clean_transaction(clean_transaction)
        update_raw_transaction_status(
            raw_transaction_id=raw_transaction["raw_transaction_id"],
            validation_status="processed",
        )
        records_cleaned += 1

    update_batch_validation_summary()

    print("Transaction cleaning finished")
    print(f"Records cleaned/upserted: {records_cleaned}")
    print(f"Records rejected: {records_rejected}")
    print(f"Validation issues written: {validation_issues_written}")


if __name__ == "__main__":
    clean_transactions()
