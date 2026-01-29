"""OpenAI/Azure OpenAI text embedding utilities."""

from __future__ import annotations

import time
from collections.abc import Iterable

from openai import APIError, APITimeoutError, RateLimitError

try:
    from langchain_core.documents import Document
except ImportError as exc:
    raise ImportError(
        "Embedder requires 'langchain-core'. Install extras with 'pip install gaik[embedder]'"
    ) from exc

from gaik.software_components.config import create_openai_client, get_openai_config


def _chunked(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _with_retries(call, *, tries: int = 4) -> object:
    for attempt in range(tries):
        try:
            return call()
        except (RateLimitError, APITimeoutError, APIError):
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)


class Embedder:
    """Generate vector embeddings from text."""

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        batch_size: int = 100,
    ) -> None:
        self.config = config
        self.model = model or "text-embedding-3-large"
        self.batch_size = batch_size
        self.client = create_openai_client(config)

    def embed(
        self,
        documents: list[Document] | list[str],
        *,
        batch_size: int | None = None,
    ) -> tuple[list[list[float]], list[Document]]:
        """Embed documents or raw strings while preserving metadata."""
        if not documents:
            return [], []

        if isinstance(documents[0], Document):
            docs = documents  # type: ignore[assignment]
        else:
            docs = [Document(page_content=text, metadata={}) for text in documents]  # type: ignore[arg-type]

        size = batch_size or self.batch_size
        embeddings: list[list[float]] = []

        for batch in _chunked([doc.page_content for doc in docs], size):
            resp = _with_retries(
                lambda: self.client.embeddings.create(model=self.model, input=batch)
            )
            data = sorted(resp.data, key=lambda item: item.index)
            embeddings.extend([item.embedding for item in data])

        return embeddings, docs

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for search."""
        embeddings, _ = self.embed([query], batch_size=1)
        return embeddings[0] if embeddings else []


def embed_texts(
    texts: list[str],
    *,
    use_azure: bool = True,
    model: str | None = None,
    batch_size: int = 100,
) -> tuple[list[list[float]], list[Document]]:
    """One-shot embedding helper."""
    config = get_openai_config(use_azure=use_azure)
    embedder = Embedder(config=config, model=model, batch_size=batch_size)
    return embedder.embed(texts, batch_size=batch_size)
