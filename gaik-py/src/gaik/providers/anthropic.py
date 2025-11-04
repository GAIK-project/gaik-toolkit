"""Anthropic provider implementation."""

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic LLM provider using LangChain's ChatAnthropic.

    Supports Claude models including Claude 3.5 Sonnet, Claude 3 Opus, and others.
    Requires ANTHROPIC_API_KEY environment variable or api_key parameter.
    """

    @property
    def default_model(self) -> str:
        """Return Anthropic's default model.

        Returns:
            str: "claude-sonnet-4-5-20250929" (Claude Sonnet 4.5)
        """
        return "claude-sonnet-4-5-20250929"

    def create_chat_model(
        self,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create Anthropic chat model instance.

        Args:
            model: Model name (e.g., "claude-sonnet-4-5-20250929", "claude-3-5-sonnet-20241022").
                   Defaults to "claude-sonnet-4-5-20250929".
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY environment variable.
            **kwargs: Additional parameters passed to ChatAnthropic (e.g., temperature, max_tokens).

        Returns:
            ChatAnthropic: Configured Anthropic chat model

        Example:
            >>> provider = AnthropicProvider()
            >>> model = provider.create_chat_model(model="claude-3-5-sonnet-20241022", temperature=0.7)
        """
        return ChatAnthropic(
            model=model or self.default_model,
            api_key=api_key,
            **kwargs,
        )
