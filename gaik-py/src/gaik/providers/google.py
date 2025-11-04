"""Google provider implementation."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from .base import LLMProvider


class GoogleProvider(LLMProvider):
    """Google LLM provider using LangChain's ChatGoogleGenerativeAI.

    Supports Google's Gemini models including Gemini 2.5 and Gemini 1.5.
    Requires GOOGLE_API_KEY environment variable or api_key parameter.
    """

    @property
    def default_model(self) -> str:
        """Return Google's default model.

        Returns:
            str: "gemini-2.5-flash-latest" (Gemini 2.5)
        """
        return "gemini-2.5-flash-latest"

    def create_chat_model(
        self,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create Google chat model instance.

        Args:
            model: Model name (e.g., "gemini-2.5-flash-latest", "gemini-1.5-pro").
                   Defaults to "gemini-2.5-flash-latest".
            api_key: Google API key. If None, uses GOOGLE_API_KEY environment variable.
            **kwargs: Additional parameters passed to ChatGoogleGenerativeAI (e.g., temperature, max_tokens).

        Returns:
            ChatGoogleGenerativeAI: Configured Google chat model

        Example:
            >>> provider = GoogleProvider()
            >>> model = provider.create_chat_model(model="gemini-1.5-pro", temperature=0.7)
        """
        return ChatGoogleGenerativeAI(
            model=model or self.default_model,
            api_key=api_key,
            **kwargs,
        )
