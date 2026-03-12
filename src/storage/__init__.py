"""
Storage module for S3/MinIO file operations.

Provides S3Client for uploading and downloading files to MinIO/S3.
"""

from src.storage.s3 import S3Client, get_s3_client

__all__ = ["S3Client", "get_s3_client"]
