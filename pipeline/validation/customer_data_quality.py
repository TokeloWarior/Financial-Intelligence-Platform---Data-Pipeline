import json
from typing import Any

from sqlalchemy import text

from pipeline.common.database import engine


ENTITY_NAME = "customers"


def fetch_latest_customer_batch_id() -> int | None:
    """
    Fetch the latest ingestion batch id for customer data.
    """

    query = text(
        """
        SELECT batch_id
        FROM ops.ingestion_batches
        WHERE source_entity = 'customers'
        ORDER BY batch_id DESC
        LIMIT 1;
        """
    )

    with engine.connect() as connection:
        return connection.execute(query).scalar_one_or_none()


def fetch_one(query_text: str, parameters: dict | None = None) -> dict:
    """
    Execute a query that returns one row.
    """

    query = text(query_text)

    with engine.connect() as connection:
        result = connection.execute(query, parameters or {})
        row = result.mappings().one()

    return dict(row)


def fetch_scalar(query_text: str, parameters: dict | None = None) -> Any:
    """
    Execute a query that returns one scalar value.
    """

    query = text(query_text)

    with engine.connect() as connection:
        return connection.execute(query, parameters or {}).scalar_one()


def clear_existing_dq_results(batch_id: int) -> None:
    """
    Delete previous customer DQ results for the same batch.

    This makes the DQ script idempotent for repeated runs.
    """

    query = text(
        """
        DELETE FROM ops.data_quality_results
        WHERE batch_id = :batch_id
          AND entity_name = :entity_name;
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "batch_id": batch_id,
                "entity_name": ENTITY_NAME,
            },
        )


def insert_dq_result(
    batch_id: int,
    check_name: str,
    check_status: str,
    records_checked: int,
    records_failed: int,
    check_details: dict,
) -> None:
    """
    Insert one data quality result.
    """

    query = text(
        """
        INSERT INTO ops.data_quality_results (
            batch_id,
            entity_name,
            check_name,
            check_status,
            records_checked,
            records_failed,
            check_details,
            created_at
        )
        VALUES (
            :batch_id,
            :entity_name,
            :check_name,
            :check_status,
            :records_checked,
            :records_failed,
            CAST(:check_details AS JSONB),
            NOW()
        );
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "batch_id": batch_id,
                "entity_name": ENTITY_NAME,
                "check_name": check_name,
                "check_status": check_status,
                "records_checked": records_checked,
                "records_failed": records_failed,
                "check_details": json.dumps(
                    check_details,
                    ensure_ascii=False,
                    default=str,
                ),
            },
        )


def status_from_failed_count(records_failed: int) -> str:
    """
    Convert failed count to DQ status.
    """

    if records_failed > 0:
        return "failed"

    return "passed"


def check_no_pending_raw_customers(batch_id: int) -> dict:
    """
    Check that no raw customer records remain pending.
    """

    counts = fetch_one(
        """
        SELECT
            COUNT(*) AS total_records,
            COUNT(*) FILTER (WHERE validation_status = 'pending') AS pending_records,
            COUNT(*) FILTER (WHERE validation_status = 'processed') AS processed_records,
            COUNT(*) FILTER (WHERE validation_status = 'rejected') AS rejected_records
        FROM raw.raw_customers
        WHERE ingestion_batch_id = :batch_id;
        """,
        {"batch_id": batch_id},
    )

    records_checked = counts["total_records"]
    records_failed = counts["pending_records"]

    return {
        "check_name": "customer_raw_no_pending_records",
        "records_checked": records_checked,
        "records_failed": records_failed,
        "check_details": counts,
    }


def check_batch_counts_match_raw_processing(batch_id: int) -> dict:
    """
    Check that ingestion batch counts match raw customer processing counts.
    """

    result = fetch_one(
        """
        SELECT
            b.records_expected,
            b.records_inserted,
            b.records_rejected,
            b.status,
            COUNT(r.raw_customer_id) AS raw_records,
            COUNT(r.raw_customer_id) FILTER (WHERE r.validation_status = 'processed') AS processed_records,
            COUNT(r.raw_customer_id) FILTER (WHERE r.validation_status = 'rejected') AS rejected_records,
            COUNT(r.raw_customer_id) FILTER (WHERE r.validation_status = 'pending') AS pending_records
        FROM ops.ingestion_batches b
        LEFT JOIN raw.raw_customers r
            ON b.batch_id = r.ingestion_batch_id
        WHERE b.batch_id = :batch_id
        GROUP BY
            b.records_expected,
            b.records_inserted,
            b.records_rejected,
            b.status;
        """,
        {"batch_id": batch_id},
    )

    failed_checks = []

    if result["records_expected"] != result["raw_records"]:
        failed_checks.append("records_expected does not match raw_records")

    if result["records_inserted"] != result["raw_records"]:
        failed_checks.append("records_inserted does not match raw_records")

    if result["records_rejected"] != result["rejected_records"]:
        failed_checks.append("records_rejected does not match rejected raw records")

    expected_status = (
        "completed_with_rejections"
        if result["rejected_records"] > 0
        else "completed"
    )

    if result["status"] != expected_status:
        failed_checks.append(
            f"batch status should be {expected_status}, found {result['status']}"
        )

    return {
        "check_name": "customer_batch_counts_match_raw_processing",
        "records_checked": result["raw_records"],
        "records_failed": len(failed_checks),
        "check_details": {
            **result,
            "failed_checks": failed_checks,
        },
    }


def check_rejected_records_have_issues(batch_id: int) -> dict:
    """
    Check that rejected raw customers have rejection issue records.
    """

    result = fetch_one(
        """
        SELECT
            COUNT(DISTINCT r.raw_customer_id) AS rejected_raw_records,
            COUNT(DISTINCT rr.source_record_id) AS rejected_records_with_issues,
            COUNT(rr.rejected_record_id) AS validation_issues
        FROM raw.raw_customers r
        LEFT JOIN ops.rejected_records rr
            ON rr.batch_id = r.ingestion_batch_id
           AND rr.source_record_id = r.raw_customer_id::TEXT
           AND rr.entity_name = 'customers'
        WHERE r.ingestion_batch_id = :batch_id
          AND r.validation_status = 'rejected';
        """,
        {"batch_id": batch_id},
    )

    missing_issue_count = (
        result["rejected_raw_records"] - result["rejected_records_with_issues"]
    )

    return {
        "check_name": "customer_rejected_records_have_issues",
        "records_checked": result["rejected_raw_records"],
        "records_failed": missing_issue_count,
        "check_details": result,
    }


def check_clean_required_fields() -> dict:
    """
    Check that required fields in clean.customers are populated.
    """

    total_records = fetch_scalar(
        """
        SELECT COUNT(*)
        FROM clean.customers;
        """
    )

    failed_records = fetch_scalar(
        """
        SELECT COUNT(*)
        FROM clean.customers
        WHERE source_customer_id IS NULL
           OR customer_type IS NULL
           OR date_of_birth IS NULL
           OR age_group IS NULL
           OR region IS NULL
           OR customer_status IS NULL
           OR source_system IS NULL;
        """
    )

    return {
        "check_name": "customer_clean_required_fields_populated",
        "records_checked": total_records,
        "records_failed": failed_records,
        "check_details": {
            "total_clean_customers": total_records,
            "records_missing_required_fields": failed_records,
        },
    }


def check_clean_duplicate_source_customer_ids() -> dict:
    """
    Check that clean.customers has no duplicate source_customer_id values.
    """

    duplicate_count = fetch_scalar(
        """
        SELECT COALESCE(SUM(duplicate_records), 0)::INTEGER
        FROM (
            SELECT COUNT(*) - 1 AS duplicate_records
            FROM clean.customers
            GROUP BY source_customer_id
            HAVING COUNT(*) > 1
        ) duplicates;
        """
    )

    total_records = fetch_scalar(
        """
        SELECT COUNT(*)
        FROM clean.customers;
        """
    )

    return {
        "check_name": "customer_clean_no_duplicate_source_customer_ids",
        "records_checked": total_records,
        "records_failed": duplicate_count,
        "check_details": {
            "duplicate_source_customer_id_records": duplicate_count,
        },
    }


def check_clean_is_active_consistency() -> dict:
    """
    Check that is_active matches customer_status.
    """

    total_records = fetch_scalar(
        """
        SELECT COUNT(*)
        FROM clean.customers;
        """
    )

    failed_records = fetch_scalar(
        """
        SELECT COUNT(*)
        FROM clean.customers
        WHERE (
                customer_status = 'active'
                AND is_active IS NOT TRUE
              )
           OR (
                customer_status <> 'active'
                AND is_active IS NOT FALSE
              );
        """
    )

    return {
        "check_name": "customer_clean_is_active_consistency",
        "records_checked": total_records,
        "records_failed": failed_records,
        "check_details": {
            "inconsistent_is_active_records": failed_records,
        },
    }


def check_processed_raw_records_loaded_to_clean(batch_id: int) -> dict:
    """
    Check that processed raw records from the batch exist in clean.customers.
    """

    result = fetch_one(
        """
        SELECT
            COUNT(r.raw_customer_id) AS processed_raw_records,
            COUNT(c.customer_id) AS matched_clean_customers
        FROM raw.raw_customers r
        LEFT JOIN clean.customers c
            ON c.source_customer_id = TRIM(r.source_customer_id)
        WHERE r.ingestion_batch_id = :batch_id
          AND r.validation_status = 'processed';
        """,
        {"batch_id": batch_id},
    )

    missing_clean_records = (
        result["processed_raw_records"] - result["matched_clean_customers"]
    )

    return {
        "check_name": "customer_processed_raw_records_loaded_to_clean",
        "records_checked": result["processed_raw_records"],
        "records_failed": missing_clean_records,
        "check_details": result,
    }


def check_validation_issue_volume(batch_id: int) -> dict:
    """
    Check that validation issue count is at least the rejected raw record count.
    """

    result = fetch_one(
        """
        SELECT
            COUNT(DISTINCT r.raw_customer_id) AS rejected_raw_records,
            COUNT(rr.rejected_record_id) AS validation_issues
        FROM raw.raw_customers r
        LEFT JOIN ops.rejected_records rr
            ON rr.batch_id = r.ingestion_batch_id
           AND rr.source_record_id = r.raw_customer_id::TEXT
           AND rr.entity_name = 'customers'
        WHERE r.ingestion_batch_id = :batch_id
          AND r.validation_status = 'rejected';
        """,
        {"batch_id": batch_id},
    )

    records_failed = 0

    if result["validation_issues"] < result["rejected_raw_records"]:
        records_failed = result["rejected_raw_records"] - result["validation_issues"]

    return {
        "check_name": "customer_validation_issue_volume",
        "records_checked": result["rejected_raw_records"],
        "records_failed": records_failed,
        "check_details": result,
    }


def run_customer_data_quality_checks() -> None:
    """
    Run customer data quality checks and write results to ops.data_quality_results.
    """

    batch_id = fetch_latest_customer_batch_id()

    if batch_id is None:
        print("No customer ingestion batch found. Nothing to check.")
        return

    print(f"Latest customer batch id: {batch_id}")

    clear_existing_dq_results(batch_id)

    checks = [
        check_no_pending_raw_customers(batch_id),
        check_batch_counts_match_raw_processing(batch_id),
        check_rejected_records_have_issues(batch_id),
        check_clean_required_fields(),
        check_clean_duplicate_source_customer_ids(),
        check_clean_is_active_consistency(),
        check_processed_raw_records_loaded_to_clean(batch_id),
        check_validation_issue_volume(batch_id),
    ]

    passed_checks = 0
    failed_checks = 0

    for check in checks:
        check_status = status_from_failed_count(check["records_failed"])

        insert_dq_result(
            batch_id=batch_id,
            check_name=check["check_name"],
            check_status=check_status,
            records_checked=check["records_checked"],
            records_failed=check["records_failed"],
            check_details=check["check_details"],
        )

        if check_status == "passed":
            passed_checks += 1
        else:
            failed_checks += 1

    print("Customer data quality checks finished")
    print(f"Checks run: {len(checks)}")
    print(f"Checks passed: {passed_checks}")
    print(f"Checks failed: {failed_checks}")


if __name__ == "__main__":
    run_customer_data_quality_checks()