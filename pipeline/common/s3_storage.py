import os
from io import BytesIO, StringIO
from pathlib import Path
from typing import Optional, Dict, Any, List

import boto3
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv


load_dotenv()


class S3StorageClient:
    """
    Reusable AWS S3 storage client for the Financial Intelligence Platform.

    Responsibilities:
    - Upload files to S3
    - Download files from S3 if needed
    - Read CSV files directly from S3
    - List S3 objects
    - Check object existence
    - Return object metadata

    PostgreSQL should store metadata and S3 references.
    S3 should store CSV files, reports, logs, and artifacts.
    """

    def __init__(self, region_name: Optional[str] = None):
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION")

        self.s3_client = boto3.client(
            "s3",
            region_name=self.region_name,
        )

    @staticmethod
    def clean_env_value(value: Optional[str]) -> str:
        """
        Clean common accidental .env mistakes:
        - leading/trailing spaces
        - trailing commas
        - wrapping quotes
        """
        if value is None:
            return ""

        return value.strip().strip(",").strip('"').strip("'")

    @staticmethod
    def build_s3_uri(bucket_name: str, object_key: str) -> str:
        return f"s3://{bucket_name}/{object_key}"

    def upload_file(
        self,
        local_file_path: str,
        bucket_name: str,
        object_key: str,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Upload a local file to S3.

        Returns:
            s3://bucket/object_key
        """
        bucket_name = self.clean_env_value(bucket_name)
        local_path = Path(local_file_path)

        if not local_path.exists():
            raise FileNotFoundError(f"Local file does not exist: {local_file_path}")

        if not local_path.is_file():
            raise ValueError(f"Path is not a file: {local_file_path}")

        upload_args = extra_args or {}

        if upload_args:
            self.s3_client.upload_file(
                Filename=str(local_path),
                Bucket=bucket_name,
                Key=object_key,
                ExtraArgs=upload_args,
            )
        else:
            self.s3_client.upload_file(
                Filename=str(local_path),
                Bucket=bucket_name,
                Key=object_key,
            )

        return self.build_s3_uri(bucket_name, object_key)

    def download_file(
        self,
        bucket_name: str,
        object_key: str,
        local_file_path: str,
    ) -> str:
        """
        Download an S3 object into a local file path.

        This is useful as a fallback for very large files or debugging,
        but the preferred ingestion path is reading directly from S3.
        """
        bucket_name = self.clean_env_value(bucket_name)

        local_path = Path(local_file_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        self.s3_client.download_file(
            Bucket=bucket_name,
            Key=object_key,
            Filename=str(local_path),
        )

        return str(local_path)

    def get_object_bytes(
        self,
        bucket_name: str,
        object_key: str,
    ) -> bytes:
        """
        Read an S3 object as raw bytes.
        """
        bucket_name = self.clean_env_value(bucket_name)

        response = self.s3_client.get_object(
            Bucket=bucket_name,
            Key=object_key,
        )

        return response["Body"].read()

    def get_object_text(
        self,
        bucket_name: str,
        object_key: str,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read an S3 object as text.
        """
        file_bytes = self.get_object_bytes(
            bucket_name=bucket_name,
            object_key=object_key,
        )

        return file_bytes.decode(encoding)

    def read_csv_as_dataframe(
        self,
        bucket_name: str,
        object_key: str,
        **read_csv_kwargs,
    ) -> pd.DataFrame:
        """
        Read a CSV file directly from S3 into a pandas DataFrame.

        Example:
            df = storage.read_csv_as_dataframe(
                bucket_name="my-bucket",
                object_key="customers/customers.csv"
            )
        """
        bucket_name = self.clean_env_value(bucket_name)

        response = self.s3_client.get_object(
            Bucket=bucket_name,
            Key=object_key,
        )

        return pd.read_csv(response["Body"], **read_csv_kwargs)

    def read_csv_as_records(self, bucket_name: str, object_key: str,**read_csv_kwargs) -> List[Dict[Any, Any]]:
        """
        Read a CSV file directly from S3 and return a list of dictionaries.

        This is useful for ingestion scripts that insert rows one-by-one
        or batch insert dictionaries.
        """
        df = self.read_csv_as_dataframe(
            bucket_name=bucket_name,
            object_key=object_key,
            **read_csv_kwargs,
        )

        return df.to_dict(orient="records")

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = "",
        max_keys: int = 100,
    ) -> List:
        """
        List object keys from an S3 bucket under a prefix.
        """
        bucket_name = self.clean_env_value(bucket_name)

        response = self.s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=max_keys,
        )

        contents = response.get("Contents", [])

        return [item["Key"] for item in contents]

    def object_exists(
        self,
        bucket_name: str,
        object_key: str,
    ) -> bool:
        """
        Check whether an S3 object exists.
        """
        bucket_name = self.clean_env_value(bucket_name)

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

    def get_object_metadata(
        self,
        bucket_name: str,
        object_key: str,
    ) -> Dict[str, Any]:
        """
        Return object metadata and basic S3 object information.
        """
        bucket_name = self.clean_env_value(bucket_name)

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