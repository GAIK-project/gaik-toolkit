"""Errors from direct HTTP calls to Gemini and the Docling service carry no key or body.

The raised message names the service, the kind of error and the HTTP status. The
response body, the URL and the headers stay out of it; the body and the URL without
its query string go to the debug log only.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
import requests
from pydantic import BaseModel

pytest.importorskip("fitz")
pytest.importorskip("markdown_it")

from gaik.software_components import _http  # noqa: E402
from gaik.software_components.parsers.docling_api_client import (  # noqa: E402
    DoclingApiClientParser,
)
from gaik.software_components.parsers.multimodal_parser import (  # noqa: E402
    multimodal_parser,
)
from gaik.software_components.vision_extractor import vision_extractor  # noqa: E402

KEY = "test-key-123"
BODY = '{"error": {"message": "quota for project 4711 exceeded", "detail": "body-only"}}'


def _http_error_response(status: int, reason: str) -> requests.Response:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/m:generateContent?key={KEY}"
    response = requests.Response()
    response.status_code = status
    response.reason = reason
    response._content = BODY.encode()
    response.url = url
    response.headers["Retry-After"] = "7"
    response.headers["X-Debug-Echo"] = KEY
    response.request = requests.Request("POST", url, headers={"x-goog-api-key": KEY}).prepare()
    return response


def _call_parser(tmp_path):
    parser = SimpleNamespace(
        config={"vertex_ai": False, "api_key": KEY, "model": "gemini-test"},
        reasoning_effort="low",
    )
    return multimodal_parser.MultimodalParser._call_google(
        parser, tmp_path / "doc.pdf", "system", "user"
    )


def _call_extractor(tmp_path):
    class Answer(BaseModel):
        answer: str

    extractor = SimpleNamespace(
        config={"vertex_ai": False, "api_key": KEY}, model="gemini-test", reasoning_effort="low"
    )
    return vision_extractor.VisionExtractor._call_google(extractor, [], "system", "user", Answer)


@pytest.fixture(params=[_call_parser, _call_extractor], ids=["multimodal_parser", "vision"])
def call_gemini(request, monkeypatch):
    monkeypatch.setattr(multimodal_parser, "_build_google_body", lambda *a, **k: {})
    return request.param


def _assert_short(message: str) -> None:
    assert KEY not in message
    assert "key=" not in message
    assert "googleapis" not in message
    assert "body-only" not in message and "4711" not in message


def test_a_failed_gemini_call_raises_only_the_status(call_gemini, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _http_error_response(429, "Too Many"))

    with caplog.at_level(logging.DEBUG, logger=_http.__name__):
        with pytest.raises(requests.HTTPError) as caught:
            call_gemini(tmp_path)

    assert str(caught.value) == "Gemini request failed: HTTP 429 Too Many"
    # The status and Retry-After stay for a caller's back-off; nothing else does.
    stripped = caught.value.response
    assert stripped.status_code == 429 and stripped.headers["Retry-After"] == "7"
    assert stripped.text == "" and stripped.url is None and stripped.request is None
    assert caught.value.request is None
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    # The detail is in the debug log, with the URL cut before its query string.
    assert "body-only" in caplog.text
    assert "googleapis.com/v1beta/models/gemini-test:generateContent" in caplog.text
    assert KEY not in caplog.text and "key=" not in caplog.text


def test_a_gemini_connection_error_keeps_its_type_without_the_url(
    call_gemini, monkeypatch, tmp_path
):
    def fail(*_a, **_k):
        raise requests.ConnectTimeout(
            f"HTTPSConnectionPool(host='h', port=443): Max retries exceeded with url: /v?key={KEY}"
        )

    monkeypatch.setattr(requests, "post", fail)

    with pytest.raises(requests.ConnectTimeout) as caught:
        call_gemini(tmp_path)

    assert str(caught.value) == "Gemini request failed: ConnectTimeout"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}, "echo": "body-only"}, "block reason SAFETY"),
        (
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]},
            "finish reason MAX_TOKENS",
        ),
    ],
)
def test_an_empty_gemini_answer_names_only_its_reason(
    call_gemini, monkeypatch, tmp_path, caplog, payload, reason
):
    payload = {**payload, "modelVersion": "body-only", "usageMetadata": {"totalTokenCount": 3}}
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload),
    )

    with caplog.at_level(logging.DEBUG, logger=_http.__name__):
        with pytest.raises(ValueError) as caught:
            call_gemini(tmp_path)

    assert reason in str(caught.value)
    _assert_short(str(caught.value))
    assert "totalTokenCount" in caplog.text and "body-only" not in caplog.text


def test_a_failed_docling_call_raises_only_the_status(monkeypatch, tmp_path, capsys):
    document = tmp_path / "doc.pdf"
    document.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None, json=dict)
    )
    monkeypatch.setattr(requests, "post", lambda *a, **k: _http_error_response(401, "Unauthorized"))
    parser = DoclingApiClientParser(
        api_base="https://parse.example",
        password="pw-secret",
        allowed_endpoint_hosts=["parse.example"],
    )

    with pytest.raises(requests.HTTPError) as caught:
        parser.parse_document(document)

    assert str(caught.value) == "Docling service request failed: HTTP 401 Unauthorized"
    printed = capsys.readouterr().out
    assert "body-only" not in printed and "pw-secret" not in printed


def test_url_for_log_drops_user_info_query_and_fragment():
    url = "https://user:pw@host.example:8443/v1/models/m:generate?key=abc&x=1#part"
    assert _http.url_for_log(url) == "https://host.example:8443/v1/models/m:generate"
