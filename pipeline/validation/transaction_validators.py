from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


SOURCE_TRANSACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,127}$")
SOURCE_ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,127}$")
ACCOUNT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{6,32}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2,3}$")
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{3,63}$")

VALID_TRANSACTION_TYPES = {
    "deposit",
    "withdrawal",
    "purchase",
    "transfer_in",
    "transfer_out",
    "bill_payment",
    "cash_withdrawal",
    "salary",
    "fee",
    "interest",
    "refund",
}
VALID_TRANSACTION_CHANNELS = {
    "branch",
    "atm",
    "mobile_app",
    "online_banking",
    "card_pos",
    "eft",
    "merchant_settlement",
}
VALID_TRANSACTION_DIRECTIONS = {
    "credit",
    "debit",
}
VALID_TRANSACTION_STATUSES = {
    "posted",
    "pending",
    "reversed",
}
TRANSACTION_TYPES_BY_DIRECTION = {
    "credit": {"deposit", "transfer_in", "salary", "interest", "refund"},
    "debit": {"withdrawal", "purchase", "transfer_out", "bill_payment", "cash_withdrawal", "fee"},
}


@dataclass(frozen=True)
class ValidationIssue:
    rule_code: str
    rule_description: str
    rejection_reason: str
    severity: str = "error"

    def to_dict(self) -> dict:
        return asdict(self)


def is_blank(value: Any) -> bool:
    if value is None:
        return True

    return str(value).strip() == ""


def value_as_string(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)


def parse_raw_timestamp_value(value: Any):
    if is_blank(value):
        return None

    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def parse_raw_decimal_value(value: Any) -> Decimal | None:
    if is_blank(value):
        return None

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def has_invalid_raw_timestamp_format(raw_payload: dict, field_name: str) -> bool:
    raw_value = raw_payload.get(field_name)

    if is_blank(raw_value):
        return False

    return parse_raw_timestamp_value(raw_value) is None


def has_invalid_raw_decimal_format(raw_payload: dict, field_name: str) -> bool:
    raw_value = raw_payload.get(field_name)

    if is_blank(raw_value):
        return False

    return parse_raw_decimal_value(raw_value) is None


def is_name_like_value(value: str | None) -> bool:
    if is_blank(value):
        return False

    trimmed_value = str(value).strip()

    if not trimmed_value[0].isalpha() or not trimmed_value[-1].isalpha():
        return False

    allowed_characters = {" ", "'", "-", "."}

    return all(char.isalpha() or char in allowed_characters for char in trimmed_value)


def add_issue(
    issues: list[ValidationIssue],
    rule_code: str,
    rule_description: str,
    rejection_reason: str,
    severity: str = "error",
) -> None:
    issues.append(
        ValidationIssue(
            rule_code=rule_code,
            rule_description=rule_description,
            rejection_reason=rejection_reason,
            severity=severity,
        )
    )


def validate_source_transaction_id(
    raw_transaction: dict,
    duplicate_source_transaction_ids: set[str] | None,
    issues: list[ValidationIssue],
) -> None:
    source_transaction_id = value_as_string(raw_transaction.get("source_transaction_id"))

    if is_blank(source_transaction_id):
        add_issue(
            issues,
            "TRANSACTION_ID_MISSING",
            "source_transaction_id is required.",
            "Missing source_transaction_id.",
        )
        return

    trimmed_transaction_id = str(source_transaction_id).strip()

    if source_transaction_id != trimmed_transaction_id:
        add_issue(
            issues,
            "TRANSACTION_ID_HAS_WHITESPACE",
            "source_transaction_id must not contain leading or trailing whitespace.",
            f"source_transaction_id has leading or trailing whitespace: {source_transaction_id!r}.",
        )

    if SOURCE_TRANSACTION_ID_PATTERN.fullmatch(trimmed_transaction_id) is None:
        add_issue(
            issues,
            "TRANSACTION_ID_INVALID_FORMAT",
            "source_transaction_id must be a non-empty source identifier with no spaces.",
            f"Invalid source_transaction_id format: {source_transaction_id!r}.",
        )

    if duplicate_source_transaction_ids and trimmed_transaction_id in duplicate_source_transaction_ids:
        add_issue(
            issues,
            "TRANSACTION_ID_DUPLICATE_IN_BATCH",
            "source_transaction_id must be unique within the incoming batch.",
            f"Duplicate source_transaction_id found in batch: {trimmed_transaction_id}.",
        )


def validate_account_link_fields(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    source_account_id = value_as_string(raw_transaction.get("source_account_id"))
    account_number = value_as_string(raw_transaction.get("account_number"))

    if is_blank(source_account_id) and is_blank(account_number):
        add_issue(
            issues,
            "TRANSACTION_ACCOUNT_LINK_MISSING",
            "Either source_account_id or account_number is required.",
            "Missing both source_account_id and account_number.",
        )
        return

    if not is_blank(source_account_id):
        trimmed_source_account_id = str(source_account_id).strip()
        if SOURCE_ACCOUNT_ID_PATTERN.fullmatch(trimmed_source_account_id) is None:
            add_issue(
                issues,
                "TRANSACTION_SOURCE_ACCOUNT_ID_INVALID",
                "source_account_id must be a readable source identifier when provided.",
                f"Invalid source_account_id: {source_account_id!r}.",
            )

    if not is_blank(account_number):
        trimmed_account_number = str(account_number).strip()
        if ACCOUNT_NUMBER_PATTERN.fullmatch(trimmed_account_number) is None:
            add_issue(
                issues,
                "TRANSACTION_ACCOUNT_NUMBER_INVALID",
                "account_number must be an alphanumeric account identifier when provided.",
                f"Invalid account_number: {account_number!r}.",
            )


def validate_transaction_timestamp(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    raw_payload = raw_transaction.get("raw_payload") or {}
    transaction_timestamp = raw_transaction.get("transaction_timestamp")

    if has_invalid_raw_timestamp_format(raw_payload, "transaction_timestamp"):
        add_issue(
            issues,
            "TRANSACTION_TIMESTAMP_INVALID_FORMAT",
            "transaction_timestamp must be a valid ISO timestamp.",
            f"Invalid transaction_timestamp format: {raw_payload.get('transaction_timestamp')!r}.",
        )
        return

    if transaction_timestamp is None:
        add_issue(
            issues,
            "TRANSACTION_TIMESTAMP_MISSING",
            "transaction_timestamp is required.",
            "Missing transaction_timestamp.",
        )
        return

    if transaction_timestamp > datetime.now(transaction_timestamp.tzinfo):
        add_issue(
            issues,
            "TRANSACTION_TIMESTAMP_IN_FUTURE",
            "transaction_timestamp cannot be in the future.",
            f"transaction_timestamp is in the future: {transaction_timestamp}.",
        )


def validate_transaction_type(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_type = value_as_string(raw_transaction.get("transaction_type"))

    if is_blank(transaction_type):
        add_issue(
            issues,
            "TRANSACTION_TYPE_MISSING",
            "transaction_type is required.",
            "Missing transaction_type.",
        )
        return

    if str(transaction_type).strip() not in VALID_TRANSACTION_TYPES:
        add_issue(
            issues,
            "TRANSACTION_TYPE_INVALID",
            "transaction_type must be one of the allowed values.",
            f"Invalid transaction_type: {transaction_type!r}.",
        )


def validate_transaction_channel(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_channel = value_as_string(raw_transaction.get("transaction_channel"))

    if is_blank(transaction_channel):
        add_issue(
            issues,
            "TRANSACTION_CHANNEL_MISSING",
            "transaction_channel is required.",
            "Missing transaction_channel.",
        )
        return

    if str(transaction_channel).strip() not in VALID_TRANSACTION_CHANNELS:
        add_issue(
            issues,
            "TRANSACTION_CHANNEL_INVALID",
            "transaction_channel must be one of the allowed values.",
            f"Invalid transaction_channel: {transaction_channel!r}.",
        )


def validate_transaction_direction(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_direction = value_as_string(raw_transaction.get("transaction_direction"))

    if is_blank(transaction_direction):
        add_issue(
            issues,
            "TRANSACTION_DIRECTION_MISSING",
            "transaction_direction is required.",
            "Missing transaction_direction.",
        )
        return

    if str(transaction_direction).strip() not in VALID_TRANSACTION_DIRECTIONS:
        add_issue(
            issues,
            "TRANSACTION_DIRECTION_INVALID",
            "transaction_direction must be either credit or debit.",
            f"Invalid transaction_direction: {transaction_direction!r}.",
        )


def validate_transaction_amount(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    raw_payload = raw_transaction.get("raw_payload") or {}
    transaction_amount = raw_transaction.get("transaction_amount")

    if has_invalid_raw_decimal_format(raw_payload, "transaction_amount"):
        add_issue(
            issues,
            "TRANSACTION_AMOUNT_INVALID_FORMAT",
            "transaction_amount must be a valid numeric amount.",
            f"Invalid transaction_amount format: {raw_payload.get('transaction_amount')!r}.",
        )
        return

    if transaction_amount is None:
        add_issue(
            issues,
            "TRANSACTION_AMOUNT_MISSING",
            "transaction_amount is required.",
            "Missing transaction_amount.",
        )
        return

    if transaction_amount <= 0:
        add_issue(
            issues,
            "TRANSACTION_AMOUNT_NON_POSITIVE",
            "transaction_amount must be greater than zero.",
            f"Invalid transaction_amount: {transaction_amount}.",
        )


def validate_transaction_currency(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_currency = value_as_string(raw_transaction.get("transaction_currency"))

    if is_blank(transaction_currency):
        add_issue(
            issues,
            "TRANSACTION_CURRENCY_MISSING",
            "transaction_currency is required.",
            "Missing transaction_currency.",
        )
        return

    if CURRENCY_PATTERN.fullmatch(str(transaction_currency).strip()) is None:
        add_issue(
            issues,
            "TRANSACTION_CURRENCY_INVALID",
            "transaction_currency must be a three-letter uppercase code.",
            f"Invalid transaction_currency: {transaction_currency!r}.",
        )


def validate_counterparty_reference(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    counterparty_reference = value_as_string(raw_transaction.get("counterparty_reference"))

    if is_blank(counterparty_reference):
        add_issue(
            issues,
            "TRANSACTION_COUNTERPARTY_REFERENCE_MISSING",
            "counterparty_reference is required.",
            "Missing counterparty_reference.",
        )


def validate_merchant_category(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    merchant_category = value_as_string(raw_transaction.get("merchant_category"))

    if is_blank(merchant_category):
        add_issue(
            issues,
            "TRANSACTION_MERCHANT_CATEGORY_MISSING",
            "merchant_category is required.",
            "Missing merchant_category.",
        )


def validate_transaction_status(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_status = value_as_string(raw_transaction.get("transaction_status"))

    if is_blank(transaction_status):
        add_issue(
            issues,
            "TRANSACTION_STATUS_MISSING",
            "transaction_status is required.",
            "Missing transaction_status.",
        )
        return

    if str(transaction_status).strip() not in VALID_TRANSACTION_STATUSES:
        add_issue(
            issues,
            "TRANSACTION_STATUS_INVALID",
            "transaction_status must be one of the allowed values.",
            f"Invalid transaction_status: {transaction_status!r}.",
        )


def validate_running_balance(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    raw_payload = raw_transaction.get("raw_payload") or {}
    running_balance = raw_transaction.get("running_balance")

    if has_invalid_raw_decimal_format(raw_payload, "running_balance"):
        add_issue(
            issues,
            "TRANSACTION_RUNNING_BALANCE_INVALID_FORMAT",
            "running_balance must be a valid numeric amount when provided.",
            f"Invalid running_balance format: {raw_payload.get('running_balance')!r}.",
        )
        return

    if running_balance is None:
        return

    if running_balance < 0:
        add_issue(
            issues,
            "TRANSACTION_RUNNING_BALANCE_NEGATIVE",
            "running_balance cannot be negative.",
            f"Invalid running_balance: {running_balance}.",
        )


def validate_country_code(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    country_code = value_as_string(raw_transaction.get("country_code"))

    if is_blank(country_code):
        return

    if COUNTRY_CODE_PATTERN.fullmatch(str(country_code).strip()) is None:
        add_issue(
            issues,
            "TRANSACTION_COUNTRY_CODE_INVALID",
            "country_code must be a two- or three-letter uppercase code when provided.",
            f"Invalid country_code: {country_code!r}.",
        )


def validate_city(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    city = value_as_string(raw_transaction.get("city"))

    if is_blank(city):
        return

    if not is_name_like_value(city):
        add_issue(
            issues,
            "TRANSACTION_CITY_INVALID",
            "city must be a readable place name when provided.",
            f"Invalid city: {city!r}.",
        )


def validate_device_id(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_channel = value_as_string(raw_transaction.get("transaction_channel"))
    device_id = value_as_string(raw_transaction.get("device_id"))

    if transaction_channel and str(transaction_channel).strip() in {"mobile_app", "online_banking", "card_pos"} and is_blank(device_id):
        add_issue(
            issues,
            "TRANSACTION_DEVICE_ID_MISSING",
            "device_id is required for digital and card channels.",
            f"Missing device_id for channel {transaction_channel!r}.",
        )
        return

    if is_blank(device_id):
        return

    if DEVICE_ID_PATTERN.fullmatch(str(device_id).strip()) is None:
        add_issue(
            issues,
            "TRANSACTION_DEVICE_ID_INVALID",
            "device_id must be a readable device or terminal identifier when provided.",
            f"Invalid device_id: {device_id!r}.",
        )


def validate_is_international(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    is_international = raw_transaction.get("is_international")

    if is_international is None:
        add_issue(
            issues,
            "TRANSACTION_IS_INTERNATIONAL_MISSING",
            "is_international is required.",
            "Missing is_international.",
        )
        return

    if not isinstance(is_international, bool):
        add_issue(
            issues,
            "TRANSACTION_IS_INTERNATIONAL_INVALID",
            "is_international must be a boolean value.",
            f"Invalid is_international value: {is_international!r}.",
        )


def validate_direction_consistency(raw_transaction: dict, issues: list[ValidationIssue]) -> None:
    transaction_type = value_as_string(raw_transaction.get("transaction_type"))
    transaction_direction = value_as_string(raw_transaction.get("transaction_direction"))

    if is_blank(transaction_type) or is_blank(transaction_direction):
        return

    trimmed_transaction_type = str(transaction_type).strip()
    trimmed_transaction_direction = str(transaction_direction).strip()
    allowed_types = TRANSACTION_TYPES_BY_DIRECTION.get(trimmed_transaction_direction)

    if allowed_types is None or trimmed_transaction_type not in allowed_types:
        add_issue(
            issues,
            "TRANSACTION_DIRECTION_TYPE_MISMATCH",
            "transaction_type must match the expected transaction_direction.",
            f"transaction_type {trimmed_transaction_type!r} does not align with transaction_direction {trimmed_transaction_direction!r}.",
        )


def validate_raw_transaction(
    raw_transaction: dict,
    duplicate_source_transaction_ids: set[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    validate_source_transaction_id(
        raw_transaction=raw_transaction,
        duplicate_source_transaction_ids=duplicate_source_transaction_ids,
        issues=issues,
    )
    validate_account_link_fields(raw_transaction, issues)
    validate_transaction_timestamp(raw_transaction, issues)
    validate_transaction_type(raw_transaction, issues)
    validate_transaction_channel(raw_transaction, issues)
    validate_transaction_direction(raw_transaction, issues)
    validate_direction_consistency(raw_transaction, issues)
    validate_transaction_amount(raw_transaction, issues)
    validate_transaction_currency(raw_transaction, issues)
    validate_counterparty_reference(raw_transaction, issues)
    validate_merchant_category(raw_transaction, issues)
    validate_transaction_status(raw_transaction, issues)
    validate_running_balance(raw_transaction, issues)
    validate_country_code(raw_transaction, issues)
    validate_city(raw_transaction, issues)
    validate_device_id(raw_transaction, issues)
    validate_is_international(raw_transaction, issues)

    return issues


def validation_issues_to_dicts(validation_issues: list[ValidationIssue]) -> list[dict]:
    return [issue.to_dict() for issue in validation_issues]


def run_smoke_test() -> None:
    valid_transaction = {
        "source_transaction_id": "TXN-00000001",
        "source_account_id": "SRC-ACCT-000001",
        "account_number": "SBZA0000000001",
        "transaction_timestamp": datetime(2026, 8, 1, 9, 30, 0),
        "transaction_type": "purchase",
        "transaction_channel": "card_pos",
        "transaction_direction": "debit",
        "transaction_amount": Decimal("125.50"),
        "transaction_currency": "ZAR",
        "counterparty_reference": "POS-0001-0001",
        "merchant_category": "groceries",
        "transaction_status": "posted",
        "running_balance": Decimal("9550.00"),
        "country_code": "ZA",
        "city": "Johannesburg",
        "device_id": "CAR-0001-4821",
        "is_international": False,
        "raw_payload": {
            "transaction_timestamp": "2026-08-01T09:30:00",
            "transaction_amount": "125.50",
            "running_balance": "9550.00",
        },
    }

    invalid_transaction = {
        "source_transaction_id": " BAD-ID ",
        "source_account_id": "",
        "account_number": "",
        "transaction_timestamp": None,
        "transaction_type": "airdrop",
        "transaction_channel": "sms",
        "transaction_direction": "sideways",
        "transaction_amount": Decimal("-99.99"),
        "transaction_currency": "rand",
        "counterparty_reference": "",
        "merchant_category": "",
        "transaction_status": "settled",
        "running_balance": Decimal("-10.00"),
        "country_code": "south-africa",
        "city": "123Town",
        "device_id": "x",
        "is_international": "maybe",
        "raw_payload": {
            "transaction_timestamp": "not-a-timestamp",
            "transaction_amount": "-99.99",
            "running_balance": "-10.00",
        },
    }

    valid_issues = validate_raw_transaction(valid_transaction)
    invalid_issues = validate_raw_transaction(invalid_transaction)

    print("Transaction validator smoke test finished")
    print(f"Valid transaction issue count: {len(valid_issues)}")
    print(f"Invalid transaction issue count: {len(invalid_issues)}")

    if valid_issues:
        raise AssertionError("Valid transaction unexpectedly failed validation.")

    if not invalid_issues:
        raise AssertionError("Invalid transaction unexpectedly passed validation.")


if __name__ == "__main__":
    run_smoke_test()
