from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyntheticDatasetDefinition:
    entity: str
    local_file_path: Path
    upload_bucket_env_var: str
    upload_prefix: str
    generator_callable: str
    ingestion_callable: str
    cleaning_callable: str | None = None
    dq_callable: str | None = None


SYNTHETIC_DATASET_DEFINITIONS: tuple[SyntheticDatasetDefinition, ...] = (
    SyntheticDatasetDefinition(
        entity="customers",
        local_file_path=Path("data/synthetic/customers.csv"),
        upload_bucket_env_var="S3_SYNTHETIC_DATA_BUCKET",
        upload_prefix="customers",
        generator_callable="pipeline.ingestion.generate_customers:main",
        ingestion_callable="pipeline.ingestion.ingest_raw_customers:ingest_raw_customers",
        cleaning_callable="pipeline.cleaning.clean_customers:clean_customers",
        dq_callable="pipeline.validation.customer_data_quality:run_customer_data_quality_checks",
    ),
    SyntheticDatasetDefinition(
        entity="accounts",
        local_file_path=Path("data/synthetic/accounts.csv"),
        upload_bucket_env_var="S3_SYNTHETIC_DATA_BUCKET",
        upload_prefix="accounts",
        generator_callable="pipeline.ingestion.generate_accounts:main",
        ingestion_callable="pipeline.ingestion.ingest_raw_accounts:ingest_raw_accounts",
        cleaning_callable="pipeline.cleaning.clean_accounts:clean_accounts",
    ),
    SyntheticDatasetDefinition(
        entity="transactions",
        local_file_path=Path("data/synthetic/transactions.csv"),
        upload_bucket_env_var="S3_SYNTHETIC_DATA_BUCKET",
        upload_prefix="transactions",
        generator_callable="pipeline.ingestion.generate_transactions:main",
        ingestion_callable="pipeline.ingestion.ingest_raw_transactions:ingest_raw_transactions",
        cleaning_callable="pipeline.cleaning.clean_transactions:clean_transactions",
        dq_callable="pipeline.validation.transaction_data_quality:run_transaction_data_quality_checks",
    ),
)


def list_synthetic_dataset_definitions(
    entities: list[str] | None = None,
) -> list[SyntheticDatasetDefinition]:
    if entities is None:
        return list(SYNTHETIC_DATASET_DEFINITIONS)

    requested_entities = {entity.strip() for entity in entities}
    definitions = [
        definition
        for definition in SYNTHETIC_DATASET_DEFINITIONS
        if definition.entity in requested_entities
    ]

    if len(definitions) != len(requested_entities):
        known_entities = {definition.entity for definition in SYNTHETIC_DATASET_DEFINITIONS}
        unknown_entities = sorted(requested_entities - known_entities)
        raise ValueError(f"Unknown synthetic entities requested: {unknown_entities}")

    return definitions


def get_synthetic_dataset_definition(entity: str) -> SyntheticDatasetDefinition:
    for definition in SYNTHETIC_DATASET_DEFINITIONS:
        if definition.entity == entity:
            return definition

    raise ValueError(f"Unknown synthetic entity: {entity}")
