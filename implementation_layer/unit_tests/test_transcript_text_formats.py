"""Subtitle text, saving and enhancement edge cases from issue #143."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_components.enhance_transcript.enhance_transcript import TranscriptEnhancer
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.parallel_transcriber.models import TranscriptionResult
from gaik.software_components.parallel_transcriber.srt import extract_text_from_srt
from gaik.software_components.transcriber.srt_utils import segments_to_srt, segments_to_vtt

_SRT = (
    "1\n00:00:00,000 --> 00:00:01,000\nHammas numero\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\n36\n\n"
    "3\n00:00:02,000 --> 00:00:03,000\nvuonna\n\n"
    "4\n00:00:03,000 --> 00:00:04,000\n2024\n"
)


def test_srt_text_keeps_cues_that_are_only_digits():
    assert extract_text_from_srt(_SRT) == "Hammas numero 36 vuonna 2024"


def test_vtt_plain_text_has_no_header():
    vtt = "WEBVTT\n\n" + _SRT.replace(",", ".")
    result = TranscriptionResult(content=vtt, format="vtt", language="fi", model_used="m")

    assert result.plain_text == "Hammas numero 36 vuonna 2024"


def test_save_into_a_folder_that_does_not_exist_yet(tmp_path: Path):
    result = TranscriptionResult(content=_SRT, format="srt", language="fi", model_used="m")

    written = result.save(f"{tmp_path / 'output'}/")

    assert written == tmp_path / "output" / "transcription.srt"
    assert written.read_text(encoding="utf-8") == _SRT


_SEGMENTS = [
    {"start": 0.0, "end": 2.3, "text": "Ensimmäinen"},
    {"start": 2.3, "end": 3.0, "text": "  "},
    {"start": 3.0, "end": 4.7, "text": "Toinen"},
]


def test_srt_rounds_milliseconds_and_numbers_cues_without_gaps():
    srt = segments_to_srt(_SEGMENTS)

    assert "00:00:00,000 --> 00:00:02,300" in srt
    assert "00:00:03,000 --> 00:00:04,700" in srt
    assert [line for line in srt.split("\n") if line.isdigit()] == ["1", "2"]


def test_vtt_rounds_milliseconds_and_numbers_cues_without_gaps():
    vtt = segments_to_vtt(_SEGMENTS)

    assert "00:00:00.000 --> 00:00:02.300" in vtt
    assert [line for line in vtt.split("\n") if line.isdigit()] == ["1", "2"]


def _enhancer(client) -> TranscriptEnhancer:
    enhancer = object.__new__(TranscriptEnhancer)
    enhancer.client = client
    enhancer.model = "gpt-4.1"
    enhancer.reasoning_effort = None
    enhancer.api_config = {}
    return enhancer


@pytest.mark.parametrize(("finish_reason", "expected"), [("length", "raw"), ("stop", "fixed")])
def test_enhancement_cut_off_at_the_token_limit_keeps_the_input(finish_reason, expected):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(finish_reason=finish_reason, message=SimpleNamespace(content="fixed"))
        ]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )

    assert _enhancer(client)._chat_text([], fallback="raw") == expected


class _Provider:
    provider = "p"
    model = "m"

    raw = None

    def __init__(self, answer_raw) -> None:
        self.answer_raw = answer_raw

    def chat(self, messages, **kwargs):
        return ChatResponse(text="fixed", model="m", provider="p", raw=self.answer_raw)

    def chat_parsed(self, messages, schema, **kwargs):
        raise NotImplementedError

    def chat_stream(self, messages, **kwargs):
        raise NotImplementedError

    def embed(self, texts, **kwargs):
        raise NotImplementedError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (SimpleNamespace(stop_reason="max_tokens"), "raw"),
        (SimpleNamespace(stop_reason="end_turn"), "fixed"),
        (SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")]), "raw"),
        (None, "fixed"),
    ],
)
def test_provider_answer_cut_off_at_the_token_limit_keeps_the_input(raw, expected):
    assert _enhancer(_Provider(raw))._chat_text([], fallback="raw") == expected
