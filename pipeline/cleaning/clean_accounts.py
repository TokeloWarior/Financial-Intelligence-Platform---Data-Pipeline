import json
from datetime import date

from sqlalchemy import text

from pipeline.common.database import engine


def standardize_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    return value


def fetch_pending_raw_accounts() -> list[dict]:
    query = text(
        """
        SELECT
            raw_account_id,
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
        FROM raw.raw_accounts
        WHERE validation_status = 'pending'
        ORDER BY ingestion_batch_id, source_row_number, raw_account_id;
        """
    )

    with engine.connect() as connection:
        result = connection.execute(query)
        rows = result.mappings().all()

    return [dict(row) for row in rows]


def find_duplicate_customer_link_keys(raw_accounts: list[dict]) -> set[str]:
    counts: dict[str, int] = {}

    for raw_account in raw_accounts:
        customer_link_key = standardize_text(raw_account.get("customer_link_key"))

        if customer_link_key is None:
            continue

        counts[customer_link_key] = counts.get(customer_link_key, 0) + 1

    return {
        customer_link_key
        for customer_link_key, count in counts.items()
        if count > 1
    }


def resolve_account_customer(raw_account: dict) -> dict | None:
    customer_link_type = standardize_text(raw_account.get("customer_link_type"))

    if customer_link_type is None:
        return None

    if customer_link_type == "source_customer_id":
        query = text(
            """
            SELECT
                c.customer_id,
                c.source_customer_id,
                p.customer_profile_id
            FROM clean.customers c
            JOIN clean.customer_profiles p
                ON p.customer_id = c.customer_id
            WHERE c.source_customer_id = :source_customer_id
            LIMIT 1;
            """
        )
        parameters = {"source_customer_id": standardize_text(raw_account.get("source_customer_id"))}
    elif customer_link_type == "id_number":
        query = text(
            """
            SELECT
                c.customer_id,
                c.source_customer_id,
                p.customer_profile_id
            FROM clean.customer_profiles p
            JOIN clean.customers c
                ON c.customer_id = p.customer_id
            WHERE p.id_number = :id_number
            LIMIT 1;
            """
        )
        parameters = {"id_number": standardize_text(raw_account.get("id_number"))}
    elif customer_link_type == "passport_number":
        query = text(
            """
            SELECT
                c.customer_id,
                c.source_customer_id,
                p.customer_profile_id
            FROM clean.customer_profiles p
            JOIN clean.customers c
                ON c.customer_id = p.customer_id
            WHERE p.passport_number = :passport_number
            LIMIT 1;
            """
        )
        parameters = {"passport_number": standardize_text(raw_account.get("passport_number"))}
    else:
        return None

    with engine.connect() as connection:
        result = connection.execute(query, parameters).mappings().first()

    if result is None:
        return None

    return dict(result)


def build_clean_account_row(raw_account: dict, customer_lookup: dict) -> dict:
    source_customer_id = standardize_text(customer_lookup.get("source_customer_id")) or standardize_text(
        raw_account.get("source_customer_id")
    )

    return {
        "customer_id": customer_lookup["customer_id"],
        "customer_profile_id": customer_lookup["customer_profile_id"],
        "source_account_id": standardize_text(raw_account.get("source_account_id")),
        "source_customer_id": source_customer_id,
        "customer_link_type": standardize_text(raw_account.get("customer_link_type")),
        "customer_link_key": standardize_text(raw_account.get("customer_link_key")),
        "bank_name": standardize_text(raw_account.get("bank_name")),
        "bank_code": standardize_text(raw_account.get("bank_code")),
        "branch_name": standardize_text(raw_account.get("branch_name")),
        "account_number": standardize_text(raw_account.get("account_number")),
        "account_type": standardize_text(raw_account.get("account_type")),
        "account_currency": standardize_text(raw_account.get("account_currency")),
        "account_status": standardize_text(raw_account.get("account_status")),
        "account_age_months": raw_account["account_age_months"],
        "opened_date": raw_account["opened_date"],
        "account_balance": raw_account["account_balance"],
        "monthly_deposits": raw_account["monthly_deposits"],
        "monthly_withdrawals": raw_account["monthly_withdrawals"],
        "overdraft_limit": raw_account["overdraft_limit"],
        "mobile_banking_enabled": raw_account["mobile_banking_enabled"],
        "source_system": standardize_text(raw_account.get("source_system")),
        "first_seen_batch_id": raw_account["ingestion_batch_id"],
        "last_seen_batch_id": raw_account["ingestion_batch_id"],
    }


def insert_clean_account(clean_account: dict) -> None:
    query = text(
        """
        INSERT INTO clean.accounts (
            customer_id,
            customer_profile_id,
            source_account_id,
            source_customer_id,
            customer_link_type,
            customer_link_key,
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
            source_system,
            first_seen_batch_id,
            last_seen_batch_id,
            created_at,
            updated_at
        )
        VALUES (
            :customer_id,
            :customer_profile_id,
            :source_account_id,
            :source_customer_id,
            :customer_link_type,
            :customer_link_key,
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
            :source_system,
            :first_seen_batch_id,
            :last_seen_batch_id,
            NOW(),
            NOW()
        )
        ON CONFLICT (source_account_id)
        DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            customer_profile_id = EXCLUDED.customer_profile_id,
            source_customer_id = EXCLUDED.source_customer_id,
            customer_link_type = EXCLUDED.customer_link_type,
            customer_link_key = EXCLUDED.customer_link_key,
            bank_name = EXCLUDED.bank_name,
            bank_code = EXCLUDED.bank_code,
            branch_name = EXCLUDED.branch_name,
            account_number = EXCLUDED.account_number,
            account_type = EXCLUDED.account_type,
            account_currency = EXCLUDED.account_currency,
            account_status = EXCLUDED.account_status,
            account_age_months = EXCLUDED.account_age_months,
            opened_date = EXCLUDED.opened_date,
            account_balance = EXCLUDED.account_balance,
            monthly_deposits = EXCLUDED.monthly_deposits,
            monthly_withdrawals = EXCLUDED.monthly_withdrawals,
            overdraft_limit = EXCLUDED.overdraft_limit,
            mobile_banking_enabled = EXCLUDED.mobile_banking_enabled,
            source_system = EXCLUDED.source_system,
            last_seen_batch_id = EXCLUDED.last_seen_batch_id,
            updated_at = NOW()
        RETURNING account_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(query, clean_account)


def insert_rejected_record(raw_account: dict, rejection_reason: str, rule_code: str) -> None:
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
                "batch_id": raw_account["ingestion_batch_id"],
                "source_schema": "raw",
                "source_table": "raw_accounts",
                "source_record_id": str(raw_account["raw_account_id"]),
                "entity_name": "accounts",
                "rule_code": rule_code,
                "rule_description": rejection_reason,
                "rejection_reason": rejection_reason,
                "severity": "error",
                "record_payload": json.dumps(raw_account["raw_payload"], ensure_ascii=False, default=str),
            },
        )


def update_raw_account_status(raw_account_id: int, validation_status: str) -> None:
    query = text(
        """
        UPDATE raw.raw_accounts
        SET
            validation_status = :validation_status,
            processed_at = NOW()
        WHERE raw_account_id = :raw_account_id;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "raw_account_id": raw_account_id,
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
            FROM raw.raw_accounts
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


def clean_accounts() -> None:
    raw_accounts = fetch_pending_raw_accounts()

    print(f"Pending raw accounts found: {len(raw_accounts)}")

    if not raw_accounts:
        print("No pending account records to process")
        return

    duplicate_customer_link_keys = find_duplicate_customer_link_keys(raw_accounts)
    print(f"Duplicate customer_link_key values found: {len(duplicate_customer_link_keys)}")

    records_cleaned = 0
    records_rejected = 0
    validation_issues_written = 0

    for raw_account in raw_accounts:
        customer_link_key = standardize_text(raw_account.get("customer_link_key"))

        if customer_link_key is None:
            insert_rejected_record(
                raw_account,
                "customer_link_key is required.",
                "ACCOUNT_LINK_KEY_MISSING",
            )
            update_raw_account_status(raw_account["raw_account_id"], "rejected")
            records_rejected += 1
            validation_issues_written += 1
            continue

        if customer_link_key in duplicate_customer_link_keys:
            insert_rejected_record(
                raw_account,
                "customer_link_key must be unique within the incoming batch.",
                "ACCOUNT_LINK_KEY_DUPLICATE_IN_BATCH",
            )
            update_raw_account_status(raw_account["raw_account_id"], "rejected")
            records_rejected += 1
            validation_issues_written += 1
            continue

        customer_lookup = resolve_account_customer(raw_account)

        if customer_lookup is None:
            insert_rejected_record(
                raw_account,
                "Account could not be linked to a clean customer/profile record.",
                "ACCOUNT_CUSTOMER_LINK_NOT_FOUND",
            )
            update_raw_account_status(raw_account["raw_account_id"], "rejected")
            records_rejected += 1
            validation_issues_written += 1
            continue

        clean_account = build_clean_account_row(raw_account, customer_lookup)
        insert_clean_account(clean_account)

        update_raw_account_status(raw_account["raw_account_id"], "processed")
        records_cleaned += 1

    update_batch_validation_summary()

    print("Account cleaning finished")
    print(f"Records cleaned/upserted: {records_cleaned}")
    print(f"Records rejected: {records_rejected}")
    print(f"Validation issues written: {validation_issues_written}")


if __name__ == "__main__":
    clean_accounts()
