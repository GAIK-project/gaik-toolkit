"""FastAPI dependencies and authentication."""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from api.config import settings

# X-API-Key header definition
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Validate X-API-Key header.

    In DEBUG mode, authentication is optional.
    In production, a valid API key is required.

    Raises:
        HTTPException: If API key is invalid or missing in production.
    """
    # Skip auth in debug mode if no API_KEY configured
    if settings.DEBUG and not settings.API_KEY:
        return "debug-mode"

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    return api_key
