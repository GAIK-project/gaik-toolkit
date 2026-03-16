"""Demo API utilities."""

from .config import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    MAX_VISION_PAGES,
    get_api_config,
    validate_file_size,
    validate_vision_page_limit,
)
from .s3 import create_s3_client, ensure_object_exists, generate_presigned_url
from .schema import (
    load_schema,
    save_schema,
    schema_id_from_requirements,
    schema_paths,
    wrap_schema_with_numeric_normalizers,
)
from .sse import sse_error_response, sse_event

__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "MAX_FILE_SIZE_MB",
    "MAX_VISION_PAGES",
    "create_s3_client",
    "ensure_object_exists",
    "generate_presigned_url",
    "get_api_config",
    "load_schema",
    "save_schema",
    "schema_id_from_requirements",
    "schema_paths",
    "sse_error_response",
    "sse_event",
    "validate_file_size",
    "validate_vision_page_limit",
    "wrap_schema_with_numeric_normalizers",
]
