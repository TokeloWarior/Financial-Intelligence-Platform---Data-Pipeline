import csv
import random
from datetime import date, timedelta
from pathlib import Path


INPUT_CUSTOMERS_FILE_PATH = Path("data/synthetic/customers.csv")
OUTPUT_ACCOUNTS_FILE_PATH = Path("data/synthetic/accounts.csv")
RANDOM_SEED = 2026


BANKS_BY_COUNTRY = {
    "South Africa": [
        ("Standard Bank", "SBZA"),
        ("FNB", "FNBZ"),
        ("Nedbank", "NEDZ"),
        ("ABSA", "ABSZ"),
        ("Capitec", "CPTC"),
    ],
    "Zimbabwe": [
        ("CBZ Bank", "CBZZ"),
        ("Stanbic Bank Zimbabwe", "STBZ"),
        ("FBC Bank", "FBCZ"),
    ],
    "Botswana": [
        ("First National Bank Botswana", "FNBB"),
        ("Standard Chartered Botswana", "SCBZ"),
        ("Absa Botswana", "ABSB"),
    ],
    "Lesotho": [
        ("Standard Lesotho Bank", "SLBL"),
        ("FNB Lesotho", "FNBL"),
        ("Nedbank Lesotho", "NEDL"),
    ],
    "Eswatini": [
        ("First National Bank Eswatini", "FNBE"),
        ("Standard Bank Eswatini", "SBZE"),
        ("Nedbank Eswatini", "NEDE"),
    ],
    "Namibia": [
        ("Standard Bank Namibia", "SBZN"),
        ("FNB Namibia", "FNNM"),
        ("Bank Windhoek", "BWND"),
    ],
    "Mozambique": [
        ("Standard Bank Mozambique", "SBZM"),
        ("BCI Mozambique", "BCIM"),
        ("FNB Mozambique", "FNBM"),
    ],
}

CURRENCY_BY_COUNTRY = {
    "South Africa": "ZAR",
    "Zimbabwe": "USD",
    "Botswana": "BWP",
    "Lesotho": "LSL",
    "Eswatini": "SZL",
    "Namibia": "NAD",
    "Mozambique": "MZN",
}

ACCOUNT_TYPES_BY_CUSTOMER_TYPE = {
    "individual": [
        "savings",
        "transactional",
        "cash_management",
        "premium_current",
    ],
    "business": [
        "business_current",
        "business_savings",
        "merchant_settlement",
        "cash_management",
    ],
}

ACCOUNT_STATUS_BY_CUSTOMER_STATUS = {
    "active": "active",
    "inactive": "dormant",
    "suspended": "restricted",
    "closed": "closed",
}

INCOME_BAND_BASES = {
    "0-4999": 750.0,
    "5000-9999": 2200.0,
    "10000-19999": 5500.0,
    "20000-39999": 12000.0,
    "40000-79999": 26000.0,
    "80000+": 55000.0,
}

ACCOUNT_TYPE_MULTIPLIERS = {
    "savings": 1.0,
    "transactional": 1.25,
    "cash_management": 1.45,
    "premium_current": 1.75,
    "business_current": 2.0,
    "business_savings": 1.6,
    "merchant_settlement": 2.35,
}

FIELDNAMES = [
    "source_account_id",
    "source_customer_id",
    "customer_link_type",
    "customer_link_key",
    "id_number",
    "passport_number",
    "country_of_birth",
    "bank_name",
    "bank_code",
    "branch_name",
    "account_number",
    "account_type",
    "account_currency",
    "account_status",
    "account_age_months",
    "opened_date",
    "account_balance",
    "monthly_deposits",
    "monthly_withdrawals",
    "overdraft_limit",
    "mobile_banking_enabled",
]


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    if value.strip() == "":
        return None

    return value


def read_customer_rows(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Customer file not found: {file_path}")

    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def parse_date_safely(value: str | None) -> date | None:
    value = blank_to_none(value)

    if value is None:
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def calculate_age(date_of_birth: date) -> int:
    today = date.today()
    age = today.year - date_of_birth.year

    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1

    return age


def choose_link_field(customer_row: dict) -> tuple[str, str]:
    source_customer_id = blank_to_none(customer_row.get("source_customer_id"))
    id_number = blank_to_none(customer_row.get("id_number"))
    passport_number = blank_to_none(customer_row.get("passport_number"))

    if id_number is not None:
        return "id_number", id_number.strip()

    if passport_number is not None:
        return "passport_number", passport_number.strip()

    if source_customer_id is not None:
        return "source_customer_id", source_customer_id.strip()

    return "source_row_number", "unknown"


def build_customer_link_key(link_type: str, link_value: str) -> str:
    return f"{link_type}:{link_value}"


def build_rng(seed_value: str) -> random.Random:
    return random.Random(seed_value)


def choose_bank(country_of_birth: str | None, rng: random.Random) -> tuple[str, str]:
    bank_choices = BANKS_BY_COUNTRY.get(country_of_birth or "", [])

    if not bank_choices:
        bank_choices = [("Global Trust Bank", "GLTB")]

    return rng.choice(bank_choices)


def choose_currency(country_of_birth: str | None) -> str:
    return CURRENCY_BY_COUNTRY.get(country_of_birth or "", "USD")


def choose_account_type(customer_type: str | None, income_band: str | None, age_years: int, rng: random.Random) -> str:
    account_type_pool = ACCOUNT_TYPES_BY_CUSTOMER_TYPE.get(customer_type or "individual", ["savings"])

    if customer_type == "business":
        if income_band in {"40000-79999", "80000+"}:
            account_type_pool = ["business_current", "merchant_settlement", "cash_management"]
        else:
            account_type_pool = ["business_savings", "business_current", "cash_management"]
    elif age_years < 25:
        account_type_pool = ["savings", "transactional"]
    elif income_band in {"40000-79999", "80000+"}:
        account_type_pool = ["premium_current", "cash_management", "transactional"]

    return rng.choice(account_type_pool)


def choose_account_status(customer_status: str | None) -> str:
    return ACCOUNT_STATUS_BY_CUSTOMER_STATUS.get(customer_status or "active", "active")


def calculate_account_age_months(date_of_birth: date | None, rng: random.Random) -> int:
    customer_age_years = calculate_age(date_of_birth) if date_of_birth is not None else 35
    upper_bound = max(12, min(240, customer_age_years * 12))

    if upper_bound <= 12:
        return 12

    return rng.randint(12, upper_bound)


def calculate_account_metrics(
    account_type: str,
    income_band: str | None,
    account_age_months: int,
    rng: random.Random,
) -> tuple[float, float, float, float, date, bool]:
    income_base = INCOME_BAND_BASES.get(income_band or "", 3500.0)
    type_multiplier = ACCOUNT_TYPE_MULTIPLIERS.get(account_type, 1.0)

    monthly_deposits = round(income_base * type_multiplier * rng.uniform(0.45, 0.95), 2)
    monthly_withdrawals = round(monthly_deposits * rng.uniform(0.35, 0.92), 2)
    account_balance = round(max(250.0, income_base * type_multiplier * rng.uniform(0.8, 3.4)), 2)
    overdraft_limit = round(account_balance * rng.uniform(0.05, 0.25), 2) if "current" in account_type or "settlement" in account_type or "management" in account_type else 0.0
    opened_date = date.today() - timedelta(days=account_age_months * 30)
    mobile_banking_enabled = rng.random() > 0.08

    return (
        account_balance,
        monthly_deposits,
        monthly_withdrawals,
        overdraft_limit,
        opened_date,
        mobile_banking_enabled,
    )


def build_account_row(customer_row: dict, account_sequence: int) -> dict:
    source_customer_id = blank_to_none(customer_row.get("source_customer_id"))
    id_number = blank_to_none(customer_row.get("id_number"))
    passport_number = blank_to_none(customer_row.get("passport_number"))
    country_of_birth = blank_to_none(customer_row.get("country_of_birth"))
    customer_type = blank_to_none(customer_row.get("customer_type"))
    customer_status = blank_to_none(customer_row.get("customer_status"))
    income_band = blank_to_none(customer_row.get("income_band"))
    date_of_birth = parse_date_safely(customer_row.get("date_of_birth"))

    link_type, link_value = choose_link_field(customer_row)
    customer_link_key = build_customer_link_key(link_type, link_value)
    rng = build_rng(customer_link_key)

    bank_name, bank_code = choose_bank(country_of_birth, rng)
    account_type = choose_account_type(customer_type, income_band, calculate_age(date_of_birth) if date_of_birth else 35, rng)
    account_status = choose_account_status(customer_status)
    account_age_months = calculate_account_age_months(date_of_birth, rng)
    account_balance, monthly_deposits, monthly_withdrawals, overdraft_limit, opened_date, mobile_banking_enabled = calculate_account_metrics(
        account_type=account_type,
        income_band=income_band,
        account_age_months=account_age_months,
        rng=rng,
    )

    source_account_id = f"SRC-ACCT-{account_sequence:06d}"
    account_number = f"{bank_code}{account_sequence:010d}"
    branch_name = f"{blank_to_none(customer_row.get('city')) or 'Central'} Branch"

    return {
        "source_account_id": source_account_id,
        "source_customer_id": source_customer_id or "",
        "customer_link_type": link_type,
        "customer_link_key": customer_link_key,
        "id_number": id_number or "",
        "passport_number": passport_number or "",
        "country_of_birth": country_of_birth or "",
        "bank_name": bank_name,
        "bank_code": bank_code,
        "branch_name": branch_name,
        "account_number": account_number,
        "account_type": account_type,
        "account_currency": choose_currency(country_of_birth),
        "account_status": account_status,
        "account_age_months": account_age_months,
        "opened_date": opened_date.isoformat(),
        "account_balance": account_balance,
        "monthly_deposits": monthly_deposits,
        "monthly_withdrawals": monthly_withdrawals,
        "overdraft_limit": overdraft_limit,
        "mobile_banking_enabled": mobile_banking_enabled,
    }


def generate_accounts() -> list[dict]:
    random.seed(RANDOM_SEED)

    customer_rows = read_customer_rows(INPUT_CUSTOMERS_FILE_PATH)
    seen_customer_links: set[str] = set()
    accounts: list[dict] = []

    for customer_row in customer_rows:
        account_row = build_account_row(customer_row, len(accounts) + 1)
        customer_link_key = account_row["customer_link_key"]

        if customer_link_key in seen_customer_links:
            continue

        seen_customer_links.add(customer_link_key)
        accounts.append(account_row)

    return accounts


def write_accounts_to_csv(accounts: list[dict]) -> None:
    OUTPUT_ACCOUNTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_ACCOUNTS_FILE_PATH.open(mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(accounts)


def main() -> None:
    accounts = generate_accounts()
    write_accounts_to_csv(accounts)

    print(f"Generated accounts: {len(accounts)}")
    print(f"Output file: {OUTPUT_ACCOUNTS_FILE_PATH}")


if __name__ == "__main__":
    main()
