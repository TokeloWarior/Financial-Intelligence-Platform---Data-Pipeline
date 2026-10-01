from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pipeline.common.pipeline_logging import logger
from pipeline.common.s3_storage import S3StorageClient
from pipeline.common.synthetic_pipeline_registry import (
    SyntheticDatasetDefinition,
    list_synthetic_dataset_definitions,
)


def count_csv_records(file_path: Path) -> int:
    with file_path.open(mode="r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return sum(1 for _ in reader)


def build_date_partitioned_object_key(
    entity: str,
    file_name: str,
    uploaded_at: datetime,
) -> str:
    return (
        f"{entity}/"
        f"year={uploaded_at:%Y}/"
        f"month={uploaded_at:%m}/"
        f"day={uploaded_at:%d}/"
        f"{file_name}"
    )


def upload_synthetic_file(
    definition: SyntheticDatasetDefinition,
    storage: S3StorageClient | None = None,
    uploaded_at: datetime | None = None,
) -> dict:
    logger.info("Starting synthetic file upload: entity=%s", definition.entity)
    storage = storage or S3StorageClient()
    uploaded_at = uploaded_at or datetime.now(timezone.utc)

    bucket_name = S3StorageClient.clean_env_value(
        os.getenv(definition.upload_bucket_env_var)
    )

    if not bucket_name:
        raise ValueError(
            f"{definition.upload_bucket_env_var} is missing from the environment."
        )

    local_path = definition.local_file_path

    if not local_path.exists():
        raise FileNotFoundError(
            f"Synthetic file not found for {definition.entity}: {local_path}"
        )

    object_key = build_date_partitioned_object_key(
        entity=definition.upload_prefix,
        file_name=local_path.name,
        uploaded_at=uploaded_at,
    )
    s3_uri = storage.upload_file(
        local_file_path=str(local_path),
        bucket_name=bucket_name,
        object_key=object_key,
    )

    result = {
        "entity": definition.entity,
        "local_path": str(local_path),
        "bucket": bucket_name,
        "object_key": object_key,
        "s3_uri": s3_uri,
        "uploaded_at": uploaded_at.isoformat(),
        "record_count": count_csv_records(local_path),
    }
    logger.info(
        "Completed synthetic file upload: entity=%s records=%s s3_uri=%s",
        definition.entity,
        result["record_count"],
        result["s3_uri"],
    )
    return result


def upload_synthetic_files(entities: list[str] | None = None) -> list[dict]:
    storage = S3StorageClient()
    uploaded_at = datetime.now(timezone.utc)
    definitions = list_synthetic_dataset_definitions(entities=entities)

    return [
        upload_synthetic_file(
            definition=definition,
            storage=storage,
            uploaded_at=uploaded_at,
        )
        for definition in definitions
    ]


def main() -> None:
    upload_results = upload_synthetic_files()
    print(json.dumps(upload_results, indent=2))


if __name__ == "__main__":
    main()
