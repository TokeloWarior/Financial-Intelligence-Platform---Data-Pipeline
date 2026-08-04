import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv


load_dotenv()


class S3StorageClient:
    """
    Reusable AWS S3 storage client for the Financial Intelligence Platform.

    This client is responsible for file/object storage only.
    PostgreSQL should store metadata and S3 references, not the actual files.
    """

    def __init__(self, region_name: Optional[str] = None):
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION")

        self.s3_client = boto3.client(
            "s3",
            region_name=self.region_name,
        )

    @staticmethod
    def build_s3_uri(bucket_name: str, object_key: str) -> str:
        return f"s3://{bucket_name}/{object_key}"

    def upload_file(self, local_file_path: str, bucket_name: str, object_key: str, extra_args: Optional[Dict[str, Any]] = None) -> str:
        """
        Upload a local file to S3.

        Returns:
            s3://bucket/object_key
        """
        local_path = Path(local_file_path)

        if not local_path.exists():
            raise FileNotFoundError(f"Local file does not exist: {local_file_path}")

        if not local_path.is_file():
            raise ValueError(f"Path is not a file: {local_file_path}")

        upload_args = extra_args or {}

        self.s3_client.upload_file(
            Filename=str(local_path),
            Bucket=bucket_name,
            Key=object_key,
            ExtraArgs=upload_args if upload_args else None,
        )

        return self.build_s3_uri(bucket_name, object_key)

    def download_file(self, bucket_name: str, object_key: str, local_file_path: str) -> str:
        """
        Download an S3 object into a local file path.

        Returns:
            local file path
        """
        local_path = Path(local_file_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        self.s3_client.download_file(
            Bucket=bucket_name,
            Key=object_key,
            Filename=str(local_path),
        )

        return str(local_path)

    def list_objects(self, bucket_name: str, prefix: str = "", max_keys: int = 100) -> List:
        """
        List object keys from an S3 bucket under a prefix.
        """
        response = self.s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=max_keys,
        )

        contents = response.get("Contents", [])

        return [item["Key"] for item in contents]

    def object_exists(self, bucket_name: str, object_key: str) -> bool:
        """
        Check whether an S3 object exists.
        """
        try:
            self.s3_client.head_object(
                Bucket=bucket_name,
                Key=object_key,
            )
            return True
        except ClientError as error:
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

            if status_code == 404:
                return False

            raise

    def get_object_metadata(self, bucket_name: str, object_key: str) -> Dict[str, Any]:
        """
        Return object metadata and basic S3 object information.
        """
        response = self.s3_client.head_object(
            Bucket=bucket_name,
            Key=object_key,
        )

        return {
            "content_length": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "last_modified": response.get("LastModified"),
            "etag": response.get("ETag"),
            "metadata": response.get("Metadata", {}),
        }