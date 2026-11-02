"""MinIO client utilities for Report Service

Handles:
- File upload/download with presigned URLs
- Bucket management
"""

import os
import logging
from datetime import timedelta
from typing import Optional
from io import BytesIO
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

# MinIO configuration from environment variables
# These must be set in .env file - see .env.example
MINIO_INTERNAL_ENDPOINT = os.getenv("MINIO_INTERNAL_ENDPOINT")
MINIO_EXTERNAL_ENDPOINT = os.getenv("MINIO_EXTERNAL_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD")
MINIO_BUCKET = os.getenv("MINIO_BUCKET")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Validate required environment variables
def _validate_minio_config():
    """Validate that required MinIO environment variables are set"""
    required_vars = {
        "MINIO_INTERNAL_ENDPOINT": MINIO_INTERNAL_ENDPOINT,
        "MINIO_EXTERNAL_ENDPOINT": MINIO_EXTERNAL_ENDPOINT,
        "MINIO_ROOT_USER": MINIO_ACCESS_KEY,
        "MINIO_ROOT_PASSWORD": MINIO_SECRET_KEY,
        "MINIO_BUCKET": MINIO_BUCKET,
    }
    missing = [name for name, value in required_vars.items() if not value]
    if missing:
        logger.warning(f"Missing MinIO environment variables: {', '.join(missing)}. Check your .env file.")
    return len(missing) == 0

# Log configuration status at import time
if not _validate_minio_config():
    logger.warning("MinIO may not work correctly due to missing configuration")

# Presigned URL expiry times
UPLOAD_URL_EXPIRY = timedelta(hours=1)  # 1 hour for upload
DOWNLOAD_URL_EXPIRY = timedelta(hours=24)  # 24 hours for download


def get_minio_client() -> Minio:
    """Get MinIO client instance for internal operations (server-side)"""
    if not MINIO_INTERNAL_ENDPOINT or not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        raise ValueError("MinIO configuration is incomplete. Check environment variables.")
    client = Minio(
        MINIO_INTERNAL_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    return client


def get_presigned_client() -> Minio:
    """Get MinIO client for presigned URL generation (external access)
    
    Uses MINIO_EXTERNAL_ENDPOINT so the signature includes the correct hostname
    that clients will access. This client is ONLY used for generating presigned URLs,
    not for actual MinIO operations (bucket/object management).
    
    Note: region is set explicitly to 'us-east-1' to skip bucket location lookup.
    """
    if not MINIO_EXTERNAL_ENDPOINT or not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        raise ValueError("MinIO configuration is incomplete. Check environment variables.")
    client = Minio(
        MINIO_EXTERNAL_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
        region="us-east-1"
    )
    return client


def is_minio_available() -> bool:
    """Check if MinIO server is reachable"""
    try:
        client = get_minio_client()
        client.list_buckets()
        return True
    except Exception as e:
        logger.warning(f"MinIO not available: {e}")
        return False


def ensure_bucket_exists(client: Minio, bucket_name: str = MINIO_BUCKET) -> bool:
    """Ensure the bucket exists, create if not"""
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"Created MinIO bucket: {bucket_name}")
        return True
    except S3Error as e:
        logger.error(f"Failed to ensure bucket exists: {e}")
        return False


def generate_upload_url(
    filename: str,
    content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
) -> dict:
    """Generate presigned URL for uploading a file
    
    Args:
        filename: Original filename
        content_type: MIME type of the file
        
    Returns:
        Dict with upload_url, object_name, and expiry info
    """
    from datetime import datetime
    
    # Use internal client for bucket management
    internal_client = get_minio_client()
    ensure_bucket_exists(internal_client)
    
    # Use presigned client for URL generation (with external endpoint)
    presigned_client = get_presigned_client()
    
    # Use original filename with timestamp prefix for uniqueness
    # Format: uploads/YYYYMMDD_HHMMSS_originalfilename.ext
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize filename (remove special chars that might cause issues)
    safe_filename = "".join(c if c.isalnum() or c in '._-' else '_' for c in filename)
    object_name = f"uploads/{timestamp}_{safe_filename}"
    
    try:
        # Generate presigned PUT URL with external endpoint
        # Note: presigned_put_object only generates a signed URL, doesn't need connectivity
        upload_url = presigned_client.presigned_put_object(
            MINIO_BUCKET,
            object_name,
            expires=UPLOAD_URL_EXPIRY
        )
        
        logger.info(f"Generated upload URL for: {object_name} (external: {MINIO_EXTERNAL_ENDPOINT})")
        
        return {
            "upload_url": upload_url,
            "object_name": object_name,
            "bucket": MINIO_BUCKET,
            "expires_in_seconds": int(UPLOAD_URL_EXPIRY.total_seconds()),
            "content_type": content_type
        }
    except S3Error as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise


def generate_download_url(object_name: str) -> str:
    """Generate presigned URL for downloading a file
    
    Args:
        object_name: Object name in MinIO
        
    Returns:
        Presigned download URL
    """
    # Use presigned client for URL generation (with external endpoint)
    presigned_client = get_presigned_client()
    
    try:
        download_url = presigned_client.presigned_get_object(
            MINIO_BUCKET,
            object_name,
            expires=DOWNLOAD_URL_EXPIRY
        )
        
        logger.info(f"Generated download URL for: {object_name} (external: {MINIO_EXTERNAL_ENDPOINT})")
        return download_url
    except S3Error as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise


def download_file(object_name: str) -> bytes:
    """Download file content from MinIO
    
    Args:
        object_name: Object name in MinIO
        
    Returns:
        File content as bytes
    """
    client = get_minio_client()
    
    try:
        response = client.get_object(MINIO_BUCKET, object_name)
        content = response.read()
        response.close()
        response.release_conn()
        
        logger.info(f"Downloaded file from MinIO: {object_name}, size: {len(content)} bytes")
        return content
    except S3Error as e:
        logger.error(f"Failed to download file: {e}")
        raise


def upload_file(
    content: bytes,
    object_name: str,
    content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
) -> str:
    """Upload file content to MinIO
    
    Args:
        content: File content as bytes
        object_name: Object name in MinIO
        content_type: MIME type of the file
        
    Returns:
        Object name of uploaded file
    """
    client = get_minio_client()
    ensure_bucket_exists(client)
    
    try:
        client.put_object(
            MINIO_BUCKET,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type
        )
        
        logger.info(f"Uploaded file to MinIO: {object_name}, size: {len(content)} bytes")
        return object_name
    except S3Error as e:
        logger.error(f"Failed to upload file: {e}")
        raise


def upload_result_file(
    content: bytes,
    original_object_name: str,
    suffix: str = "_analysis"
) -> dict:
    """Upload result file to MinIO and generate download URL
    
    Args:
        content: File content as bytes
        original_object_name: Original uploaded file's object name (e.g., uploads/20250114_123456_report.xlsb)
        suffix: Suffix to add to filename
        
    Returns:
        Dict with object_name and download_url
    """
    # Generate result object name based on original
    # Original: uploads/20250114_123456_report.xlsb
    # Result:   results/20250114_123456_report_analysis.xlsx
    base_name = os.path.splitext(original_object_name)[0]  # uploads/20250114_123456_report
    result_object_name = f"{base_name}{suffix}.xlsx"  # uploads/20250114_123456_report_analysis.xlsx
    # Change path from uploads/ to results/
    result_object_name = result_object_name.replace("uploads/", "results/")
    
    # Upload result file
    upload_file(content, result_object_name)
    
    # Generate download URL
    download_url = generate_download_url(result_object_name)
    
    return {
        "object_name": result_object_name,
        "download_url": download_url,
        "expires_in_seconds": int(DOWNLOAD_URL_EXPIRY.total_seconds())
    }


def check_file_exists(object_name: str) -> bool:
    """Check if a file exists in MinIO
    
    Args:
        object_name: Object name in MinIO
        
    Returns:
        True if file exists, False otherwise
    """
    client = get_minio_client()
    
    try:
        client.stat_object(MINIO_BUCKET, object_name)
        return True
    except S3Error as e:
        if e.code == "NoSuchKey":
            return False
        raise


def delete_file(object_name: str) -> bool:
    """Delete a file from MinIO
    
    Args:
        object_name: Object name in MinIO
        
    Returns:
        True if deleted successfully
    """
    client = get_minio_client()
    
    try:
        client.remove_object(MINIO_BUCKET, object_name)
        logger.info(f"Deleted file from MinIO: {object_name}")
        return True
    except S3Error as e:
        logger.error(f"Failed to delete file: {e}")
        return False

