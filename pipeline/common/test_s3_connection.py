import os

from dotenv import load_dotenv

from pipeline.common.s3_storage import S3StorageClient


load_dotenv()


def main():
    bucket_name = os.getenv("S3_SYNTHETIC_DATA_BUCKET")

    if not bucket_name:
        raise ValueError("S3_SYNTHETIC_DATA_BUCKET is missing from .env")

    storage = S3StorageClient()

    print(f"Testing S3 access for bucket: {bucket_name}")

    objects = storage.list_objects(
        bucket_name=bucket_name,
        prefix="",
        max_keys=10,
    )

    print("Connection successful.")
    print(f"Objects found: {len(objects)}")

    for object_key in objects:
        print(f"- {object_key}")


if __name__ == "__main__":
    main()