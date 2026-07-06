from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


SOURCE_CUSTOMER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,127}$")

MINIMUM_CUSTOMER_AGE = 18
MAXIMUM_CUSTOMER_AGE = 95


VALID_CUSTOMER_TYPES = {
    "individual",
    "business",
}

VALID_GENDERS = {
    "female",
    "male",
    "other",
    "unknown",
}

VALID_EMPLOYMENT_STATUSES = {
    "employed",
    "self_employed",
    "self-employed",
    "unemployed",
    "student",
    "retired",
}

VALID_INCOME_BANDS = {
    "0-4999",
    "5000-9999",
    "10000-19999",
    "20000-39999",
    "40000-79999",
    "80000+",
}

VALID_CUSTOMER_STATUSES = {
    "active",
    "inactive",
    "suspended",
    "closed",
}

VALID_KYC_STATUSES = {
    "not_started",
    "pending",
    "verified",
    "failed",
    "expired",
}

VALID_RISK_RATINGS = {
    "low",
    "medium",
    "high",
}
IDENTITY_DOCUMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{4,31}$")
PHONE_NUMBER_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass(frozen=True)
class ValidationIssue:
    """
    Represents one validation issue for one raw customer record.

    These fields map cleanly to ops.rejected_records.
    """

    rule_code: str
    rule_description: str
    rejection_reason: str
    severity: str = "error"

    def to_dict(self) -> dict:
        """
        Convert the validation issue into a dictionary.
        """

        return asdict(self)


def is_blank(value: Any) -> bool:
    """
    Return True when a value is None or blank after trimming.
    """

    if value is None:
        return True

    return str(value).strip() == ""


def value_as_string(value: Any) -> str | None:
    """
    Convert a non-null value to string.

    Returns None when the value is None.
    """

    if value is None:
        return None

    return str(value)


def parse_raw_date_value(value: Any) -> date | None:
    """
    Parse a raw date string in YYYY-MM-DD format.

    Returns None if the value is blank or invalid.
    """

    if is_blank(value):
        return None

    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_age(date_of_birth: date, today: date | None = None) -> int:
    """
    Calculate age from date_of_birth.
    """

    if today is None:
        today = date.today()

    age = today.year - date_of_birth.year

    has_not_had_birthday_this_year = (today.month, today.day) < (
        date_of_birth.month,
        date_of_birth.day,
    )

    if has_not_had_birthday_this_year:
        age -= 1

    return age


def has_invalid_raw_date_format(raw_payload: dict, field_name: str) -> bool:
    """
    Detect whether a raw date field had a non-blank but invalid format.

    Example:
        raw_payload["date_of_birth"] = "not-a-date"
        typed raw_customers.date_of_birth = NULL

    This should be rejected as invalid format, not only treated as missing.
    """

    raw_value = raw_payload.get(field_name)

    if is_blank(raw_value):
        return False

    return parse_raw_date_value(raw_value) is None


def add_issue(
    issues: list[ValidationIssue],
    rule_code: str,
    rule_description: str,
    rejection_reason: str,
    severity: str = "error",
) -> None:
    """
    Add one validation issue to a list.
    """

    issues.append(
        ValidationIssue(
            rule_code=rule_code,
            rule_description=rule_description,
            rejection_reason=rejection_reason,
            severity=severity,
        )
    )


def is_name_like_value(value: str | None) -> bool:
    """
    Return True when a value looks like a human-readable name or place name.

    This stays country-agnostic by allowing Unicode letters, spaces, apostrophes,
    hyphens, and periods.
    """

    if is_blank(value):
        return False

    trimmed_value = value.strip()

    if not trimmed_value[0].isalpha() or not trimmed_value[-1].isalpha():
        return False

    allowed_characters = {" ", "'", "-", "."}

    return all(char.isalpha() or char in allowed_characters for char in trimmed_value)


def is_valid_identity_document(value: str | None) -> bool:
    """
    Return True when a document identifier has a generic, source-agnostic shape.
    """

    if is_blank(value):
        return False

    return IDENTITY_DOCUMENT_PATTERN.fullmatch(value.strip()) is not None


def validate_source_customer_id(
    raw_customer: dict,
    duplicate_source_customer_ids: set[str] | None,
    issues: list[ValidationIssue],
) -> None:
    """
    Validate source_customer_id.
    """

    source_customer_id = value_as_string(raw_customer.get("source_customer_id"))

    if is_blank(source_customer_id):
        add_issue(
            issues,
            "CUSTOMER_ID_MISSING",
            "source_customer_id is required.",
            "Missing source_customer_id.",
        )
        return

    if source_customer_id != source_customer_id.strip():
        add_issue(
            issues,
            "CUSTOMER_ID_HAS_WHITESPACE",
            "source_customer_id must not contain leading or trailing whitespace.",
            f"source_customer_id has leading or trailing whitespace: {source_customer_id!r}.",
        )

    trimmed_customer_id = source_customer_id.strip()

    if SOURCE_CUSTOMER_ID_PATTERN.fullmatch(trimmed_customer_id) is None:
        add_issue(
            issues,
            "CUSTOMER_ID_INVALID_FORMAT",
            "source_customer_id must be a non-empty source identifier with no spaces.",
            f"Invalid source_customer_id format: {source_customer_id!r}.",
        )

    if duplicate_source_customer_ids and trimmed_customer_id in duplicate_source_customer_ids:
        add_issue(
            issues,
            "CUSTOMER_ID_DUPLICATE_IN_BATCH",
            "source_customer_id must be unique within the incoming batch.",
            f"Duplicate source_customer_id found in batch: {trimmed_customer_id}.",
        )


def validate_customer_type(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate customer_type.
    """

    customer_type = value_as_string(raw_customer.get("customer_type"))

    if is_blank(customer_type):
        add_issue(
            issues,
            "CUSTOMER_TYPE_MISSING",
            "customer_type is required.",
            "Missing customer_type.",
        )
        return

    if customer_type.strip() not in VALID_CUSTOMER_TYPES:
        add_issue(
            issues,
            "CUSTOMER_TYPE_INVALID",
            "customer_type must be one of the allowed values.",
            f"Invalid customer_type: {customer_type!r}.",
        )


def validate_date_of_birth(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate date_of_birth.
    """

    raw_payload = raw_customer.get("raw_payload") or {}
    date_of_birth = raw_customer.get("date_of_birth")

    if has_invalid_raw_date_format(raw_payload, "date_of_birth"):
        add_issue(
            issues,
            "CUSTOMER_DOB_INVALID_FORMAT",
            "date_of_birth must be a valid date in YYYY-MM-DD format.",
            f"Invalid date_of_birth format: {raw_payload.get('date_of_birth')!r}.",
        )
        return

    if date_of_birth is None:
        add_issue(
            issues,
            "CUSTOMER_DOB_MISSING",
            "date_of_birth is required.",
            "Missing date_of_birth.",
        )
        return

    today = date.today()

    if date_of_birth > today:
        add_issue(
            issues,
            "CUSTOMER_DOB_IN_FUTURE",
            "date_of_birth cannot be in the future.",
            f"date_of_birth is in the future: {date_of_birth}.",
        )
        return

    age = calculate_age(date_of_birth, today=today)

    if age < MINIMUM_CUSTOMER_AGE:
        add_issue(
            issues,
            "CUSTOMER_UNDERAGE",
            "Customer must be at least 18 years old.",
            f"Customer age is below {MINIMUM_CUSTOMER_AGE}: {age}.",
        )

    if age > MAXIMUM_CUSTOMER_AGE:
        add_issue(
            issues,
            "CUSTOMER_AGE_UNREALISTIC",
            "Customer age must not exceed the maximum realistic age threshold.",
            f"Customer age is above {MAXIMUM_CUSTOMER_AGE}: {age}.",
        )


def validate_gender(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate gender.
    """

    gender = value_as_string(raw_customer.get("gender"))

    if is_blank(gender):
        return

    if gender.strip() not in VALID_GENDERS:
        add_issue(
            issues,
            "CUSTOMER_GENDER_INVALID",
            "gender must be one of the allowed values when provided.",
            f"Invalid gender: {gender!r}.",
        )


def validate_name_field(
    raw_customer: dict,
    field_name: str,
    issues: list[ValidationIssue],
) -> None:
    """
    Validate a required profile name field.
    """

    value = value_as_string(raw_customer.get(field_name))

    if is_blank(value):
        add_issue(
            issues,
            f"CUSTOMER_{field_name.upper()}_MISSING",
            f"{field_name} is required.",
            f"Missing {field_name}.",
        )
        return

    trimmed_value = value.strip()

    if trimmed_value != value:
        add_issue(
            issues,
            f"CUSTOMER_{field_name.upper()}_WHITESPACE",
            f"{field_name} must not contain leading or trailing whitespace.",
            f"{field_name} has leading or trailing whitespace: {value!r}.",
        )

    if not is_name_like_value(trimmed_value):
        add_issue(
            issues,
            f"CUSTOMER_{field_name.upper()}_INVALID",
            f"{field_name} must contain only letters, spaces, apostrophes, hyphens, or periods.",
            f"Invalid {field_name}: {value!r}.",
        )


def validate_country_of_birth(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate country_of_birth.
    """

    country_of_birth = value_as_string(raw_customer.get("country_of_birth"))

    if is_blank(country_of_birth):
        add_issue(
            issues,
            "CUSTOMER_COUNTRY_OF_BIRTH_MISSING",
            "country_of_birth is required.",
            "Missing country_of_birth.",
        )
        return

    if not is_name_like_value(country_of_birth):
        add_issue(
            issues,
            "CUSTOMER_COUNTRY_OF_BIRTH_INVALID",
            "country_of_birth must be a readable country name.",
            f"Invalid country_of_birth: {country_of_birth!r}.",
        )


def validate_primary_phone_number(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate primary_phone_number.
    """

    primary_phone_number = value_as_string(raw_customer.get("primary_phone_number"))

    if is_blank(primary_phone_number):
        add_issue(
            issues,
            "CUSTOMER_PRIMARY_PHONE_NUMBER_MISSING",
            "primary_phone_number is required.",
            "Missing primary_phone_number.",
        )
        return

    trimmed_phone = primary_phone_number.strip()

    if PHONE_NUMBER_PATTERN.fullmatch(trimmed_phone) is None:
        add_issue(
            issues,
            "CUSTOMER_PRIMARY_PHONE_NUMBER_INVALID",
            "primary_phone_number must match international E.164 format.",
            f"Invalid primary_phone_number: {primary_phone_number!r}.",
        )


def validate_secondary_phone_number(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate secondary_phone_number when provided.
    """

    secondary_phone_number = value_as_string(raw_customer.get("secondary_phone_number"))

    if is_blank(secondary_phone_number):
        return

    trimmed_phone = secondary_phone_number.strip()

    if PHONE_NUMBER_PATTERN.fullmatch(trimmed_phone) is None:
        add_issue(
            issues,
            "CUSTOMER_SECONDARY_PHONE_NUMBER_INVALID",
            "secondary_phone_number must match international E.164 format when provided.",
            f"Invalid secondary_phone_number: {secondary_phone_number!r}.",
        )


def validate_identity_documents(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate id_number and passport_number using source-agnostic document rules.
    """

    id_number = value_as_string(raw_customer.get("id_number"))
    passport_number = value_as_string(raw_customer.get("passport_number"))
    trimmed_id_number = None if is_blank(id_number) else id_number.strip()
    trimmed_passport_number = None if is_blank(passport_number) else passport_number.strip()

    if trimmed_id_number is None and trimmed_passport_number is None:
        add_issue(
            issues,
            "CUSTOMER_IDENTITY_DOCUMENT_MISSING",
            "Either id_number or passport_number is required.",
            "Missing both id_number and passport_number.",
        )

    if trimmed_id_number is not None and not is_valid_identity_document(trimmed_id_number):
        add_issue(
            issues,
            "CUSTOMER_ID_NUMBER_INVALID",
            "id_number must be a readable alphanumeric identifier.",
            f"Invalid id_number: {id_number!r}.",
        )

    if trimmed_passport_number is not None and not is_valid_identity_document(trimmed_passport_number):
        add_issue(
            issues,
            "CUSTOMER_PASSPORT_NUMBER_INVALID",
            "passport_number must be a readable alphanumeric identifier.",
            f"Invalid passport_number: {passport_number!r}.",
        )


def validate_region_and_city(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate region and city as generic place names.
    """

    region = value_as_string(raw_customer.get("region"))
    city = value_as_string(raw_customer.get("city"))

    if is_blank(region):
        add_issue(
            issues,
            "CUSTOMER_REGION_MISSING",
            "region is required.",
            "Missing region.",
        )
        return

    if not is_name_like_value(region):
        add_issue(
            issues,
            "CUSTOMER_REGION_INVALID",
            "region must be a readable place name.",
            f"Invalid region: {region!r}.",
        )
        return

    if is_blank(city):
        add_issue(
            issues,
            "CUSTOMER_CITY_MISSING",
            "city is required.",
            "Missing city.",
        )
        return

    if not is_name_like_value(city):
        add_issue(
            issues,
            "CUSTOMER_CITY_INVALID",
            "city must be a readable place name.",
            f"Invalid city: {city!r}.",
        )


def validate_employment_status(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate employment_status.
    """

    employment_status = value_as_string(raw_customer.get("employment_status"))

    if is_blank(employment_status):
        add_issue(
            issues,
            "CUSTOMER_EMPLOYMENT_STATUS_MISSING",
            "employment_status is required.",
            "Missing employment_status.",
        )
        return

    if employment_status.strip() not in VALID_EMPLOYMENT_STATUSES:
        add_issue(
            issues,
            "CUSTOMER_EMPLOYMENT_STATUS_INVALID",
            "employment_status must be one of the allowed values.",
            f"Invalid employment_status: {employment_status!r}.",
        )


def validate_income_band(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate income_band.
    """

    income_band = value_as_string(raw_customer.get("income_band"))

    if is_blank(income_band):
        add_issue(
            issues,
            "CUSTOMER_INCOME_BAND_MISSING",
            "income_band is required.",
            "Missing income_band.",
        )
        return

    if income_band.strip() not in VALID_INCOME_BANDS:
        add_issue(
            issues,
            "CUSTOMER_INCOME_BAND_INVALID",
            "income_band must be one of the allowed values.",
            f"Invalid income_band: {income_band!r}.",
        )


def validate_customer_status(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate customer_status.
    """

    customer_status = value_as_string(raw_customer.get("customer_status"))

    if is_blank(customer_status):
        add_issue(
            issues,
            "CUSTOMER_STATUS_MISSING",
            "customer_status is required.",
            "Missing customer_status.",
        )
        return

    if customer_status.strip() not in VALID_CUSTOMER_STATUSES:
        add_issue(
            issues,
            "CUSTOMER_STATUS_INVALID",
            "customer_status must be one of the allowed values.",
            f"Invalid customer_status: {customer_status!r}.",
        )


def validate_onboarding_date(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate onboarding_date.
    """

    raw_payload = raw_customer.get("raw_payload") or {}
    date_of_birth = raw_customer.get("date_of_birth")
    onboarding_date = raw_customer.get("onboarding_date")

    if has_invalid_raw_date_format(raw_payload, "onboarding_date"):
        add_issue(
            issues,
            "CUSTOMER_ONBOARDING_DATE_INVALID_FORMAT",
            "onboarding_date must be a valid date in YYYY-MM-DD format.",
            f"Invalid onboarding_date format: {raw_payload.get('onboarding_date')!r}.",
        )
        return

    if onboarding_date is None:
        add_issue(
            issues,
            "CUSTOMER_ONBOARDING_DATE_MISSING",
            "onboarding_date is required.",
            "Missing onboarding_date.",
        )
        return

    today = date.today()

    if onboarding_date > today:
        add_issue(
            issues,
            "CUSTOMER_ONBOARDING_DATE_IN_FUTURE",
            "onboarding_date cannot be in the future.",
            f"onboarding_date is in the future: {onboarding_date}.",
        )

    if date_of_birth is None:
        return

    eighteenth_birthday = date(
        date_of_birth.year + MINIMUM_CUSTOMER_AGE,
        date_of_birth.month,
        date_of_birth.day,
    )

    if onboarding_date < eighteenth_birthday:
        add_issue(
            issues,
            "CUSTOMER_ONBOARDED_BEFORE_18",
            "Customer onboarding_date cannot be before the customer turned 18.",
            f"onboarding_date {onboarding_date} is before eighteenth birthday {eighteenth_birthday}.",
        )


def validate_kyc_status(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate kyc_status.
    """

    kyc_status = value_as_string(raw_customer.get("kyc_status"))

    if is_blank(kyc_status):
        add_issue(
            issues,
            "CUSTOMER_KYC_STATUS_MISSING",
            "kyc_status is required.",
            "Missing kyc_status.",
        )
        return

    if kyc_status.strip() not in VALID_KYC_STATUSES:
        add_issue(
            issues,
            "CUSTOMER_KYC_STATUS_INVALID",
            "kyc_status must be one of the allowed values.",
            f"Invalid kyc_status: {kyc_status!r}.",
        )


def validate_risk_rating(raw_customer: dict, issues: list[ValidationIssue]) -> None:
    """
    Validate risk_rating.
    """

    risk_rating = value_as_string(raw_customer.get("risk_rating"))

    if is_blank(risk_rating):
        add_issue(
            issues,
            "CUSTOMER_RISK_RATING_MISSING",
            "risk_rating is required.",
            "Missing risk_rating.",
        )
        return

    if risk_rating.strip() not in VALID_RISK_RATINGS:
        add_issue(
            issues,
            "CUSTOMER_RISK_RATING_INVALID",
            "risk_rating must be one of the allowed values.",
            f"Invalid risk_rating: {risk_rating!r}.",
        )


def validate_raw_customer(
    raw_customer: dict,
    duplicate_source_customer_ids: set[str] | None = None,
) -> list[ValidationIssue]:
    """
    Validate one raw customer record.

    Args:
        raw_customer:
            Dictionary representing one row from raw.raw_customers.

        duplicate_source_customer_ids:
            Optional set of source_customer_id values that appear more than once
            in the current validation batch.

    Returns:
        A list of validation issues.
        If the list is empty, the record is valid.
    """

    issues: list[ValidationIssue] = []

    validate_source_customer_id(
        raw_customer=raw_customer,
        duplicate_source_customer_ids=duplicate_source_customer_ids,
        issues=issues,
    )

    validate_customer_type(raw_customer, issues)
    validate_name_field(raw_customer, "first_name", issues)
    validate_name_field(raw_customer, "last_name", issues)
    validate_country_of_birth(raw_customer, issues)
    validate_identity_documents(raw_customer, issues)
    validate_primary_phone_number(raw_customer, issues)
    validate_secondary_phone_number(raw_customer, issues)
    validate_date_of_birth(raw_customer, issues)
    validate_gender(raw_customer, issues)
    validate_region_and_city(raw_customer, issues)
    validate_employment_status(raw_customer, issues)
    validate_income_band(raw_customer, issues)
    validate_customer_status(raw_customer, issues)
    validate_onboarding_date(raw_customer, issues)
    validate_kyc_status(raw_customer, issues)
    validate_risk_rating(raw_customer, issues)

    return issues


def validation_issues_to_dicts(
    validation_issues: list[ValidationIssue],
) -> list[dict]:
    """
    Convert validation issues into dictionaries.
    """

    return [issue.to_dict() for issue in validation_issues]


def run_smoke_test() -> None:
    """
    Run a small smoke test to confirm the validator module works.
    """

    valid_customer = {
        "source_customer_id": "CUST-999001",
        "customer_type": "individual",
        "first_name": "Lerato",
        "last_name": "Mokoena",
        "id_number": "",
        "passport_number": "X1234567",
        "country_of_birth": "Côte d'Ivoire",
        "primary_phone_number": "+14155552671",
        "secondary_phone_number": "",
        "date_of_birth": date(1990, 1, 1),
        "gender": "female",
        "region": "Greater Accra",
        "city": "Accra",
        "employment_status": "employed",
        "income_band": "20000-39999",
        "customer_status": "active",
        "onboarding_date": date(2015, 1, 1),
        "kyc_status": "verified",
        "risk_rating": "low",
        "raw_payload": {
            "date_of_birth": "1990-01-01",
            "onboarding_date": "2015-01-01",
        },
    }

    invalid_customer = {
        "source_customer_id": " BAD-ID ",
        "customer_type": "vip_person",
        "first_name": "",
        "last_name": "12345",
        "id_number": "ABC",
        "passport_number": "passport",
        "country_of_birth": "123Land",
        "primary_phone_number": "12345",
        "secondary_phone_number": "not-a-phone",
        "date_of_birth": None,
        "gender": "robot",
        "region": "Atlantis",
        "city": "Poseidon City",
        "employment_status": "gig_worker",
        "income_band": "999999-1000000",
        "customer_status": "paused",
        "onboarding_date": None,
        "kyc_status": "approved",
        "risk_rating": "extreme",
        "raw_payload": {
            "date_of_birth": "not-a-date",
            "onboarding_date": "not-a-date",
        },
    }

    valid_issues = validate_raw_customer(valid_customer)
    invalid_issues = validate_raw_customer(invalid_customer)

    print("Customer validator smoke test finished")
    print(f"Valid customer issue count: {len(valid_issues)}")
    print(f"Invalid customer issue count: {len(invalid_issues)}")

    if valid_issues:
        raise AssertionError("Valid customer unexpectedly failed validation.")

    if not invalid_issues:
        raise AssertionError("Invalid customer unexpectedly passed validation.")


if __name__ == "__main__":
    run_smoke_test()