"""OpenAI provider implementation."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from .base import LLMProvider, _build_model_kwargs


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider using LangChain's ChatOpenAI.

    Supports OpenAI's GPT models including GPT-4, GPT-4 Turbo, and GPT-3.5.
    Requires OPENAI_API_KEY environment variable or api_key parameter.
    """

    @property
    def default_model(self) -> str:
        """Return OpenAI's default model.

        Returns:
            str: "gpt-4.1"
        """
        return "gpt-4.1"

    def create_chat_model(
        self,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create OpenAI chat model instance.

        Args:
            model: Model name (e.g., "gpt-4.1", "gpt-4o", "gpt-3.5-turbo").
                   Defaults to "gpt-4.1".
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY environment variable.
            **kwargs: Additional parameters passed to ChatOpenAI (e.g., temperature, max_tokens).

        Returns:
            ChatOpenAI: Configured OpenAI chat model

        Example:
            >>> provider = OpenAIProvider()
            >>> model = provider.create_chat_model(model="gpt-4o", temperature=0.7)
        """
        model_kwargs = _build_model_kwargs(
            model=model or self.default_model,
            api_key=api_key,
            **kwargs
        )
        return ChatOpenAI(**model_kwargs)
