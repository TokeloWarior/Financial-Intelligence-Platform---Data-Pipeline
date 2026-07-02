import csv
import random
from datetime import date, timedelta
from pathlib import Path


OUTPUT_PATH = Path("data/synthetic/customers.csv")
CUSTOMER_COUNT = 300
INVALID_CUSTOMER_COUNT = 30
RANDOM_SEED = 42


REGION_CITY_MAP = {
    "Gauteng": ["Johannesburg", "Pretoria", "Soweto", "Midrand", "Centurion"],
    "Western Cape": ["Cape Town", "Stellenbosch", "George", "Paarl", "Bellville"],
    "KwaZulu-Natal": ["Durban", "Pietermaritzburg", "Richards Bay", "Newcastle", "Umhlanga"],
    "Eastern Cape": ["Gqeberha", "East London", "Mthatha", "Queenstown", "Grahamstown"],
    "Free State": ["Bloemfontein", "Welkom", "Bethlehem", "Sasolburg", "Kroonstad"],
    "Limpopo": ["Polokwane", "Tzaneen", "Makhado", "Thohoyandou", "Lephalale"],
    "Mpumalanga": ["Mbombela", "Witbank", "Secunda", "Middelburg", "Ermelo"],
    "North West": ["Rustenburg", "Mahikeng", "Klerksdorp", "Potchefstroom", "Brits"],
    "Northern Cape": ["Kimberley", "Upington", "Springbok", "De Aar", "Kuruman"],
}


FIRST_NAMES = [
    "Thabo", "Lerato", "Anele", "Sipho", "Nomsa", "Kabelo", "Naledi", "Mpho",
    "Ayanda", "Karabo", "Zanele", "Sibusiso", "Lindiwe", "Neo", "Palesa",
]

LAST_NAMES = [
    "Mokoena", "Ndlovu", "Khumalo", "Dlamini", "Molefe", "Naidoo", "Pillay",
    "Botha", "Van Wyk", "Maseko", "Mabena", "Nkosi", "Mthembu", "Mahlangu",
]

COUNTRIES = [
    "South Africa",
    "Zimbabwe",
    "Botswana",
    "Lesotho",
    "Eswatini",
    "Namibia",
    "Mozambique",
]


VALID_CUSTOMER_TYPES = ["individual"]

VALID_GENDERS = ["female", "male", "other", "unknown"]

VALID_EMPLOYMENT_STATUSES = [
    "employed",
    "self_employed",
    "self-employed",
    "unemployed",
    "student",
    "retired",
]

VALID_INCOME_BANDS = [
    "0-4999",
    "5000-9999",
    "10000-19999",
    "20000-39999",
    "40000-79999",
    "80000+",
]

VALID_CUSTOMER_STATUSES = ["active", "inactive", "suspended", "closed"]

VALID_KYC_STATUSES = ["not_started", "pending", "verified", "failed", "expired"]

VALID_RISK_RATINGS = ["low", "medium", "high"]


FIELDNAMES = [
    "source_customer_id",
    "customer_type",
    "first_name",
    "last_name",
    "id_number",
    "passport_number",
    "country_of_birth",
    "primary_phone_number",
    "secondary_phone_number",
    "date_of_birth",
    "gender",
    "region",
    "city",
    "employment_status",
    "income_band",
    "customer_status",
    "onboarding_date",
    "kyc_status",
    "risk_rating",
]


def random_date_between(start_date: date, end_date: date) -> date:
    days_between = (end_date - start_date).days
    random_days = random.randint(0, days_between)

    return start_date + timedelta(days=random_days)


def generate_date_of_birth() -> date:
    today = date.today()

    oldest_birth_date = date(today.year - 75, today.month, today.day)
    youngest_birth_date = date(today.year - 18, today.month, today.day)

    return random_date_between(oldest_birth_date, youngest_birth_date)


def generate_onboarding_date(date_of_birth: date) -> date:
    eighteenth_birthday = date(
        date_of_birth.year + 18,
        date_of_birth.month,
        date_of_birth.day,
    )

    today = date.today()

    return random_date_between(eighteenth_birthday, today)


def generate_sa_id_number(date_of_birth: date, customer_number: int) -> str:
    """
    Generate a synthetic 13-digit South African-style ID number.

    This is synthetic test data only.
    """

    birth_part = date_of_birth.strftime("%y%m%d")
    sequence_part = f"{customer_number % 10000:04d}"
    citizenship_digit = "0"
    checksum_placeholder = f"{customer_number % 100:02d}"

    return f"{birth_part}{sequence_part}{citizenship_digit}{checksum_placeholder}"


def generate_passport_number(customer_number: int) -> str:
    """
    Generate a synthetic passport number.
    """

    return f"P{customer_number:08d}"


def generate_phone_number(customer_number: int) -> str:
    """
    Generate a synthetic South African mobile number in +27 format.
    """

    suffix = 1000000 + customer_number

    return f"+2782{suffix:07d}"


def choose_customer_status() -> str:
    return random.choices(
        VALID_CUSTOMER_STATUSES,
        weights=[70, 15, 10, 5],
        k=1,
    )[0]


def choose_kyc_status(customer_status: str) -> str:
    if customer_status == "active":
        return random.choices(
            VALID_KYC_STATUSES,
            weights=[2, 8, 85, 3, 2],
            k=1,
        )[0]

    if customer_status == "closed":
        return random.choices(
            VALID_KYC_STATUSES,
            weights=[5, 5, 70, 5, 15],
            k=1,
        )[0]

    return random.choices(
        VALID_KYC_STATUSES,
        weights=[10, 25, 45, 10, 10],
        k=1,
    )[0]


def choose_risk_rating(customer_status: str, kyc_status: str) -> str:
    if kyc_status in ("failed", "expired"):
        return random.choices(
            VALID_RISK_RATINGS,
            weights=[10, 35, 55],
            k=1,
        )[0]

    if customer_status == "suspended":
        return random.choices(
            VALID_RISK_RATINGS,
            weights=[10, 40, 50],
            k=1,
        )[0]

    return random.choices(
        VALID_RISK_RATINGS,
        weights=[60, 30, 10],
        k=1,
    )[0]


def generate_identity_fields(date_of_birth: date, customer_number: int) -> dict:
    """
    Generate either a South African ID number or a passport number.

    If country_of_birth is South Africa, we generate id_number.
    Otherwise, we generate passport_number.
    """

    country_of_birth = random.choices(
        COUNTRIES,
        weights=[85, 4, 3, 3, 2, 2, 1],
        k=1,
    )[0]

    if country_of_birth == "South Africa":
        return {
            "id_number": generate_sa_id_number(date_of_birth, customer_number),
            "passport_number": "",
            "country_of_birth": country_of_birth,
        }

    return {
        "id_number": "",
        "passport_number": generate_passport_number(customer_number),
        "country_of_birth": country_of_birth,
    }


def generate_valid_customer(customer_number: int) -> dict:
    source_customer_id = f"CUST-{customer_number:06d}"

    date_of_birth = generate_date_of_birth()
    onboarding_date = generate_onboarding_date(date_of_birth)

    region = random.choice(list(REGION_CITY_MAP.keys()))
    city = random.choice(REGION_CITY_MAP[region])

    customer_status = choose_customer_status()
    kyc_status = choose_kyc_status(customer_status)
    risk_rating = choose_risk_rating(customer_status, kyc_status)

    identity_fields = generate_identity_fields(date_of_birth, customer_number)

    return {
        "source_customer_id": source_customer_id,
        "customer_type": random.choice(VALID_CUSTOMER_TYPES),
        "first_name": random.choice(FIRST_NAMES),
        "last_name": random.choice(LAST_NAMES),
        "id_number": identity_fields["id_number"],
        "passport_number": identity_fields["passport_number"],
        "country_of_birth": identity_fields["country_of_birth"],
        "primary_phone_number": generate_phone_number(customer_number),
        "secondary_phone_number": "",
        "date_of_birth": date_of_birth.isoformat(),
        "gender": random.choice(VALID_GENDERS),
        "region": region,
        "city": city,
        "employment_status": random.choice(VALID_EMPLOYMENT_STATUSES),
        "income_band": random.choice(VALID_INCOME_BANDS),
        "customer_status": customer_status,
        "onboarding_date": onboarding_date.isoformat(),
        "kyc_status": kyc_status,
        "risk_rating": risk_rating,
    }


def generate_invalid_customers(start_customer_number: int) -> list[dict]:
    today = date.today()

    invalid_customers = [
        {
            **generate_valid_customer(start_customer_number),
            "source_customer_id": "",
        },
        {
            **generate_valid_customer(start_customer_number + 1),
            "customer_type": "vip_person",
        },
        {
            **generate_valid_customer(start_customer_number + 2),
            "date_of_birth": (today + timedelta(days=30)).isoformat(),
        },
        {
            **generate_valid_customer(start_customer_number + 3),
            "date_of_birth": date(today.year - 15, today.month, today.day).isoformat(),
        },
        {
            **generate_valid_customer(start_customer_number + 4),
            "region": "Atlantis",
            "city": "Poseidon City",
        },
        {
            **generate_valid_customer(start_customer_number + 5),
            "region": "",
        },
        {
            **generate_valid_customer(start_customer_number + 6),
            "income_band": "999999-1000000",
        },
        {
            **generate_valid_customer(start_customer_number + 7),
            "customer_status": "paused",
        },
        {
            **generate_valid_customer(start_customer_number + 8),
            "kyc_status": "approved",
        },
        {
            **generate_valid_customer(start_customer_number + 9),
            "risk_rating": "extreme",
        },
        {
            **generate_valid_customer(start_customer_number + 10),
            "onboarding_date": (today + timedelta(days=90)).isoformat(),
        },
        {
            **generate_valid_customer(start_customer_number + 11),
            "date_of_birth": date(today.year - 25, today.month, today.day).isoformat(),
            "onboarding_date": date(today.year - 10, today.month, today.day).isoformat(),
        },
        {
            **generate_valid_customer(start_customer_number + 12),
            "date_of_birth": "",
        },
        {
            **generate_valid_customer(start_customer_number + 13),
            "customer_status": "",
        },
        {
            **generate_valid_customer(start_customer_number + 14),
            "source_customer_id": "INVALID-ID-001",
        },
        {
            **generate_valid_customer(start_customer_number + 15),
            "source_customer_id": "CUST-000001",
        },
        {
            **generate_valid_customer(start_customer_number + 16),
            "employment_status": "gig_worker",
        },
        {
            **generate_valid_customer(start_customer_number + 17),
            "gender": "robot",
        },
        {
            **generate_valid_customer(start_customer_number + 18),
            "city": "",
        },
        {
            **generate_valid_customer(start_customer_number + 19),
            "date_of_birth": "not-a-date",
        },
        {
            **generate_valid_customer(start_customer_number + 20),
            "onboarding_date": "not-a-date",
        },
        {
            **generate_valid_customer(start_customer_number + 21),
            "source_customer_id": "CUST-ABCDEF",
        },
        {
            **generate_valid_customer(start_customer_number + 22),
            "income_band": "",
        },
        {
            **generate_valid_customer(start_customer_number + 23),
            "kyc_status": "",
        },
        {
            **generate_valid_customer(start_customer_number + 24),
            "risk_rating": "",
        },
        {
            **generate_valid_customer(start_customer_number + 25),
            "first_name": "",
        },
        {
            **generate_valid_customer(start_customer_number + 26),
            "last_name": "",
        },
        {
            **generate_valid_customer(start_customer_number + 27),
            "id_number": "",
            "passport_number": "",
        },
        {
            **generate_valid_customer(start_customer_number + 28),
            "primary_phone_number": "12345",
        },
        {
            **generate_valid_customer(start_customer_number + 29),
            "country_of_birth": "",
        },
    ]

    return invalid_customers


def generate_customers() -> list[dict]:
    random.seed(RANDOM_SEED)

    valid_customer_count = CUSTOMER_COUNT - INVALID_CUSTOMER_COUNT

    valid_customers = [
        generate_valid_customer(customer_number)
        for customer_number in range(1, valid_customer_count + 1)
    ]

    invalid_customers = generate_invalid_customers(valid_customer_count + 1)

    return valid_customers + invalid_customers


def write_customers_to_csv(customers: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open(mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)

        writer.writeheader()
        writer.writerows(customers)


def main() -> None:
    customers = generate_customers()
    write_customers_to_csv(customers)

    valid_customer_count = CUSTOMER_COUNT - INVALID_CUSTOMER_COUNT

    print(f"Generated customers: {len(customers)}")
    print(f"Expected mostly valid customers: {valid_customer_count}")
    print(f"Deliberately invalid customers: {INVALID_CUSTOMER_COUNT}")
    print(f"Output file: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
