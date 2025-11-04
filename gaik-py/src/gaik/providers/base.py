"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models import BaseChatModel


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All provider implementations must inherit from this class and implement
    the required methods. This ensures consistent interface across all providers.
    """

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model name for this provider.

        Returns:
            str: The default model identifier
        """
        pass

    @abstractmethod
    def create_chat_model(
        self,
        model: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create a LangChain chat model instance.

        Args:
            model: Model name. If None, uses the provider's default model.
            api_key: API key for authentication. If None, uses environment variable.
            **kwargs: Additional provider-specific parameters.

        Returns:
            BaseChatModel: Configured LangChain chat model instance
        """
        pass
