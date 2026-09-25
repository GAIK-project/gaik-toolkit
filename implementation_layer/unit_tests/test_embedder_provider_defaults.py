"""A provider's embedding model must not silently fall back to an OpenAI model."""

from unittest.mock import patch

import pytest
from gaik.software_components.llm import get_llm_config
from gaik.software_components.RAG.embedder import Embedder


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible"])
def test_custom_provider_requires_embedding_model(provider):
    config = get_llm_config(
        provider,
        api_key="test",
        base_url="https://example.test/v1",
        model="chat-model",
        embedding_model="",
    )
    with patch("gaik.software_components.RAG.embedder.embedder.build_compat_client") as factory:
        with pytest.raises(ValueError, match="requires an explicit embedding_model"):
            Embedder(config)
        factory.assert_not_called()


def test_explicit_embedding_override_is_used():
    config = get_llm_config("aitta", api_key="test", embedding_model="")
    embedder = Embedder(config, model="intfloat/multilingual-e5-large")
    try:
        assert embedder.model == "intfloat/multilingual-e5-large"
    finally:
        embedder.client.raw.close()


def test_legacy_openai_default_is_preserved():
    embedder = Embedder({"use_azure": False, "api_key": "test"})
    try:
        assert embedder.model == "text-embedding-3-large"
    finally:
        embedder.client.close()
