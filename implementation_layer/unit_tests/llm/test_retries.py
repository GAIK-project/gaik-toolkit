"""One retry helper: only rate limits, server errors, timeouts and lost connections
are sent again (#146 item 10)."""

from __future__ import annotations

import httpx
import openai
import pytest
from gaik.software_components.llm.retries import is_transient_error, with_retries

_REQUEST = httpx.Request("POST", "https://api.example.test/v1/chat/completions")


def _openai_status(status: int) -> openai.APIStatusError:
    response = httpx.Response(status, request=_REQUEST, json={"error": {"message": "x"}})
    cls = {
        400: openai.BadRequestError,
        401: openai.AuthenticationError,
        403: openai.PermissionDeniedError,
        404: openai.NotFoundError,
        409: openai.ConflictError,
        422: openai.UnprocessableEntityError,
        429: openai.RateLimitError,
    }.get(status, openai.InternalServerError if status >= 500 else openai.APIStatusError)
    return cls("x", response=response, body=None)


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 529])
def test_rate_limits_and_server_errors_are_transient(status):
    assert is_transient_error(_openai_status(status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_a_refused_request_is_not_transient(status):
    assert not is_transient_error(_openai_status(status))


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=_REQUEST),
        openai.APIConnectionError(request=_REQUEST),
        httpx.ReadTimeout("slow", request=_REQUEST),
        httpx.ConnectError("refused", request=_REQUEST),
        TimeoutError(),
        ConnectionResetError(),
    ],
)
def test_timeouts_and_lost_connections_are_transient(error):
    assert is_transient_error(error)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("bad"),
        openai.APIResponseValidationError(
            response=httpx.Response(200, request=_REQUEST), body=None
        ),
        KeyError("x"),
    ],
)
def test_other_errors_are_not_transient(error):
    assert not is_transient_error(error)


def test_httpx_status_errors_read_the_response_status():
    def error(status):
        response = httpx.Response(status, request=_REQUEST)
        return httpx.HTTPStatusError("x", request=_REQUEST, response=response)

    assert is_transient_error(error(503))
    assert not is_transient_error(error(400))


def test_anthropic_errors_are_read_the_same_way():
    anthropic = pytest.importorskip("anthropic")

    def status(code):
        response = httpx.Response(code, request=_REQUEST)
        return anthropic.APIStatusError("x", response=response, body=None)

    assert is_transient_error(status(529))  # overloaded
    assert is_transient_error(status(429))
    assert not is_transient_error(status(400))
    assert is_transient_error(anthropic.APITimeoutError(request=_REQUEST))
    assert is_transient_error(anthropic.APIConnectionError(request=_REQUEST))


def test_google_errors_are_read_by_their_code():
    errors = pytest.importorskip("google.genai.errors")

    assert is_transient_error(errors.ServerError(503, {"error": {"code": 503}}))
    assert is_transient_error(errors.ClientError(429, {"error": {"code": 429}}))
    assert not is_transient_error(errors.ClientError(400, {"error": {"code": 400}}))


def test_litellm_errors_are_read_the_same_way():
    litellm = pytest.importorskip("litellm")

    assert is_transient_error(litellm.RateLimitError("x", llm_provider="azure", model="m"))
    assert is_transient_error(litellm.Timeout("x", model="m", llm_provider="azure"))
    assert not is_transient_error(litellm.BadRequestError("x", model="m", llm_provider="azure"))


def test_a_code_attribute_outside_google_is_not_a_status():
    class OtherError(Exception):
        code = 503

    assert not is_transient_error(OtherError())


class _Calls:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.count = 0

    def __call__(self):
        self.count += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_a_transient_failure_is_tried_again_with_growing_waits():
    waits = []
    call = _Calls(_openai_status(429), _openai_status(503), "ok")
    assert with_retries(call, sleep=waits.append) == "ok"
    assert (call.count, waits) == (3, [1, 2])


def test_a_refused_request_is_raised_at_once_without_waiting():
    waits = []
    call = _Calls(_openai_status(400), "never")
    with pytest.raises(openai.BadRequestError):
        with_retries(call, sleep=waits.append)
    assert (call.count, waits) == (1, [])


def test_the_last_transient_failure_is_raised():
    waits = []
    call = _Calls(*[_openai_status(503)] * 4)
    with pytest.raises(openai.InternalServerError):
        with_retries(call, tries=4, sleep=waits.append)
    assert (call.count, waits) == (4, [1, 2, 4])


def test_tries_must_be_positive():
    with pytest.raises(ValueError):
        with_retries(lambda: None, tries=0)


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("slow", request=_REQUEST),
        httpx.PoolTimeout("busy", request=_REQUEST),
        httpx.ReadError("reset", request=_REQUEST),
        httpx.WriteError("broken pipe", request=_REQUEST),
        httpx.RemoteProtocolError("server hung up", request=_REQUEST),
    ],
)
def test_httpx_timeouts_and_network_errors_are_transient(error):
    assert is_transient_error(error)


@pytest.mark.parametrize(
    "error",
    [
        httpx.UnsupportedProtocol("ftp://", request=_REQUEST),
        httpx.ProxyError("proxy refused", request=_REQUEST),
        httpx.LocalProtocolError("bad header", request=_REQUEST),
    ],
)
def test_httpx_errors_that_repeat_on_every_try_are_not_transient(error):
    assert not is_transient_error(error)


def _wrapped(cls, cause):
    try:
        raise cls(request=_REQUEST) from cause
    except cls as error:
        return error


def test_an_sdk_connection_error_is_judged_by_the_httpx_error_under_it():
    unsupported = httpx.UnsupportedProtocol("ftp://", request=_REQUEST)
    reset = httpx.ReadError("reset", request=_REQUEST)
    assert not is_transient_error(_wrapped(openai.APIConnectionError, unsupported))
    assert is_transient_error(_wrapped(openai.APIConnectionError, reset))
    # Without an httpx cause the SDK's own word stands.
    assert is_transient_error(_wrapped(openai.APIConnectionError, OSError("down")))
