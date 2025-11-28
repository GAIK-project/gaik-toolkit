"""
Shared API configuration for OpenAI and Azure OpenAI.

This module re-exports configuration from the common gaik.config module.
"""

from ..config import get_openai_config, create_openai_client

__all__ = ["get_openai_config", "create_openai_client"]
