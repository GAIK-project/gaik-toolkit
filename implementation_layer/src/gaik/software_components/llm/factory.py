"""Factory that turns a config dict into a ``ProviderClient`` instance.

Lazy-imports the provider-specific adapter so that an installation without the
``llm-anthropic`` or ``llm-google`` extras can still use OpenAI/Azure.
"""

from __future__ import annotations

from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.providers import Provider, resolve_provider


def create_llm_client(config: dict) -> ProviderClient:
    """Return a ``ProviderClient`` matching the configured provider.

    Accepts either the new ``{"provider": ..., ...}`` shape or the legacy
    OpenAI/Azure dict (``{"use_azure": True, "api_key": ...}``). Raises
    ``ImportError`` with a useful hint if the provider's SDK extra is missing.
    """
    name = resolve_provider(config=config)
    if name in (Provider.OPENAI.value, Provider.AZURE.value):
        from gaik.software_components.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
    if name in (Provider.ANTHROPIC.value, Provider.ANTHROPIC_FOUNDRY.value):
        try:
            from gaik.software_components.llm.anthropic_provider import AnthropicProvider
        except ImportError as exc:
            raise ImportError(
                "Anthropic provider requires the 'llm-anthropic' extra: "
                "pip install 'gaik[llm-anthropic]'"
            ) from exc
        return AnthropicProvider(config)
    if name in (Provider.GOOGLE.value, Provider.VERTEX.value):
        try:
            from gaik.software_components.llm.google_provider import GoogleProvider
        except ImportError as exc:
            raise ImportError(
                "Google provider requires the 'llm-google' extra: "
                "pip install 'gaik[llm-google]'"
            ) from exc
        return GoogleProvider(config)
    raise ValueError(f"Unsupported provider: {name}")
