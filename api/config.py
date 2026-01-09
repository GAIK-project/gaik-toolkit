"""Environment configuration for GAIK API."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """API configuration from environment variables."""

    # API settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Authentication
    API_KEY: str = ""  # Required in production

    # OpenAI/Azure configuration (all from .env)
    USE_AZURE: bool = True
    OPENAI_API_KEY: str | None = None
    AZURE_API_KEY: str | None = None
    AZURE_ENDPOINT: str | None = None
    AZURE_API_VERSION: str = "2025-04-01-preview"
    AZURE_DEPLOYMENT: str = "gpt-5.1"
    AZURE_TRANSCRIPTION_MODEL: str = "whisper"

    # CORS
    CORS_ORIGINS: list[str] = []

    # File limits
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_AUDIO_EXTENSIONS: list[str] = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    ALLOWED_DOC_EXTENSIONS: list[str] = [".pdf", ".docx"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()


settings = get_settings()


def get_openai_config() -> dict:
    """Build OpenAI configuration from environment variables."""
    if settings.USE_AZURE:
        return {
            "use_azure": True,
            "api_key": settings.AZURE_API_KEY,
            "azure_endpoint": settings.AZURE_ENDPOINT,
            "azure_audio_endpoint": settings.AZURE_ENDPOINT,
            "api_version": settings.AZURE_API_VERSION,
            "model": settings.AZURE_DEPLOYMENT,
            "transcription_model": settings.AZURE_TRANSCRIPTION_MODEL,
        }
    else:
        return {
            "use_azure": False,
            "api_key": settings.OPENAI_API_KEY,
            "model": "gpt-4o",
            "transcription_model": "whisper-1",
        }
