"""LLM provider registry for GAIK toolkit.

This module provides a unified interface for working with different LLM providers.
All GAIK modules (extract, summarize, etc.) use this shared provider infrastructure.

Available providers:
- openai: OpenAI GPT models (default: gpt-4.1)
- anthropic: Anthropic Claude models (default: claude-sonnet-4-5-20250929)
- azure: Azure OpenAI models (default: gpt-4.1)
- google: Google Gemini models (default: gemini-2.5-flash)

Example:
    >>> from gaik.providers import get_provider
    >>> provider = get_provider("openai")
    >>> model = provider.create_chat_model(model="gpt-4o")
"""

from .anthropic import AnthropicProvider
from .azure import AzureProvider
from .base import LLMProvider
from .google import GoogleProvider
from .openai import OpenAIProvider

# Provider registry
PROVIDERS: dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "azure": AzureProvider(),
    "google": GoogleProvider(),
}


def get_provider(name: str) -> LLMProvider:
    """Get provider instance by name.

    Args:
        name: Provider name (e.g., "openai", "anthropic", "azure", "google")

    Returns:
        LLMProvider: Provider instance

    Raises:
        ValueError: If provider name is not recognized

    Example:
        >>> provider = get_provider("anthropic")
        >>> model = provider.create_chat_model()
    """
    if name not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown provider: '{name}'. Available providers: {available}")
    return PROVIDERS[name]


__all__ = [
    "LLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "AzureProvider",
    "GoogleProvider",
    "PROVIDERS",
    "get_provider",
]
