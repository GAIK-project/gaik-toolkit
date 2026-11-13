"""OpenTelemetry spans for every call of a ``ProviderClient``.

``create_llm_client()`` returns its client wrapped in ``TracedProviderClient``
when gaik's tracing is on (the ``gaik[otel]`` extra, see
``gaik.observability.tracing``), so ``chat``, ``chat_parsed``, ``chat_stream``
and ``embed`` each make one ``llm_call`` span. Without the extra, or with
``OTEL_SDK_DISABLED=true``, the factory returns the client unwrapped.

The wrapper changes nothing a caller sees: arguments are passed on as given,
and results, exceptions and retries are the client's own. Every other
attribute is the client's, read and set through the wrapper, and
``isinstance`` answers as for the client. A fault in the instrumentation is
logged and never reaches the caller. One difference: a model method replaced
on the client (``client.chat = Mock()``) is the one called, but reading
``client.chat`` back gives the wrapper's method, so assert on the mock itself.

A span holds lengths, never text: the characters of the messages' text parts
and of the answer (the parsed record as JSON for ``chat_parsed``; the summed
input texts for ``embed``). Tokens and settings come from the adapter, which
reports them as it sends the request (``record_request``) and reads the
response (``record_response``); a stream reports neither. A call made inside a
component's own ``llm_span`` gets no second span.

The factory wraps only when the ``gaik[otel]`` extra is installed; the
OpenTelemetry API alone, which other packages bring, leaves the client as it
is. Limits: a stream's span starts at its first read, so a client whose
``chat_stream`` fails before returning gets none. A call made in a thread
started inside a component's ``llm_span`` does not see that span (threads do
not inherit context), so it gets a span of its own.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Iterator
from typing import Any

from gaik.observability.tracing import (
    LLMCallSpan,
    in_llm_span,
    llm_span,
    start_llm_span,
    tracing_enabled,
)

logger = logging.getLogger(__name__)


def traced_client(client: Any) -> Any:
    """``client`` wrapped in ``TracedProviderClient`` when tracing is on, else itself."""
    if isinstance(client, TracedProviderClient) or not tracing_enabled():
        return client
    return TracedProviderClient(client)


class TracedProviderClient:
    """A ``ProviderClient`` whose model calls each make one ``llm_call`` span."""

    __slots__ = ("_gaik_client", "__weakref__")

    def __init__(self, client: Any) -> None:
        object.__setattr__(self, "_gaik_client", client)

    # -- transparency -------------------------------------------------------

    @property
    def __wrapped__(self) -> Any:
        """The client itself."""
        return self._gaik_client

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        # isinstance() falls back to __class__, so checks against the adapter's
        # class (OpenAIProvider, ...) answer as for the client itself.
        return type(self._gaik_client)

    # ProviderClient's data members, as properties: a runtime-checkable Protocol
    # looks them up on the class, past __getattr__.
    @property
    def provider(self) -> Any:
        return self._gaik_client.provider

    @provider.setter
    def provider(self, value: Any) -> None:
        self._gaik_client.provider = value

    @property
    def model(self) -> Any:
        return self._gaik_client.model

    @model.setter
    def model(self, value: Any) -> None:
        self._gaik_client.model = value

    @property
    def raw(self) -> Any:
        return self._gaik_client.raw

    @raw.setter
    def raw(self, value: Any) -> None:
        self._gaik_client.raw = value

    def __getattr__(self, name: str) -> Any:
        if name == "_gaik_client":  # not set yet: never recurse
            raise AttributeError(name)
        return getattr(self._gaik_client, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("provider", "model", "raw"):
            object.__setattr__(self, name, value)  # the properties' setters
        elif getattr(value, "__self__", None) is self and getattr(
            value, "__func__", None
        ) is getattr(TracedProviderClient, name, None):
            # This wrapper's own method put back under its own name (monkeypatch's
            # undo, for one): give the client back its own, or each would call
            # the other.
            try:
                delattr(self._gaik_client, name)
            except AttributeError:
                pass
        else:
            setattr(self._gaik_client, name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._gaik_client, name)

    def __dir__(self) -> list[str]:
        return dir(self._gaik_client)

    def __repr__(self) -> str:
        return repr(self._gaik_client)

    def __copy__(self) -> TracedProviderClient:
        return TracedProviderClient(copy.copy(self._gaik_client))

    def __deepcopy__(self, memo: dict[int, Any]) -> TracedProviderClient:
        return TracedProviderClient(copy.deepcopy(self._gaik_client, memo))

    def __reduce_ex__(self, protocol: Any) -> tuple[Any, ...]:
        return (TracedProviderClient, (self._gaik_client,))

    # -- the model calls ----------------------------------------------------

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        client = self._gaik_client
        span = self._span("chat", kwargs)
        if span is None:
            return client.chat(*args, **kwargs)
        with span as call:
            response = client.chat(*args, **kwargs)
            _record_lengths(call, _messages(args, kwargs), lambda: len(response.text))
        return response

    def chat_parsed(self, *args: Any, **kwargs: Any) -> Any:
        client = self._gaik_client
        span = self._span("chat", kwargs)
        if span is None:
            return client.chat_parsed(*args, **kwargs)
        with span as call:
            parsed = client.chat_parsed(*args, **kwargs)
            _record_lengths(call, _messages(args, kwargs), lambda: len(parsed.model_dump_json()))
        return parsed

    def chat_stream(self, *args: Any, **kwargs: Any) -> Any:
        client = self._gaik_client
        # Called here, not in the generator below, so a client that fails at
        # once still fails at once.
        stream = client.chat_stream(*args, **kwargs)
        if not _wanted():
            return stream
        try:
            provider, model = _identity(client, kwargs, "chat")
            messages = _messages(args, kwargs)
        except Exception:
            logger.debug("gaik tracing could not prepare a stream span", exc_info=True)
            return stream
        return _traced_stream(stream, provider, model, messages)

    def embed(self, *args: Any, **kwargs: Any) -> Any:
        client = self._gaik_client
        span = self._span("embeddings", kwargs)
        if span is None:
            return client.embed(*args, **kwargs)
        with span as call:
            vectors = client.embed(*args, **kwargs)
            texts = args[0] if args else kwargs.get("texts")
            if call.recording:
                call.record(None, input_length=_safe(lambda: sum(len(t) for t in texts)))
        return vectors

    def _span(self, operation: str, kwargs: dict[str, Any]) -> Any:
        """The ``llm_span`` for one call, or ``None`` to make the call without one."""
        if not _wanted():
            return None
        try:
            provider, model = _identity(self._gaik_client, kwargs, operation)
            return llm_span(None, provider=provider, model=model, operation=operation)
        except Exception:
            logger.debug("gaik tracing could not prepare a span", exc_info=True)
            return None


def _wanted() -> bool:
    """Whether a call should get a span: tracing on, and no component span open."""
    try:
        return tracing_enabled() and not in_llm_span()
    except Exception:
        return False


def _identity(client: Any, kwargs: dict[str, Any], operation: str) -> tuple[str, str]:
    """The provider and model a call goes to, as the adapter picks them."""
    default = "embedding_model" if operation == "embeddings" else "model"
    model = kwargs.get("model") or getattr(client, default, None) or "unknown"
    return str(getattr(client, "provider", None) or "unknown"), str(model)


def _traced_stream(
    stream: Iterator[str], provider: str, model: str, messages: Any
) -> Iterator[str]:
    """``stream`` passed on chunk by chunk inside a span that ends with it.

    The span starts at the first read and ends when the stream is used up,
    closed early or fails. It is current only while the client produces a
    chunk, never across a ``yield``: the caller's own code between chunks
    stays outside it. Nothing is buffered.
    """
    if not _wanted():  # read inside a component's span: that span covers it
        yield from stream
        return
    try:
        call = start_llm_span(None, provider=provider, model=model)
        recording = call.recording
    except Exception:
        logger.debug("gaik tracing could not start a stream span", exc_info=True)
        yield from stream
        return
    if not recording:
        try:
            yield from stream
        finally:
            call.end()
        return
    length = 0
    thrown: BaseException | None = None
    try:
        iterator = iter(stream)
        while True:
            with call.active():
                try:
                    if thrown is None:
                        chunk = next(iterator)
                    else:  # passed on into the client's stream, as yield from does
                        error, thrown = thrown, None
                        chunk = iterator.throw(error)
                except StopIteration:
                    break
            if isinstance(chunk, str):
                length += len(chunk)
            try:
                yield chunk
            except GeneratorExit:
                # Closed early: let the client's stream clean up as it would if
                # it were read directly.
                close = getattr(iterator, "close", None)
                if callable(close):
                    with call.active():
                        close()
                raise
            except BaseException as error:
                if not callable(getattr(iterator, "throw", None)):
                    raise
                thrown = error
    except GeneratorExit:
        raise
    except BaseException as exc:
        call.fail(exc)
        raise
    finally:
        call.record(None, input_length=_input_length(messages), output_length=length)
        call.end()


def _record_lengths(call: LLMCallSpan, messages: Any, output_length: Callable[[], int]) -> None:
    """Add the call's lengths to its span, measured only when the span is kept."""
    if call.recording:
        call.record(None, input_length=_input_length(messages), output_length=_safe(output_length))


def _messages(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return args[0] if args else kwargs.get("messages")


def _input_length(messages: Any) -> int | None:
    """Characters in the messages' text, never the text itself; images are not counted."""

    def count() -> int:
        total = 0
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        total += len(part["text"])
        return total

    return _safe(count)


def _safe(compute: Callable[[], int]) -> int | None:
    try:
        return compute()
    except Exception:
        return None
