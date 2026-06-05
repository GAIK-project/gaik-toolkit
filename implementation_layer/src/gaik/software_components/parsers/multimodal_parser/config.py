"""
Shared API configuration for OpenAI/Azure OpenAI, Anthropic Foundry, and Google Vertex AI.

This module provides reusable configuration utilities for creating
model clients and auth tokens across different extraction modules.
"""

import json
import os

import anthropic
import google.auth.transport.requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from openai import AzureOpenAI, OpenAI

load_dotenv()


def require_env(name: str) -> str:
    """Return a required environment variable or fail with a clear message."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not found in .env")
    return value.strip()


def get_openai_config(use_azure: bool = True) -> dict:
    """Get OpenAI configuration based on whether to use Azure or standard OpenAI."""
    if use_azure:
        azure_endpoint = require_env("AZURE_ENDPOINT")
        return {
            "use_azure": True,
            "api_key": require_env("AZURE_API_KEY"),
            "azure_endpoint": azure_endpoint,
            "azure_audio_endpoint": azure_endpoint,
            "api_version": os.getenv("AZURE_API_VERSION", "2025-03-01-preview"),
            "model": os.getenv("AZURE_DEPLOYMENT", "gpt-5.4"),
            "transcription_model": "gpt-4o-transcribe",
        }
    return {
        "use_azure": False,
        "api_key": require_env("OPENAI_API_KEY"),
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-2026-03-05"),
        "transcription_model": "gpt-4o-transcribe",
    }


def create_openai_client(config: dict):
    """Create an OpenAI or Azure OpenAI client based on configuration."""
    if config.get("use_azure", False):
        return AzureOpenAI(
            api_key=config["api_key"],
            api_version=config["api_version"],
            azure_endpoint=config["azure_endpoint"],
        )
    return OpenAI(api_key=config["api_key"])


def get_claude_config(use_azure: bool = True) -> dict:
    """Get Anthropic configuration based on whether to use Azure Foundry or direct API."""
    if use_azure:
        return {
            "use_azure": True,
            "api_key": require_env("AZURE_API_KEY"),
            "resource": require_env("ANTHROPIC_FOUNDRY_RESOURCE"),
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        }
    return {
        "use_azure": False,
        "api_key": require_env("ANTHROPIC_API_KEY"),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    }


def create_claude_client(config: dict):
    """Create an Anthropic Foundry or direct Anthropic client based on configuration."""
    if config.get("use_azure", False):
        return anthropic.AnthropicFoundry(
            resource=config["resource"],
            api_key=config["api_key"],
        )
    return anthropic.Anthropic(api_key=config["api_key"])


def get_google_config(vertex_ai: bool = True) -> dict:
    """Get Google configuration based on whether to use Vertex AI or direct Gemini API."""
    model = os.getenv("GOOGLE_MODEL", "gemini-3-flash-preview")
    if vertex_ai:
        return {
            "vertex_ai": True,
            "project_id": require_env("GOOGLE_PROJECT_ID"),
            "service_account_json": require_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
            "model": model,
            "scopes": [
                scope.strip() for scope in require_env("GOOGLE_SCOPES").split(",") if scope.strip()
            ],
            "generate_content_url": require_env("GOOGLE_GENERATE_CONTENT_URL"),
        }
    return {
        "vertex_ai": False,
        "api_key": require_env("GOOGLE_API_KEY"),
        "model": model,
    }


def get_google_access_token(config: dict) -> str:
    """Refresh and return a Google Cloud access token for Vertex AI requests."""
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(config["service_account_json"]),
        scopes=config["scopes"],
    )
    request = google.auth.transport.requests.Request()
    if not credentials.valid:
        credentials.refresh(request)
    return credentials.token
