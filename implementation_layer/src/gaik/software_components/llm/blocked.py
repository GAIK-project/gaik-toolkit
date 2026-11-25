"""A reply the provider's content filter blocked, or that the model declined to give.

Without these checks a blocked reply came back as empty text (or as a parse error
that pointed at the schema), so a component returned an empty or partial result
as if the document held nothing. Every provider now raises ``ContentBlockedError``
instead, and the error is not retried: the same request is blocked again.

The checks read the providers' responses by attribute name, so no optional SDK
has to be imported:

* OpenAI, Azure OpenAI and LiteLLM: ``finish_reason == "content_filter"``, a
  ``refusal`` on the message, or a 400 error whose code is ``content_filter``
  (Azure's prompt filter) or LiteLLM's ``ContentPolicyViolationError``;
* Anthropic: ``stop_reason == "refusal"``;
* Google Gen AI: a ``block_reason`` in the prompt feedback, or a candidate that
  finished for a safety or recitation reason.

For OpenAI and Azure most components keep the raw SDK client
(``build_compat_client``); they call it through ``checked_openai`` for the same
checks.
"""

from __future__ import annotations

from typing import Any

#: Why a reply was blocked: the provider's filter or the model itself.
CONTENT_FILTER = "content_filter"
REFUSAL = "refusal"

_OPENAI_FILTER_FINISH = frozenset({"content_filter"})
_GOOGLE_SAFETY_FINISH = frozenset(
    {
        "SAFETY",
        "PROHIBITED_CONTENT",
        "BLOCKLIST",
        "SPII",
        "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT",
        # The reply would have repeated protected text, so Gemini stopped it.
        "RECITATION",
        "IMAGE_RECITATION",
    }
)
_FILTER_ERROR_CODES = frozenset({"content_filter", "content_policy_violation"})
#: LiteLLM's filter error, and the one openai's ``parse()`` raises itself for a
#: ``content_filter`` finish.
_FILTER_ERROR_NAMES = frozenset({"ContentPolicyViolationError", "ContentFilterFinishReasonError"})


class ContentBlockedError(RuntimeError):
    """The provider's content filter blocked the request or the reply, or the model
    declined to answer.

    ``reason`` is ``"content_filter"`` or ``"refusal"``; ``detail`` is the
    provider's code for it (a finish reason, a block reason or an error code).
    ``refusal_text`` is the model's own refusal, when it gave one; it can echo the
    user's document, so it is kept out of the message and so out of logs. Show the
    user a sentence of your own, not the message.
    """

    def __init__(
        self, provider: str, model: str, reason: str, detail: str = "", refusal_text: str = ""
    ) -> None:
        self.provider = provider
        self.model = model
        self.reason = reason
        self.detail = detail
        self.refusal_text = refusal_text
        what = (
            "the provider's content filter blocked the request or the reply"
            if reason == CONTENT_FILTER
            else "the model declined to answer"
        )
        super().__init__(f"{provider} model {model}: {what}" + (f" ({detail})" if detail else ""))


def _name(value: Any) -> str:
    """An enum's name or a plain string, upper-cased for Google, as given otherwise."""
    name = getattr(value, "name", None)
    return name if isinstance(name, str) else str(value or "")


def check_openai_choice(choice: Any, *, provider: str, model: str) -> None:
    """Raise when an OpenAI-style choice (OpenAI, Azure, LiteLLM) was blocked."""
    if choice is None:
        return
    finish = getattr(choice, "finish_reason", None)
    if isinstance(finish, str) and finish in _OPENAI_FILTER_FINISH:
        raise ContentBlockedError(provider, model, CONTENT_FILTER, finish)
    message = getattr(choice, "message", None) or getattr(choice, "delta", None)
    refusal = getattr(message, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        raise ContentBlockedError(provider, model, REFUSAL, "refusal", refusal.strip())


def blocked_request_error(
    error: BaseException, *, provider: str, model: str
) -> ContentBlockedError | None:
    """The ``ContentBlockedError`` for an SDK error that is a content-filter refusal
    of the request (Azure's 400 ``content_filter``), or None for any other error."""
    if any(cls.__name__ in _FILTER_ERROR_NAMES for cls in type(error).__mro__):
        return ContentBlockedError(provider, model, CONTENT_FILTER, "content_filter")
    status = getattr(error, "status_code", None)
    if status != 400:
        return None
    code = getattr(error, "code", None)
    if not isinstance(code, str):
        body = getattr(error, "body", None)
        inner = body.get("error", body) if isinstance(body, dict) else None
        code = inner.get("code") if isinstance(inner, dict) else None
    if isinstance(code, str) and code in _FILTER_ERROR_CODES:
        return ContentBlockedError(provider, model, CONTENT_FILTER, code)
    return None


def check_anthropic_response(response: Any, *, provider: str, model: str) -> None:
    """Raise when Claude declined to answer (``stop_reason == "refusal"``)."""
    if getattr(response, "stop_reason", None) == "refusal":
        raise ContentBlockedError(provider, model, REFUSAL, "refusal")


def check_google_response(response: Any, *, provider: str, model: str) -> None:
    """Raise when Gemini blocked the prompt or stopped a candidate for safety."""
    feedback = getattr(response, "prompt_feedback", None)
    block = getattr(feedback, "block_reason", None)
    if block and _name(block) not in {"", "BLOCKED_REASON_UNSPECIFIED"}:
        raise ContentBlockedError(provider, model, CONTENT_FILTER, _name(block))
    for candidate in getattr(response, "candidates", None) or []:
        finish = _name(getattr(candidate, "finish_reason", None))
        if finish in _GOOGLE_SAFETY_FINISH:
            raise ContentBlockedError(provider, model, CONTENT_FILTER, finish)


def _checked_stream(stream: Any, provider: str, model: str) -> Any:
    """The stream's chunks, raising ContentBlockedError at a filtered one."""
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if choices:
            check_openai_choice(choices[0], provider=provider, model=model)
        yield chunk


def _checked(create: Any, kwargs: dict[str, Any], provider: str) -> Any:
    """``create(**kwargs)`` on a raw OpenAI client, raising ContentBlockedError for
    a blocked request or reply; a stream's chunks are checked as they are read."""
    model = str(kwargs.get("model", ""))
    try:
        completion = create(**kwargs)
    except Exception as error:
        blocked = blocked_request_error(error, provider=provider, model=model)
        if blocked is not None:
            raise blocked from error
        raise
    if kwargs.get("stream"):
        return _checked_stream(completion, provider, model)
    choices = getattr(completion, "choices", None) or []
    if choices:
        check_openai_choice(choices[0], provider=provider, model=model)
    return completion


class _CheckedCompletions:
    def __init__(self, completions: Any, provider: str) -> None:
        self._completions = completions
        self._provider = provider

    def create(self, **kwargs: Any) -> Any:
        return _checked(self._completions.create, kwargs, self._provider)

    def parse(self, **kwargs: Any) -> Any:
        return _checked(self._completions.parse, kwargs, self._provider)


class _CheckedChat:
    def __init__(self, chat: Any, provider: str) -> None:
        self.completions = _CheckedCompletions(chat.completions, provider)


class _CheckedOpenAI:
    """``client.chat.completions`` and ``client.beta.chat.completions`` of a raw
    OpenAI or Azure OpenAI client, with the blocked-reply checks."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._provider = "azure" if "Azure" in type(client).__name__ else "openai"

    @property
    def chat(self) -> _CheckedChat:
        return _CheckedChat(self._client.chat, self._provider)

    @property
    def beta(self) -> Any:
        return _CheckedBeta(self._client.beta, self._provider)


class _CheckedBeta:
    def __init__(self, beta: Any, provider: str) -> None:
        self.chat = _CheckedChat(beta.chat, provider)


def checked_openai(client: Any) -> _CheckedOpenAI:
    """A raw ``OpenAI``/``AzureOpenAI`` client's chat calls, raising
    ContentBlockedError when the content filter blocked the request or the reply,
    or the model refused. Components that keep the raw client for OpenAI and
    Azure (``build_compat_client``) call through this."""
    return _CheckedOpenAI(client)
