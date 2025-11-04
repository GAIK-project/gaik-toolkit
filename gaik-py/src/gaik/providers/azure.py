"""Azure OpenAI provider implementation."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import AzureChatOpenAI

from .base import LLMProvider


class AzureProvider(LLMProvider):
    """Azure OpenAI LLM provider using LangChain's AzureChatOpenAI.

    Supports OpenAI models deployed on Azure. Requires:
    - AZURE_OPENAI_API_KEY environment variable or api_key parameter
    - AZURE_OPENAI_ENDPOINT environment variable or azure_endpoint parameter
    - azure_deployment parameter (deployment name in Azure)
    """

    @property
    def default_model(self) -> str:
        """Return Azure OpenAI's default model.

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
        """Create Azure OpenAI chat model instance.

        Args:
            model: Model name (e.g., "gpt-4.1", "gpt-4o", "gpt-35-turbo").
                   Defaults to "gpt-4.1".
            api_key: Azure OpenAI API key. If None, uses AZURE_OPENAI_API_KEY environment variable.
            **kwargs: Additional parameters passed to AzureChatOpenAI:
                - azure_endpoint (str): Azure OpenAI endpoint URL
                - azure_deployment (str): Deployment name in Azure
                - api_version (str): API version (default: "2024-02-01")
                - temperature, max_tokens, etc.

        Returns:
            AzureChatOpenAI: Configured Azure OpenAI chat model

        Example:
            >>> provider = AzureProvider()
            >>> model = provider.create_chat_model(
            ...     model="gpt-4o",
            ...     azure_endpoint="https://your-resource.openai.azure.com/",
            ...     azure_deployment="gpt-4o-deployment",
            ...     api_key="your-api-key"
            ... )
        """
        return AzureChatOpenAI(
            model=model or self.default_model,
            api_key=api_key,
            **kwargs,
        )
