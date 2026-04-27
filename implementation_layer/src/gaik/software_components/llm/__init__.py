"""Multi-provider LLM client abstractions.

Public API for components that need to call OpenAI, Azure, Anthropic, or
Google models through a single ``ProviderClient`` interface. The legacy
``software_components.config.create_openai_client`` helper continues to work
unchanged for OpenAI/Azure-only use cases.
"""

from gaik.software_components.llm.base import ChatResponse, ProviderClient
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import (
    assert_openai_or_azure,
    build_compat_client,
    create_llm_client,
)
from gaik.software_components.llm.providers import Provider, resolve_provider

__all__ = [
    "ChatResponse",
    "Provider",
    "ProviderClient",
    "assert_openai_or_azure",
    "build_compat_client",
    "create_llm_client",
    "get_llm_config",
    "resolve_provider",
]
