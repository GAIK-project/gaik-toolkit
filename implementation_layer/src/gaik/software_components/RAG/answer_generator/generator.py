"""Answer generation for RAG workflows."""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator

from openai import APIError, APITimeoutError, RateLimitError

try:
    from langchain_core.documents import Document
except ImportError:
    Document = None  # type: ignore[assignment]

from gaik.observability.tracing import llm_span, provider_of, record_request, record_response
from gaik.software_components.config import get_openai_config
from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.factory import build_compat_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.llm.traced_client import traced_stream

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
        self.client = build_compat_client(self.config)
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

        with llm_span(
            "AnswerGenerator", provider=provider_of(self.client), model=self.model
        ) as call:
            answer = self._answer(messages)
            call.record_text(messages, answer)
        self._remember(query, answer)
        return answer

    def _answer(self, messages: list[dict]) -> str:
        if isinstance(self.client, ProviderClient):
            result = _with_retries(
                lambda: self.client.chat(messages=messages, model=self.model, temperature=0.0)
            )
            return result.text or ""

        def create():
            settings = normalize_chat_kwargs(self.model, {"temperature": 0.0}, config=self.config)
            record_request(settings)
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, **settings
            )
            record_response(response)
            return response

        response = _with_retries(create)
        if not response or not response.choices:
            return ""
        return response.choices[0].message.content or ""

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
            for delta in traced_stream(
                self._deltas(messages),
                component="AnswerGenerator",
                provider=provider_of(self.client),
                model=self.model,
                messages=messages,
            ):
                collected.append(delta)
                yield delta
            answer = "".join(collected)
            self._remember(query, answer)

        return iterator()

    def _deltas(self, messages: list[dict]) -> Iterator[str]:
        """The answer's text deltas; the request is made at the first read."""
        if isinstance(self.client, ProviderClient):
            stream = self.client.chat_stream(messages=messages, model=self.model, temperature=0.0)
            for delta in stream:
                if delta:
                    yield delta
            return
        settings = normalize_chat_kwargs(self.model, {"temperature": 0.0}, config=self.config)
        record_request(settings)
        response = _with_retries(
            lambda: self.client.chat.completions.create(
                model=self.model, messages=messages, **settings, stream=True
            )
        )
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

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
