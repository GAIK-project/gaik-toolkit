"""Direct Gemini API calls send the key in a header, never in the URL."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

pytest.importorskip("fitz")
pytest.importorskip("markdown_it")

from gaik.software_components.parsers.multimodal_parser import (  # noqa: E402
    multimodal_parser,
)
from gaik.software_components.vision_extractor import vision_extractor  # noqa: E402

KEY = "test-key-123"


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _capture(monkeypatch, module, payload):
    calls = []

    def post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers})
        return _Response(payload)

    monkeypatch.setattr(module.requests, "post", post)
    return calls


def _assert_key_only_in_header(call):
    assert KEY not in call["url"]
    assert "key=" not in call["url"]
    assert call["url"].endswith(":generateContent")
    assert call["headers"]["x-goog-api-key"] == KEY


def test_multimodal_parser_sends_the_key_in_a_header(monkeypatch, tmp_path):
    payload = {"candidates": [{"content": {"parts": [{"text": "# Title"}]}}]}
    calls = _capture(monkeypatch, multimodal_parser, payload)
    monkeypatch.setattr(multimodal_parser, "_build_google_body", lambda *a, **k: {})
    parser = SimpleNamespace(
        config={"vertex_ai": False, "api_key": KEY, "model": "gemini-test"},
        reasoning_effort="low",
    )

    text, _usage = multimodal_parser.MultimodalParser._call_google(
        parser, tmp_path / "doc.pdf", "system", "user"
    )

    assert text.startswith("# Title")
    _assert_key_only_in_header(calls[0])


def test_vision_extractor_sends_the_key_in_a_header(monkeypatch):
    class Answer(BaseModel):
        answer: str

    payload = {"candidates": [{"content": {"parts": [{"text": '{"answer": "yes"}'}]}}]}
    calls = _capture(monkeypatch, vision_extractor, payload)
    extractor = SimpleNamespace(
        config={"vertex_ai": False, "api_key": KEY},
        model="gemini-test",
        reasoning_effort="low",
    )

    result, _usage = vision_extractor.VisionExtractor._call_google(
        extractor, [], "system", "user", Answer
    )

    assert result == {"answer": "yes"}
    _assert_key_only_in_header(calls[0])
