"""
S3/MinIO storage client for file operations.

Provides S3Client class for uploading, downloading, and managing files
in MinIO or AWS S3 compatible storage.
"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError, EndpointConnectionError
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional
from uuid import UUID
import re
import time

from src.core.logging import get_logger, log_exception, log_performance
from src.core.exceptions import FileStorageError
from src.core.config import Settings


# Module logger
storage_logger = get_logger("debtfund.storage")
logger = storage_logger


class S3Client:
    """
    S3/MinIO storage client for file operations.

    Manages file uploads, downloads, and lifecycle operations with MinIO/S3.
    Follows DebtFund error handling and logging patterns.

    Attributes:
        endpoint: S3/MinIO endpoint URL
        access_key: S3 access key
        secret_key: S3 secret key
        bucket_name: Default bucket for operations
        s3_client: boto3 S3 client instance

    Example:
        >>> from src.storage.s3 import get_s3_client
        >>> from src.core.config import get_settings
        >>>
        >>> settings = get_settings()
        >>> s3_client = get_s3_client(settings)
        >>>
        >>> # Upload file
        >>> s3_key = s3_client.upload_file(
        ...     file_bytes=file_data,
        ...     s3_key="uploads/2024/02/file123.xlsx"
        ... )
        >>>
        >>> # Download file
        >>> file_bytes = s3_client.download_file("uploads/2024/02/file123.xlsx")
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        verify_ssl: bool = True
    ) -> None:
        """
        Initialize S3 client.

        Args:
            endpoint: S3/MinIO endpoint URL (e.g., "http://localhost:9000")
            access_key: S3 access key
            secret_key: S3 secret key
            bucket_name: Default bucket name
            verify_ssl: Whether to verify SSL certificates (False for local MinIO)

        Raises:
            FileStorageError: If client initialization fails
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.verify_ssl = verify_ssl

        try:
            # Configure retries with exponential backoff
            retry_config = Config(
                retries={
                    'max_attempts': 3,
                    'mode': 'adaptive'  # Exponential backoff
                }
            )

            # Initialize boto3 S3 client
            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                verify=verify_ssl,
                config=retry_config
            )

            logger.info(
                f"S3Client initialized - endpoint: {endpoint}, "
                f"bucket: {bucket_name}, verify_ssl: {verify_ssl}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize S3Client: {str(e)}")
            raise FileStorageError(
                f"Failed to initialize S3 client: {str(e)}",
                bucket=bucket_name
            )

    def upload_file(
        self,
        file_bytes: bytes,
        s3_key: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload file bytes to S3/MinIO.

        Args:
            file_bytes: File content as bytes
            s3_key: S3 object key (path in bucket)
            content_type: MIME type (default: Excel XLSX)
            metadata: Optional metadata dictionary

        Returns:
            str: S3 key of uploaded file

        Raises:
            FileStorageError: If upload fails (connection, bucket not found, etc.)

        Example:
            >>> s3_key = client.upload_file(
            ...     file_bytes=file_data,
            ...     s3_key="uploads/2024/02/file123.xlsx",
            ...     metadata={"file_id": "abc-123", "filename": "model.xlsx"}
            ... )
        """
        start_time = time.time()

        try:
            # Upload file using BytesIO
            file_obj = BytesIO(file_bytes)

            # Prepare upload arguments
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
                'Body': file_obj,
                'ContentType': content_type
            }

            # Add metadata if provided
            if metadata:
                # S3 metadata keys must be lowercase
                upload_args['Metadata'] = {k.lower(): str(v) for k, v in metadata.items()}

            # Perform upload
            self.s3_client.put_object(**upload_args)

            duration = time.time() - start_time

            logger.info(
                f"File uploaded: {s3_key}, size: {len(file_bytes)} bytes, "
                f"bucket: {self.bucket_name}"
            )

            log_performance(
                logger,
                "upload_file",
                duration,
                {"size_bytes": len(file_bytes), "s3_key": s3_key}
            )

            return s3_key

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            if error_code == 'NoSuchBucket':
                logger.error(f"Bucket not found: {self.bucket_name}")
                raise FileStorageError(
                    f"Bucket '{self.bucket_name}' not found",
                    bucket=self.bucket_name,
                    key=s3_key
                )
            else:
                logger.error(f"S3 upload failed: {str(e)}")
                raise FileStorageError(
                    f"Failed to upload file: {str(e)}",
                    bucket=self.bucket_name,
                    key=s3_key
                )

        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"S3 credentials error: {str(e)}")
            raise FileStorageError(
                "Invalid S3 credentials",
                bucket=self.bucket_name
            )

        except EndpointConnectionError as e:
            logger.error(f"Cannot connect to S3: {str(e)}")
            raise FileStorageError(
                f"Cannot connect to S3 endpoint: {self.endpoint}",
                bucket=self.bucket_name
            )

        except Exception as e:
            logger.error(f"Unexpected storage error during upload: {str(e)}")
            log_exception(logger, e, {"s3_key": s3_key, "bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected storage error: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )

    def download_file(self, s3_key: str) -> bytes:
        """
        Download file from S3/MinIO.

        Args:
            s3_key: S3 object key (path in bucket)

        Returns:
            bytes: File content as bytes

        Raises:
            FileStorageError: If download fails (not found, connection error, etc.)

        Example:
            >>> file_bytes = client.download_file("uploads/2024/02/file123.xlsx")
        """
        start_time = time.time()

        try:
            # Download file
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )

            # Read file bytes
            file_bytes = response['Body'].read()

            duration = time.time() - start_time

            logger.info(
                f"File downloaded: {s3_key}, size: {len(file_bytes)} bytes, "
                f"bucket: {self.bucket_name}"
            )

            log_performance(
                logger,
                "download_file",
                duration,
                {"size_bytes": len(file_bytes), "s3_key": s3_key}
            )

            return file_bytes

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            if error_code == '404' or error_code == 'NoSuchKey':
                logger.error(f"File not found: {s3_key}")
                raise FileStorageError(
                    f"File not found: {s3_key}",
                    bucket=self.bucket_name,
                    key=s3_key
                )
            elif error_code == 'NoSuchBucket':
                logger.error(f"Bucket not found: {self.bucket_name}")
                raise FileStorageError(
                    f"Bucket '{self.bucket_name}' not found",
                    bucket=self.bucket_name,
                    key=s3_key
                )
            else:
                logger.error(f"S3 download failed: {str(e)}")
                raise FileStorageError(
                    f"Failed to download file: {str(e)}",
                    bucket=self.bucket_name,
                    key=s3_key
                )

        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"S3 credentials error: {str(e)}")
            raise FileStorageError(
                "Invalid S3 credentials",
                bucket=self.bucket_name
            )

        except EndpointConnectionError as e:
            logger.error(f"Cannot connect to S3: {str(e)}")
            raise FileStorageError(
                f"Cannot connect to S3 endpoint: {self.endpoint}",
                bucket=self.bucket_name
            )

        except Exception as e:
            logger.error(f"Unexpected storage error during download: {str(e)}")
            log_exception(logger, e, {"s3_key": s3_key, "bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected storage error: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )

    def generate_s3_key(
        self,
        file_id: UUID,
        filename: str,
        prefix: str = "uploads"
    ) -> str:
        """
        Generate standardized S3 key for file storage.

        Uses pattern: {prefix}/{year}/{month}/{file_id}_{filename}

        Args:
            file_id: File UUID
            filename: Original filename
            prefix: Key prefix (default: "uploads")

        Returns:
            str: Generated S3 key

        Example:
            >>> key = client.generate_s3_key(
            ...     file_id=UUID("abc-123-def"),
            ...     filename="model.xlsx"
            ... )
            "uploads/2024/02/abc-123-def_model.xlsx"
        """
        # Get current date for partitioning
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")

        # Sanitize filename (keep alphanumeric, dash, underscore, dot)
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

        # Build key with file_id for uniqueness
        s3_key = f"{prefix}/{year}/{month}/{file_id}_{safe_filename}"

        logger.debug(f"Generated S3 key: {s3_key} for file_id: {file_id}")

        return s3_key

    def ensure_bucket_exists(self) -> None:
        """
        Ensure the configured bucket exists, create if needed.

        Should be called on application startup.

        Raises:
            FileStorageError: If bucket creation fails
        """
        try:
            # Try to get bucket metadata to check if it exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket exists: {self.bucket_name}")

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            if error_code == '404' or error_code == 'NoSuchBucket':
                # Bucket doesn't exist, create it
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Bucket created: {self.bucket_name}")

                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {str(create_error)}")
                    raise FileStorageError(
                        f"Failed to create bucket '{self.bucket_name}': {str(create_error)}",
                        bucket=self.bucket_name
                    )
            else:
                logger.error(f"Failed to check bucket: {str(e)}")
                raise FileStorageError(
                    f"Failed to check bucket '{self.bucket_name}': {str(e)}",
                    bucket=self.bucket_name
                )

        except (NoCredentialsError, PartialCredentialsError) as e:
            logger.error(f"S3 credentials error: {str(e)}")
            raise FileStorageError(
                "Invalid S3 credentials",
                bucket=self.bucket_name
            )

        except EndpointConnectionError as e:
            logger.error(f"Cannot connect to S3: {str(e)}")
            raise FileStorageError(
                f"Cannot connect to S3 endpoint: {self.endpoint}",
                bucket=self.bucket_name
            )

        except Exception as e:
            logger.error(f"Unexpected error checking bucket: {str(e)}")
            log_exception(logger, e, {"bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected error: {str(e)}",
                bucket=self.bucket_name
            )

    def file_exists(self, s3_key: str) -> bool:
        """
        Check if file exists in S3/MinIO.

        Args:
            s3_key: S3 object key

        Returns:
            bool: True if file exists, False otherwise

        Raises:
            FileStorageError: If check operation fails
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            logger.debug(f"File exists: {s3_key}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            if error_code == '404' or error_code == 'NoSuchKey':
                logger.debug(f"File does not exist: {s3_key}")
                return False
            else:
                logger.error(f"Failed to check file existence: {str(e)}")
                raise FileStorageError(
                    f"Failed to check if file exists: {str(e)}",
                    bucket=self.bucket_name,
                    key=s3_key
                )

        except Exception as e:
            logger.error(f"Unexpected error checking file existence: {str(e)}")
            log_exception(logger, e, {"s3_key": s3_key, "bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected error: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )

    def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3/MinIO.

        Args:
            s3_key: S3 object key

        Returns:
            bool: True if deleted, False if file didn't exist

        Raises:
            FileStorageError: If deletion fails
        """
        try:
            # Check if file exists first
            if not self.file_exists(s3_key):
                logger.warning(f"Cannot delete file that doesn't exist: {s3_key}")
                return False

            # Delete the file
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.info(f"File deleted: {s3_key}, bucket: {self.bucket_name}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete file: {str(e)}")
            raise FileStorageError(
                f"Failed to delete file: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )

        except Exception as e:
            logger.error(f"Unexpected error during deletion: {str(e)}")
            log_exception(logger, e, {"s3_key": s3_key, "bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected error: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )

    def get_file_metadata(self, s3_key: str) -> Dict[str, Any]:
        """
        Get file metadata from S3/MinIO.

        Args:
            s3_key: S3 object key

        Returns:
            dict: Metadata including size, last_modified, content_type, custom metadata

        Raises:
            FileStorageError: If metadata retrieval fails
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)

            metadata = {
                'size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType', 'unknown'),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {})
            }

            logger.debug(f"Retrieved metadata for: {s3_key}")
            return metadata

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')

            if error_code == '404' or error_code == 'NoSuchKey':
                logger.error(f"File not found: {s3_key}")
                raise FileStorageError(
                    f"File not found: {s3_key}",
                    bucket=self.bucket_name,
                    key=s3_key
                )
            else:
                logger.error(f"Failed to get metadata: {str(e)}")
                raise FileStorageError(
                    f"Failed to get file metadata: {str(e)}",
                    bucket=self.bucket_name,
                    key=s3_key
                )

        except Exception as e:
            logger.error(f"Unexpected error getting metadata: {str(e)}")
            log_exception(logger, e, {"s3_key": s3_key, "bucket": self.bucket_name})
            raise FileStorageError(
                f"Unexpected error: {str(e)}",
                bucket=self.bucket_name,
                key=s3_key
            )


# ============================================================================
# Factory Function for Dependency Injection
# ============================================================================

def get_s3_client(settings: Settings = None) -> S3Client:
    """
    Factory function to create S3Client with settings.

    Args:
        settings: Settings instance (uses singleton if None)

    Returns:
        S3Client: Configured S3 client

    Example (FastAPI endpoint):
        >>> from src.core.config import get_settings
        >>> from src.storage.s3 import get_s3_client
        >>>
        >>> settings = get_settings()
        >>> s3_client = get_s3_client(settings)
        >>>
        >>> # Or let it use the singleton:
        >>> s3_client = get_s3_client()
    """
    if settings is None:
        from src.core.config import get_settings
        settings = get_settings()

    return S3Client(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket_name=settings.s3_bucket,
        verify_ssl=settings.s3_verify_ssl  # Use configured value (secure by default)
    )
