"""A model reply cut off at its token cap is not passed off as the whole document.

VisionParser merges the pages of a PDF with one cleanup call (clean_output=True, the
default). When that reply stopped at max_tokens, it replaced the complete per-page
Markdown and the later pages were lost without an error. MultimodalParser had no check
of a stop reason either. Also here: the cleanup's code-fence language tag, and the
multimodal cleaner that dropped nested and out-of-div text.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import fitz
import pytest
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.parsers._cut_off import Reply, reply_cut_off
from gaik.software_components.parsers.multimodal_parser import MultimodalParser
from gaik.software_components.parsers.multimodal_parser import multimodal_parser as multimodal
from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser


@pytest.mark.parametrize(
    ("raw", "cut_off"),
    [
        # OpenAI Chat Completions and LiteLLM.
        (SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")]), True),
        (SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop")]), False),
        # OpenAI Responses API.
        (
            SimpleNamespace(
                status="incomplete",
                incomplete_details=SimpleNamespace(reason="max_output_tokens"),
            ),
            True,
        ),
        (SimpleNamespace(status="completed", incomplete_details=None), False),
        # Anthropic.
        (SimpleNamespace(stop_reason="max_tokens"), True),
        (SimpleNamespace(stop_reason="end_turn"), False),
        # Gemini: the SDK's enum and the REST JSON.
        (
            SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))]
            ),
            True,
        ),
        (
            SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))]
            ),
            False,
        ),
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, True),
        ({"candidates": [{"finishReason": "STOP"}]}, False),
        # No stop reason to read.
        (None, False),
        (SimpleNamespace(), False),
        ({}, False),
        (MagicMock(), False),
    ],
)
def test_reply_cut_off_reads_each_providers_stop_reason(raw, cut_off):
    assert reply_cut_off(raw) is cut_off


def _two_page_pdf(path):
    with fitz.open() as document:
        document.new_page().insert_text((20, 20), "First page")
        document.new_page().insert_text((20, 20), "Second page")
        document.save(path)
    return path


class _Completions:
    """Page replies, then the cleanup reply with its finish reason."""

    def __init__(self, cleanup: str, finish_reason: str) -> None:
        self.replies = [("# Page 1", "stop"), ("# Page 2", "stop"), (cleanup, finish_reason)]

    def create(self, **kwargs):
        content, finish_reason = self.replies.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content), finish_reason=finish_reason
                )
            ],
            usage=None,
        )


def _vision_parser(monkeypatch, completions):
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(VisionParser, "_initialize_client", lambda self: client)
    return VisionParser(OpenAIConfig(model="gpt-test", use_azure=False, api_key="test"))


def test_a_cut_off_cleanup_returns_the_pages_as_parsed(monkeypatch, tmp_path, caplog):
    parser = _vision_parser(monkeypatch, _Completions("# Page 1\n\n# Pa", "length"))
    pdf = _two_page_pdf(tmp_path / "long.pdf")

    with caplog.at_level(logging.WARNING):
        pages = parser.convert_pdf(str(pdf))

    assert pages == ["# Page 1", "# Page 2"]
    assert "stopped at max_tokens=16000" in caplog.text
    assert "long" not in caplog.text


@pytest.mark.parametrize("cleanup", ["", None])
def test_a_cleanup_cut_off_before_any_text_returns_the_pages(monkeypatch, tmp_path, cleanup):
    # A reasoning model can spend the whole budget before it writes anything.
    parser = _vision_parser(monkeypatch, _Completions(cleanup, "length"))

    assert parser.convert_pdf(str(_two_page_pdf(tmp_path / "a.pdf"))) == ["# Page 1", "# Page 2"]


@pytest.mark.parametrize("content", ["", None])
def test_a_page_cut_off_before_any_text_raises(monkeypatch, content):
    # As before for an empty reply: a page must not come back empty without an error.
    completions = SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="length")
            ],
            usage=None,
        )
    )
    parser = _vision_parser(monkeypatch, completions)

    with pytest.raises(RuntimeError, match="empty content: the reply stopped at max_tokens"):
        parser._parse_image(b"image", page=1, previous_context=None)


def test_a_page_cut_off_after_some_text_keeps_it(monkeypatch, caplog):
    completions = SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="# Pa"), finish_reason="length")
            ],
            usage=None,
        )
    )
    parser = _vision_parser(monkeypatch, completions)

    with caplog.at_level("WARNING"):
        assert parser._parse_image(b"image", page=2, previous_context=None) == "# Pa"
    assert "Page 2: the reply stopped" in caplog.text


def test_a_finished_cleanup_still_replaces_the_pages(monkeypatch, tmp_path):
    parser = _vision_parser(monkeypatch, _Completions("# Page 1\n\n# Page 2", "stop"))

    assert parser.convert_pdf(str(_two_page_pdf(tmp_path / "a.pdf"))) == ["# Page 1\n\n# Page 2"]


def test_an_empty_finished_cleanup_still_raises(monkeypatch, tmp_path):
    parser = _vision_parser(monkeypatch, _Completions("", "stop"))

    with pytest.raises(RuntimeError, match="Cleanup LLM returned empty output"):
        parser.convert_pdf(str(_two_page_pdf(tmp_path / "a.pdf")))


def test_a_cut_off_cleanup_through_a_shared_client_returns_the_pages(monkeypatch):
    from gaik.software_components.parsers import vision

    class Client:
        model = "vision-model"
        provider = "anthropic"
        raw = None

        def chat(self, messages, **kwargs):
            return ChatResponse(
                text="# Merged but cut",
                model=self.model,
                provider=self.provider,
                raw=SimpleNamespace(stop_reason="max_tokens"),
            )

        def chat_parsed(self, *args, **kwargs):
            raise AssertionError

        def chat_stream(self, *args, **kwargs):
            raise AssertionError

        def embed(self, *args, **kwargs):
            raise AssertionError

    monkeypatch.setattr(vision, "create_llm_client", lambda config: Client())
    parser = VisionParser({"provider": "anthropic", "model": "vision-model", "api_key": "k"})

    assert parser._clean_markdown(["first", "second"]) is None


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("```markdown\n# Title\n\nText\n```", "# Title\n\nText"),
        ("```md\n# Title\n```", "# Title"),
        ("```\n# Title\n```", "# Title"),
        # A wrapper that never closes.
        ("```markdown\n# Title", "# Title"),
        # A code block that opens the document is the document's own.
        ("```python\nprint(1)\n```\n\nText after", "```python\nprint(1)\n```\n\nText after"),
        ("# Title\n\n```json\n{}\n```", "# Title\n\n```json\n{}\n```"),
        ("No fence", "No fence"),
        # A wrapper around a document that holds its own code blocks.
        (
            "```markdown\n# T\n\n```py\nx\n```\n\ntext\n```",
            "# T\n\n```py\nx\n```\n\ntext",
        ),
        ("```\n# T\n```py\nx\n```\ntext\n```", "# T\n```py\nx\n```\ntext"),
        # An untagged inner block: the markdown tag says the outer fence is a wrapper.
        ("```markdown\n# T\n```\nx\n```\ntext\n```", "# T\n```\nx\n```\ntext"),
        # A wrapper that never closes, around a closed inner block.
        ("```markdown\n# T\n```py\nx\n```", "# T\n```py\nx\n```"),
        # Two code blocks of the document, at its start and its end.
        ("```py\na\n```\ntext\n```js\nb\n```", "```py\na\n```\ntext\n```js\nb\n```"),
        # CRLF line ends.
        (
            "```python\r\nprint(1)\r\n```\r\n\r\nText after",
            "```python\r\nprint(1)\r\n```\r\n\r\nText after",
        ),
        ("```markdown\r\n# Title\r\n```", "# Title"),
        # A four-backtick wrapper: a three-backtick fence inside it is its text.
        ("````markdown\n# T\n\n```py\nx\n```\n````", "# T\n\n```py\nx\n```"),
        ("````markdown\n# T\n```\nx\n```\n````", "# T\n```\nx\n```"),
        ("````\ncode\n```\nmore\n````", "code\n```\nmore"),
        # Tildes, and a tilde fence that a backtick fence does not close.
        ("~~~markdown\n# T\n~~~", "# T"),
        ("~~~markdown\n# T\n```py\nx\n```\n~~~", "# T\n```py\nx\n```"),
        # Two backticks are no fence.
        ("``markdown\n# T\n``", "``markdown\n# T\n``"),
    ],
)
def test_the_cleanup_takes_off_a_wrapping_fence_with_its_language_tag(monkeypatch, reply, expected):
    parser = _vision_parser(monkeypatch, SimpleNamespace())
    monkeypatch.setattr(parser, "_chat_content", lambda messages: Reply(reply))

    assert parser._clean_markdown(["first", "second"]) == expected


def _shared_parser(monkeypatch, raw):
    from gaik.software_components import llm

    class Client:
        raw = SimpleNamespace(close=lambda: None)

        def chat(self, messages, **kwargs):
            return ChatResponse(
                text="<div data-label='Text'>Name: Ada</div>",
                model="served-vision",
                provider="azure",
                raw=raw,
            )

    monkeypatch.setattr(llm, "create_llm_client", lambda config: Client())
    return MultimodalParser(api_config={"provider": "azure", "model": "m", "api_key": "k"})


def test_multimodal_parse_reports_a_cut_off_reply(monkeypatch, tmp_path, caplog):
    raw = SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")])
    parser = _shared_parser(monkeypatch, raw)

    with caplog.at_level(logging.WARNING):
        result = parser.parse(_two_page_pdf(tmp_path / "long.pdf"))

    assert result.truncated is True
    assert result.clean_markdown == "Name: Ada\n"
    assert "output-token cap" in caplog.text
    assert "long" not in caplog.text


def test_multimodal_parse_of_a_finished_reply_is_not_truncated(monkeypatch, tmp_path):
    raw = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop")])

    result = _shared_parser(monkeypatch, raw).parse(_two_page_pdf(tmp_path / "a.pdf"))

    assert result.truncated is False


def test_multimodal_gemini_rest_reply_cut_off_is_read(monkeypatch, tmp_path):
    payload = {
        "candidates": [{"content": {"parts": [{"text": "# Title"}]}, "finishReason": "MAX_TOKENS"}]
    }
    monkeypatch.setattr(multimodal, "_build_google_body", lambda *a, **k: {})
    monkeypatch.setattr(
        multimodal._http, "post", lambda *a, **k: SimpleNamespace(json=lambda: payload)
    )
    parser = SimpleNamespace(
        config={"vertex_ai": False, "api_key": "k", "model": "gemini-test"},
        reasoning_effort="low",
    )

    text, _usage = MultimodalParser._call_google(parser, tmp_path / "a.pdf", "system", "user")

    assert text == "# Title\n"
    assert text.cut_off is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Flat layout wrappers, as before.
        (
            '<div data-label="Title"># Report</div>\n<div data-label="Text">Body text</div>',
            "# Report\n\nBody text\n",
        ),
        # A div nested in another keeps both its text and the text after it.
        (
            '<div data-label="Table"><div data-label="Caption">Table 1</div>'
            "<table><tr><td>1</td></tr></table></div>",
            "Table 1\n\n<table><tr><td>1</td></tr></table>\n",
        ),
        # Text outside every div is kept, in its place.
        (
            'Intro line\n<div data-label="Text">Inside</div>\nClosing line',
            "Intro line\n\nInside\n\nClosing line\n",
        ),
        # No divs at all.
        ("# Plain\n\nText", "# Plain\n\nText\n"),
        ("", "\n"),
    ],
)
def test_multimodal_cleaner_keeps_nested_and_out_of_div_content(raw, expected):
    assert multimodal._clean_markdown(raw) == expected
