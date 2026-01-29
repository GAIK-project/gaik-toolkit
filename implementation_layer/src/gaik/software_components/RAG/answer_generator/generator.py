"""Answer generation for RAG workflows."""

from __future__ import annotations

import time
from collections.abc import Iterable

from openai import APIError, APITimeoutError, RateLimitError

try:
    from langchain_core.documents import Document
except ImportError:
    Document = None  # type: ignore[assignment]

from gaik.software_components.config import create_openai_client, get_openai_config

DEFAULT_PROMPT = (
    "You are a helpful assistant that answers questions using only the provided context.\n"
    "If the context does not contain the answer, say you do not have enough information.\n"
    "Be concise and factual.\n\n"
    "Context:\n{context}\n\n"
    "Question: {query}"
)


DEFAULT_PROMPT_WITH_CITATIONS = (
    "You are a helpful assistant that answers questions using only the provided context.\n"
    "If the context does not contain the answer, say you do not have enough information.\n"
    "Be concise and factual. Include citations in the form [document_name, page X].\n\n"
    "Context:\n{context}\n\n"
    "Question: {query}"
)


def _with_retries(call, *, tries: int = 4):
    for attempt in range(tries):
        try:
            return call()
        except (RateLimitError, APITimeoutError, APIError):
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)


class AnswerGenerator:
    """Generate answers from retrieved context."""

    def __init__(
        self,
        *,
        config: dict | None = None,
        use_azure: bool = True,
        model: str | None = None,
        citations: bool = False,
        prompt: str | None = None,
        stream: bool = True,
        conversation_history: bool = False,
        last_n: int = 10,
    ) -> None:
        self.config = config or get_openai_config(use_azure=use_azure)
        self.model = model or self.config["model"]
        self.citations = citations
        self.prompt = prompt
        self.stream = stream
        self.conversation_history = conversation_history
        self.last_n = last_n
        self.client = create_openai_client(self.config)
        self._history: list[tuple[str, str]] = []

    def generate(
        self,
        query: str,
        context: str | list[Document],
        *,
        stream: bool | None = None,
    ) -> str | Iterable[str]:
        use_stream = self.stream if stream is None else stream

        context_text = self._format_context(context)
        prompt = self._build_prompt(query, context_text)
        messages = self._build_messages(prompt)

        if use_stream:
            return self._stream_answer(messages, query)

        response = _with_retries(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
            )
        )
        if not response or not response.choices:
            answer = ""
        else:
            answer = response.choices[0].message.content or ""
        self._remember(query, answer)
        return answer

    def _build_prompt(self, query: str, context_text: str) -> str:
        if self.prompt:
            return self.prompt.format(query=query, context=context_text)
        template = DEFAULT_PROMPT_WITH_CITATIONS if self.citations else DEFAULT_PROMPT
        return template.format(query=query, context=context_text)

    def _build_messages(self, prompt: str) -> list[dict]:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        if not self.conversation_history:
            return messages

        if self._history:
            history_msgs: list[dict] = []
            for question, answer in self._history[-self.last_n :]:
                history_msgs.append({"role": "user", "content": question})
                history_msgs.append({"role": "assistant", "content": answer})
            messages = history_msgs + messages
        return messages

    def _stream_answer(self, messages: list[dict], query: str) -> Iterable[str]:
        def iterator():
            collected = []
            response = _with_retries(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    stream=True,
                )
            )
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    collected.append(delta)
                    yield delta
            answer = "".join(collected)
            self._remember(query, answer)

        return iterator()

    def _remember(self, query: str, answer: str) -> None:
        if not self.conversation_history:
            return
        self._history.append((query, answer))
        if len(self._history) > self.last_n:
            self._history = self._history[-self.last_n :]

    @staticmethod
    def _format_context(context: str | list[Document]) -> str:
        if isinstance(context, str):
            return context
        if not context:
            return ""
        if Document is None:
            return "\n\n".join([doc.page_content for doc in context])  # type: ignore[union-attr]

        lines = []
        for doc in context:
            meta = doc.metadata
            document_name = meta.get("document_name", "unknown")
            page = meta.get("page_number", "unknown")
            heading = meta.get("heading")
            header = f"[Document: {document_name}, Page: {page}]"
            if heading:
                header = f"{header} {heading}"
            lines.append(header)
            lines.append(doc.page_content)
        return "\n\n".join(lines)
