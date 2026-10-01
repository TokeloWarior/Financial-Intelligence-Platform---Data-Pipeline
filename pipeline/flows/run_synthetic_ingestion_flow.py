from __future__ import annotations

import importlib
from pathlib import Path

from prefect import flow, task

from pipeline.common.pipeline_logging import logger
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
    logger.info("Starting synthetic generation: entity=%s", definition.entity)
    generator = load_callable(definition.generator_callable)
    generator()
    logger.info("Completed synthetic generation: entity=%s", definition.entity)
    return definition.entity


@task
def upload_generated_datasets(entities: list[str]) -> list[dict]:
    logger.info("Starting S3 upload: entities=%s", ",".join(entities))
    upload_results = upload_synthetic_files(entities=entities)
    logger.info("Completed S3 upload: files=%s", len(upload_results))
    return upload_results


@task
def ingest_dataset_from_s3(definition: SyntheticDatasetDefinition, upload_result: dict) -> None:
    logger.info(
        "Starting raw ingestion: entity=%s s3_uri=%s",
        definition.entity,
        upload_result["s3_uri"],
    )
    ingestion_callable = load_callable(definition.ingestion_callable)
    ingestion_callable(
        bucket_name=upload_result["bucket"],
        object_key=upload_result["object_key"],
    )
    logger.info("Completed raw ingestion: entity=%s", definition.entity)


@task
def run_cleaning_step(definition: SyntheticDatasetDefinition) -> None:
    if definition.cleaning_callable is None:
        logger.info("Skipping cleaning: entity=%s reason=not_configured", definition.entity)
        return

    logger.info("Starting cleaning: entity=%s", definition.entity)
    cleaning_callable = load_callable(definition.cleaning_callable)
    cleaning_callable()
    logger.info("Completed cleaning: entity=%s", definition.entity)


@task
def run_data_quality_step(definition: SyntheticDatasetDefinition) -> None:
    if definition.dq_callable is None:
        logger.info("Skipping data quality: entity=%s reason=not_configured", definition.entity)
        return

    logger.info("Starting data quality: entity=%s", definition.entity)
    dq_callable = load_callable(definition.dq_callable)
    dq_callable()
    logger.info("Completed data quality: entity=%s", definition.entity)


@task
def cleanup_local_synthetic_files(upload_results: list[dict]) -> None:
    logger.info("Starting local file cleanup: files=%s", len(upload_results))
    for upload_result in upload_results:
        local_path = Path(upload_result["local_path"])

        if local_path.exists():
            local_path.unlink()
            logger.info("Deleted local synthetic file: path=%s", local_path)

    logger.info("Completed local file cleanup")


@flow(name="run-synthetic-ingestion-flow")
def run_synthetic_ingestion_flow(
    entities: list[str] | None = None,
    cleanup_local_files: bool = True,
) -> dict:
    definitions = list_synthetic_dataset_definitions(entities=entities)
    logger.info(
        "Pipeline run started: entities=%s cleanup_local_files=%s",
        ",".join(definition.entity for definition in definitions),
        cleanup_local_files,
    )

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

    result = {
        "entities": [definition.entity for definition in definitions],
        "uploaded_files": upload_results,
        "cleanup_local_files": cleanup_local_files,
    }
    logger.info("Pipeline run completed: entities=%s", ",".join(result["entities"]))
    return result


if __name__ == "__main__":
    run_synthetic_ingestion_flow()
