"""Shared Allas/S3 client factory for the demo API."""

import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def create_s3_client():
    """Create a boto3 S3 client configured for CSC Allas.

    Returns:
        Tuple of (s3_client, bucket_name).

    Raises:
        HTTPException: If required environment variables are missing.
    """
    bucket = os.getenv("ALLAS_BUCKET_NAME")
    endpoint = os.getenv("ALLAS_ENDPOINT_URL")
    access_key = os.getenv("ALLAS_ACCESS_KEY_ID")
    secret_key = os.getenv("ALLAS_SECRET_ACCESS_KEY")

    if not all([bucket, endpoint, access_key, secret_key]):
        raise HTTPException(status_code=503, detail="S3/Allas storage not configured")

    import boto3
    from botocore.config import Config as BotoConfig

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="regionOne",
        config=BotoConfig(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    return s3, bucket


def ensure_object_exists(s3, bucket: str, key: str, *, label: str) -> None:
    """Verify an S3 object exists, raising HTTPException(404) if not."""
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            logger.warning("Missing %s object in Allas: s3://%s/%s", label, bucket, key)
            raise HTTPException(
                status_code=404,
                detail=f"{label.capitalize()} media not found for video '{key.split('/')[1]}'",
            ) from exc
        raise


def generate_presigned_url(video_id: str, filename: str, *, label: str, expires_in: int = 900) -> dict:
    """Generate a presigned S3 URL for a video asset.

    Args:
        video_id: The video identifier.
        filename: The file name within the video's S3 prefix (e.g. "video.mp4").
        label: Human-readable label for error messages (e.g. "video", "thumbnail").
        expires_in: URL expiry in seconds (default 900 = 15 minutes).

    Returns:
        Dict with "url" and "expires_in" keys.
    """
    try:
        s3, bucket = create_s3_client()
        key = f"dental-demo/{video_id}/{filename}"
        ensure_object_exists(s3, bucket, key, label=label)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return {"url": url, "expires_in": expires_in}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate {label} URL: {e}") from e
