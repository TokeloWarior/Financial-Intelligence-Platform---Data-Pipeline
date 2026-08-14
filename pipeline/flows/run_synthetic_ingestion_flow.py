from __future__ import annotations

import importlib
from pathlib import Path

from prefect import flow, task

from pipeline.common.synthetic_pipeline_registry import (
    SyntheticDatasetDefinition,
    list_synthetic_dataset_definitions,
)
from pipeline.ingestion.upload_synthetic_to_s3 import upload_synthetic_files


def load_callable(callable_path: str):
    module_name, function_name = callable_path.split(":", maxsplit=1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


@task
def generate_synthetic_dataset(definition: SyntheticDatasetDefinition) -> str:
    generator = load_callable(definition.generator_callable)
    generator()
    return definition.entity


@task
def upload_generated_datasets(entities: list[str]) -> list[dict]:
    return upload_synthetic_files(entities=entities)


@task
def ingest_dataset_from_s3(definition: SyntheticDatasetDefinition, upload_result: dict) -> None:
    ingestion_callable = load_callable(definition.ingestion_callable)
    ingestion_callable(
        bucket_name=upload_result["bucket"],
        object_key=upload_result["object_key"],
    )


@task
def run_cleaning_step(definition: SyntheticDatasetDefinition) -> None:
    if definition.cleaning_callable is None:
        return

    cleaning_callable = load_callable(definition.cleaning_callable)
    cleaning_callable()


@task
def run_data_quality_step(definition: SyntheticDatasetDefinition) -> None:
    if definition.dq_callable is None:
        return

    dq_callable = load_callable(definition.dq_callable)
    dq_callable()


@task
def cleanup_local_synthetic_files(upload_results: list[dict]) -> None:
    for upload_result in upload_results:
        local_path = Path(upload_result["local_path"])

        if local_path.exists():
            local_path.unlink()


@flow(name="run-synthetic-ingestion-flow")
def run_synthetic_ingestion_flow(
    entities: list[str] | None = None,
    cleanup_local_files: bool = True,
) -> dict:
    definitions = list_synthetic_dataset_definitions(entities=entities)

    for definition in definitions:
        generate_synthetic_dataset(definition)

    upload_results = upload_generated_datasets(
        [definition.entity for definition in definitions]
    )
    upload_results_by_entity = {
        upload_result["entity"]: upload_result for upload_result in upload_results
    }

    for definition in definitions:
        upload_result = upload_results_by_entity[definition.entity]
        ingest_dataset_from_s3(definition, upload_result)
        run_cleaning_step(definition)
        run_data_quality_step(definition)

    if cleanup_local_files:
        cleanup_local_synthetic_files(upload_results)

    return {
        "entities": [definition.entity for definition in definitions],
        "uploaded_files": upload_results,
        "cleanup_local_files": cleanup_local_files,
    }


if __name__ == "__main__":
    run_synthetic_ingestion_flow()
