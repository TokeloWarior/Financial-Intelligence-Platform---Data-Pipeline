import csv
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pipeline.common.pipeline_logging import logger


INPUT_ACCOUNTS_FILE_PATH = Path("data/synthetic/accounts.csv")
OUTPUT_TRANSACTIONS_FILE_PATH = Path("data/synthetic/transactions.csv")
RANDOM_SEED = 20260814
INVALID_TRANSACTION_COUNT = 24


COUNTRY_CODE_BY_COUNTRY = {
    "South Africa": "ZA",
    "Zimbabwe": "ZW",
    "Botswana": "BW",
    "Lesotho": "LS",
    "Eswatini": "SZ",
    "Namibia": "NA",
    "Mozambique": "MZ",
}

TRANSACTION_TYPE_CONFIG = {
    "salary": {
        "direction": "credit",
        "channels": ["eft", "online_banking"],
        "merchant_categories": ["payroll", "employer_disbursement"],
    },
    "deposit": {
        "direction": "credit",
        "channels": ["branch", "atm", "eft"],
        "merchant_categories": ["cash_deposit", "account_funding"],
    },
    "transfer_in": {
        "direction": "credit",
        "channels": ["mobile_app", "online_banking", "eft"],
        "merchant_categories": ["peer_transfer", "wallet_topup"],
    },
    "interest": {
        "direction": "credit",
        "channels": ["online_banking"],
        "merchant_categories": ["interest_credit"],
    },
    "refund": {
        "direction": "credit",
        "channels": ["card_pos", "mobile_app", "online_banking"],
        "merchant_categories": ["merchant_refund"],
    },
    "purchase": {
        "direction": "debit",
        "channels": ["card_pos", "mobile_app", "online_banking"],
        "merchant_categories": ["groceries", "fuel", "retail", "dining", "healthcare"],
    },
    "bill_payment": {
        "direction": "debit",
        "channels": ["mobile_app", "online_banking", "eft"],
        "merchant_categories": ["utilities", "telecoms", "rent", "insurance", "school_fees"],
    },
    "cash_withdrawal": {
        "direction": "debit",
        "channels": ["atm", "branch"],
        "merchant_categories": ["cash_access"],
    },
    "transfer_out": {
        "direction": "debit",
        "channels": ["mobile_app", "online_banking", "eft"],
        "merchant_categories": ["peer_transfer", "supplier_payment"],
    },
    "withdrawal": {
        "direction": "debit",
        "channels": ["atm", "branch"],
        "merchant_categories": ["cash_access"],
    },
    "fee": {
        "direction": "debit",
        "channels": ["online_banking", "merchant_settlement"],
        "merchant_categories": ["service_fee", "bank_charge"],
    },
}

FIELDNAMES = [
    "source_transaction_id",
    "source_account_id",
    "account_number",
    "transaction_timestamp",
    "transaction_type",
    "transaction_channel",
    "transaction_direction",
    "transaction_amount",
    "transaction_currency",
    "counterparty_reference",
    "merchant_category",
    "transaction_status",
    "running_balance",
    "country_code",
    "city",
    "device_id",
    "is_international",
]


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None

    if value.strip() == "":
        return None

    return value


def parse_decimal_safely(value: str | None) -> Decimal | None:
    value = blank_to_none(value)

    if value is None:
        return None

    return Decimal(value.strip())


def read_account_rows(file_path: Path) -> list[dict]:
    if not file_path.exists():
        raise FileNotFoundError(f"Account file not found: {file_path}")

    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def build_rng(seed_value: str) -> random.Random:
    return random.Random(seed_value)


def choose_transaction_count(account_status: str | None, rng: random.Random) -> int:
    account_status = (account_status or "").strip()

    if account_status == "active":
        return rng.randint(10, 18)
    if account_status == "dormant":
        return rng.randint(3, 6)
    if account_status == "restricted":
        return rng.randint(4, 8)
    if account_status == "closed":
        return rng.randint(1, 4)

    return rng.randint(6, 10)


def choose_transaction_type(account_status: str | None, rng: random.Random) -> str:
    account_status = (account_status or "").strip()

    if account_status == "dormant":
        choices = ["fee", "interest", "cash_withdrawal", "deposit"]
        weights = [35, 20, 25, 20]
    elif account_status == "restricted":
        choices = ["fee", "transfer_in", "purchase", "bill_payment", "cash_withdrawal"]
        weights = [20, 15, 25, 20, 20]
    elif account_status == "closed":
        choices = ["fee", "transfer_out", "withdrawal", "interest"]
        weights = [30, 35, 25, 10]
    else:
        choices = [
            "salary",
            "deposit",
            "transfer_in",
            "purchase",
            "bill_payment",
            "cash_withdrawal",
            "transfer_out",
            "fee",
            "interest",
            "refund",
        ]
        weights = [14, 8, 10, 28, 10, 8, 10, 4, 4, 4]

    return rng.choices(choices, weights=weights, k=1)[0]


def choose_transaction_status(transaction_type: str, rng: random.Random) -> str:
    if transaction_type in {"fee", "interest", "salary"}:
        return rng.choices(["posted", "pending"], weights=[97, 3], k=1)[0]

    return rng.choices(["posted", "pending", "reversed"], weights=[90, 8, 2], k=1)[0]


def choose_amount(transaction_type: str, monthly_deposits: Decimal, monthly_withdrawals: Decimal, rng: random.Random) -> Decimal:
    if transaction_type == "salary":
        amount = monthly_deposits * Decimal(str(rng.uniform(0.60, 1.15)))
    elif transaction_type in {"deposit", "transfer_in", "refund"}:
        amount = monthly_deposits * Decimal(str(rng.uniform(0.08, 0.45)))
    elif transaction_type == "interest":
        amount = monthly_deposits * Decimal(str(rng.uniform(0.002, 0.015)))
    elif transaction_type in {"purchase", "bill_payment"}:
        amount = monthly_withdrawals * Decimal(str(rng.uniform(0.03, 0.28)))
    elif transaction_type in {"cash_withdrawal", "withdrawal", "transfer_out"}:
        amount = monthly_withdrawals * Decimal(str(rng.uniform(0.08, 0.42)))
    else:
        amount = monthly_withdrawals * Decimal(str(rng.uniform(0.002, 0.03)))

    minimum_amount = Decimal("5.00")
    return max(amount.quantize(Decimal("0.01")), minimum_amount)


def build_counterparty_reference(transaction_type: str, account_number: str, transaction_sequence: int) -> str:
    account_suffix = account_number[-4:] if account_number else "0000"

    prefix_by_type = {
        "salary": "EMP",
        "deposit": "DEP",
        "transfer_in": "TRI",
        "interest": "INT",
        "refund": "RFD",
        "purchase": "POS",
        "bill_payment": "BIL",
        "cash_withdrawal": "ATM",
        "transfer_out": "TRO",
        "withdrawal": "CSH",
        "fee": "FEE",
    }

    prefix = prefix_by_type.get(transaction_type, "GEN")
    return f"{prefix}-{account_suffix}-{transaction_sequence:04d}"


def build_device_id(channel: str, source_account_id: str, rng: random.Random) -> str:
    if channel not in {"mobile_app", "online_banking", "card_pos"}:
        return ""

    account_suffix = source_account_id[-4:] if source_account_id else "0000"
    return f"{channel[:3].upper()}-{account_suffix}-{rng.randint(1000, 9999)}"


def build_transaction_row(
    account_row: dict,
    transaction_sequence: int,
    running_balance: Decimal,
    transaction_timestamp: datetime,
    txn_index: int,
) -> tuple[dict, Decimal]:
    source_account_id = blank_to_none(account_row.get("source_account_id")) or ""
    account_number = blank_to_none(account_row.get("account_number")) or ""
    account_currency = blank_to_none(account_row.get("account_currency")) or "USD"
    account_status = blank_to_none(account_row.get("account_status"))
    city = (blank_to_none(account_row.get("branch_name")) or "Central Branch").replace(" Branch", "")
    country_of_birth = blank_to_none(account_row.get("country_of_birth"))
    monthly_deposits = parse_decimal_safely(account_row.get("monthly_deposits")) or Decimal("1000.00")
    monthly_withdrawals = parse_decimal_safely(account_row.get("monthly_withdrawals")) or Decimal("800.00")

    rng = build_rng(f"{source_account_id}:{txn_index}")
    transaction_type = choose_transaction_type(account_status, rng)
    config = TRANSACTION_TYPE_CONFIG[transaction_type]
    transaction_channel = rng.choice(config["channels"])
    transaction_direction = config["direction"]
    transaction_status = choose_transaction_status(transaction_type, rng)
    transaction_amount = choose_amount(transaction_type, monthly_deposits, monthly_withdrawals, rng)

    if transaction_direction == "debit" and transaction_status != "reversed":
        max_debit = max(running_balance - Decimal("25.00"), Decimal("5.00"))
        transaction_amount = min(transaction_amount, max_debit).quantize(Decimal("0.01"))

    if transaction_amount <= 0:
        transaction_amount = Decimal("5.00")

    if transaction_status == "reversed":
        next_running_balance = running_balance
    elif transaction_direction == "credit":
        next_running_balance = running_balance + transaction_amount
    else:
        next_running_balance = max(Decimal("25.00"), running_balance - transaction_amount)

    return (
        {
            "source_transaction_id": f"TXN-{transaction_sequence:08d}",
            "source_account_id": source_account_id,
            "account_number": account_number,
            "transaction_timestamp": transaction_timestamp.replace(microsecond=0).isoformat(),
            "transaction_type": transaction_type,
            "transaction_channel": transaction_channel,
            "transaction_direction": transaction_direction,
            "transaction_amount": f"{transaction_amount.quantize(Decimal('0.01'))}",
            "transaction_currency": account_currency,
            "counterparty_reference": build_counterparty_reference(transaction_type, account_number, transaction_sequence),
            "merchant_category": rng.choice(config["merchant_categories"]),
            "transaction_status": transaction_status,
            "running_balance": f"{next_running_balance.quantize(Decimal('0.01'))}",
            "country_code": COUNTRY_CODE_BY_COUNTRY.get(country_of_birth or "", "US"),
            "city": city,
            "device_id": build_device_id(transaction_channel, source_account_id, rng),
            "is_international": str(account_currency != "ZAR"),
        },
        next_running_balance,
    )


def generate_valid_transactions() -> list[dict]:
    random.seed(RANDOM_SEED)

    account_rows = read_account_rows(INPUT_ACCOUNTS_FILE_PATH)
    transactions: list[dict] = []

    for account_row in account_rows:
        source_account_id = blank_to_none(account_row.get("source_account_id")) or f"UNKNOWN-{len(transactions):04d}"
        account_balance = parse_decimal_safely(account_row.get("account_balance")) or Decimal("2500.00")
        rng = build_rng(source_account_id)
        transaction_count = choose_transaction_count(blank_to_none(account_row.get("account_status")), rng)
        running_balance = max(account_balance * Decimal(str(rng.uniform(0.75, 1.35))), Decimal("250.00")).quantize(Decimal("0.01"))
        transaction_timestamp = datetime.now() - timedelta(days=rng.randint(45, 120))

        account_transactions: list[dict] = []
        for txn_index in range(transaction_count):
            transaction_timestamp = transaction_timestamp + timedelta(
                days=rng.randint(0, 5),
                hours=rng.randint(1, 18),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            transaction_row, running_balance = build_transaction_row(
                account_row=account_row,
                transaction_sequence=len(transactions) + len(account_transactions) + 1,
                running_balance=running_balance,
                transaction_timestamp=transaction_timestamp,
                txn_index=txn_index,
            )
            account_transactions.append(transaction_row)
        transactions.extend(account_transactions)

    return transactions


def generate_invalid_transactions(valid_transactions: list[dict]) -> list[dict]:
    if len(valid_transactions) < INVALID_TRANSACTION_COUNT:
        raise ValueError("Not enough valid transactions to derive invalid examples.")

    reference_ids = [row["source_transaction_id"] for row in valid_transactions[:4]]
    today = datetime.now()

    invalid_transactions = [
        {**valid_transactions[0], "source_transaction_id": ""},
        {**valid_transactions[1], "source_transaction_id": f" {valid_transactions[1]['source_transaction_id']} "},
        {**valid_transactions[2], "source_transaction_id": reference_ids[0]},
        {**valid_transactions[3], "source_account_id": "", "account_number": ""},
        {**valid_transactions[4], "transaction_timestamp": "not-a-timestamp"},
        {**valid_transactions[5], "transaction_timestamp": (today + timedelta(days=2)).replace(microsecond=0).isoformat()},
        {**valid_transactions[6], "transaction_type": "airdrop"},
        {**valid_transactions[7], "transaction_channel": "sms"},
        {**valid_transactions[8], "transaction_direction": "sideways"},
        {**valid_transactions[9], "transaction_amount": "-150.00"},
        {**valid_transactions[10], "transaction_amount": "0.00"},
        {**valid_transactions[11], "transaction_currency": "rand"},
        {**valid_transactions[12], "counterparty_reference": ""},
        {**valid_transactions[13], "merchant_category": ""},
        {**valid_transactions[14], "transaction_status": "settled"},
        {**valid_transactions[15], "running_balance": "-10.00"},
        {**valid_transactions[16], "country_code": "south-africa"},
        {**valid_transactions[17], "city": "1234"},
        {**valid_transactions[18], "device_id": "x"},
        {
            **valid_transactions[19],
            "transaction_type": "salary",
            "transaction_direction": "debit",
        },
        {
            **valid_transactions[20],
            "transaction_type": "purchase",
            "transaction_direction": "credit",
        },
        {
            **valid_transactions[21],
            "transaction_channel": "mobile_app",
            "device_id": "",
        },
        {
            **valid_transactions[22],
            "is_international": "maybe",
        },
        {
            **valid_transactions[23],
            "source_account_id": "SRC-ACCT-999999",
        },
    ]

    return invalid_transactions


def generate_transactions() -> list[dict]:
    valid_transactions = generate_valid_transactions()
    invalid_transactions = generate_invalid_transactions(valid_transactions)
    return valid_transactions + invalid_transactions


def write_transactions_to_csv(transactions: list[dict]) -> None:
    OUTPUT_TRANSACTIONS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_TRANSACTIONS_FILE_PATH.open(mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(transactions)


def main() -> None:
    logger.info("Starting transaction generation")
    transactions = generate_transactions()
    write_transactions_to_csv(transactions)

    print(f"Generated transactions: {len(transactions)}")
    print(f"Deliberately invalid transactions: {INVALID_TRANSACTION_COUNT}")
    print(f"Output file: {OUTPUT_TRANSACTIONS_FILE_PATH}")
    logger.info(
        "Completed transaction generation: records=%s invalid_records=%s output=%s",
        len(transactions),
        INVALID_TRANSACTION_COUNT,
        OUTPUT_TRANSACTIONS_FILE_PATH,
    )


if __name__ == "__main__":
    main()
