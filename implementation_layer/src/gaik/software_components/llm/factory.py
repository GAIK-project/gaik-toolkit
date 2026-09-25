"""Factory that turns a config dict into a ``ProviderClient`` instance.

Lazy-imports the provider-specific adapter so that an installation without the
``llm-anthropic`` or ``llm-google`` extras can still use OpenAI/Azure.
"""

from __future__ import annotations

from gaik.software_components.config import create_openai_client
from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.providers import Provider, resolve_provider


def create_llm_client(config: dict) -> ProviderClient:
    """Return a ``ProviderClient`` matching the configured provider.

    Accepts either the new ``{"provider": ..., ...}`` shape or the legacy
    OpenAI/Azure dict (``{"use_azure": True, "api_key": ...}``). Raises
    ``ImportError`` with a useful hint if the provider's SDK extra is missing.
    """
    name = resolve_provider(config=config)
    config = {**config, "provider": name, "use_azure": name == Provider.AZURE.value}
    if name == Provider.LITELLM.value:
        try:
            from gaik.software_components.llm.litellm_provider import LiteLLMProvider
        except ImportError as exc:
            raise ImportError(
                "LiteLLM requires the 'llm-litellm' extra: pip install 'gaik[llm-litellm]'"
            ) from exc
        return LiteLLMProvider(config)
    if name in (
        Provider.OPENAI.value,
        Provider.AZURE.value,
        Provider.OPENAI_COMPATIBLE.value,
        Provider.AITTA.value,
    ):
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
                "Google provider requires the 'llm-google' extra: pip install 'gaik[llm-google]'"
            ) from exc
        return GoogleProvider(config)
    raise ValueError(f"Unsupported provider: {name}")


def assert_openai_or_azure(config: dict, *, component: str) -> None:
    """Raise NotImplementedError if config picks a non-OpenAI/Azure provider.

    Audio components (transcriber, parallel_transcriber, text_to_speech) only
    support OpenAI and Azure: Anthropic has no audio API and Google's audio is
    served through different APIs. An OpenAI-compatible chat endpoint does not
    imply support for OpenAI's transcription or speech endpoints.
    """
    # A bare legacy config means standard OpenAI, as in create_openai_client().
    provider = resolve_provider(config={"use_azure": False, **config})
    if provider not in {Provider.OPENAI.value, Provider.AZURE.value}:
        raise NotImplementedError(
            f"{component} only supports OpenAI/Azure (got provider='{provider}'). "
            "OpenAI-compatible chat endpoints do not necessarily support "
            "transcription or text-to-speech. Configure an OpenAI/Azure audio provider."
        )


def build_compat_client(config: dict):
    """Pick a client matching the config's provider, with legacy bit-for-bit fallback.

    Components call this from their constructors so OpenAI/Azure users keep
    using the original ``OpenAI``/``AzureOpenAI`` instance (preserving the exact
    deterministic call paths and kwargs in older code), while non-OpenAI
    providers go through the multi-provider ``ProviderClient`` adapter.

    Returns the raw ``OpenAI``/``AzureOpenAI`` client for OpenAI/Azure configs,
    including legacy configs with ``use_azure``; returns a ``ProviderClient``
    for other providers, including Aitta and custom compatible servers.
    Minimal legacy dictionaries without either routing field retain standard
    OpenAI. New callers wanting the environment-selected provider should use
    ``get_llm_config()`` or ``create_llm_client()``.
    """
    if "provider" not in config and "use_azure" not in config:
        return create_openai_client({**config, "provider": Provider.OPENAI.value})
    name = resolve_provider(config=config)
    if name in (Provider.OPENAI.value, Provider.AZURE.value):
        return create_openai_client({**config, "provider": name})
    return create_llm_client(config)
