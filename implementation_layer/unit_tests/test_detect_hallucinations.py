"""Unit tests for LLMJudge.detect_hallucinations()."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from gaik.software_components.validators.llm_judge import (
    HALLUCINATION_SYSTEM_PROMPT,
    HallucinationFlag,
    HallucinationReport,
    LLMJudge,
    build_hallucination_prompt,
    parse_hallucination_flags,
)

# ── parse_hallucination_flags ───────────────────────────────────────


def test_parse_hallucination_flags_clean_json():
    raw = (
        '{"flags": ['
        '{"field": "org", "value": "Luvata Pori Oy", "severity": "wrong",'
        ' "reason": "Speaker did not name an employer."}'
        "]}"
    )
    flags = parse_hallucination_flags(raw)
    assert len(flags) == 1
    assert flags[0].field == "org"
    assert flags[0].value == "Luvata Pori Oy"
    assert flags[0].severity == "wrong"


def test_parse_hallucination_flags_drops_ok_entries():
    """The judge should only emit non-ok entries, but be defensive anyway."""
    raw = (
        '{"flags": ['
        '{"field": "name", "value": "Matti", "severity": "ok", "reason": "stated"},'
        '{"field": "org", "value": "Luvata", "severity": "wrong", "reason": "no"}'
        "]}"
    )
    flags = parse_hallucination_flags(raw)
    assert len(flags) == 1
    assert flags[0].field == "org"


def test_parse_hallucination_flags_with_markdown_fence():
    raw = (
        "```json\n"
        '{"flags": [{"field": "x", "value": "y", "severity": "suspect", "reason": "z"}]}\n'
        "```"
    )
    flags = parse_hallucination_flags(raw)
    assert len(flags) == 1
    assert flags[0].severity == "suspect"


def test_parse_hallucination_flags_unparseable_returns_empty():
    flags = parse_hallucination_flags("not json")
    assert flags == []


def test_parse_hallucination_flags_skips_invalid_entries():
    raw = (
        '{"flags": ['
        "null,"
        '{"field": "", "value": "x", "severity": "wrong", "reason": "missing field name"},'
        '{"field": "good", "value": "v", "severity": "wrong", "reason": "real flag"}'
        "]}"
    )
    flags = parse_hallucination_flags(raw)
    assert len(flags) == 1
    assert flags[0].field == "good"


# ── build_hallucination_prompt ──────────────────────────────────────


def test_build_hallucination_prompt_contains_source_and_extracted():
    prompt = build_hallucination_prompt(
        source_text="Test transcript here.",
        extracted={"foo": "bar"},
    )
    assert "Test transcript here." in prompt
    assert '"foo"' in prompt and '"bar"' in prompt


def test_build_hallucination_prompt_includes_field_descriptions_when_given():
    prompt = build_hallucination_prompt(
        source_text="x",
        extracted={"a": "b"},
        field_descriptions={"a": "field a description"},
    )
    assert "Field rules" in prompt
    assert "field a description" in prompt


def test_build_hallucination_prompt_no_field_rules_block_when_omitted():
    prompt = build_hallucination_prompt(source_text="x", extracted={"a": "b"})
    assert "Field rules" not in prompt


def test_hallucination_system_prompt_describes_severity_classes():
    assert "wrong" in HALLUCINATION_SYSTEM_PROMPT
    assert "suspect" in HALLUCINATION_SYSTEM_PROMPT
    assert "empty" in HALLUCINATION_SYSTEM_PROMPT.lower()


# ── LLMJudge.detect_hallucinations ──────────────────────────────────


def test_detect_hallucinations_empty_source_raises():
    judge = LLMJudge(model_provider="azure")
    with pytest.raises(ValueError, match="empty"):
        judge.detect_hallucinations("", {"foo": "bar"})


def test_detect_hallucinations_short_circuits_when_extracted_all_empty():
    judge = LLMJudge(model_provider="azure")
    with patch.object(judge, "_dispatch_text") as dispatch:
        report = judge.detect_hallucinations(
            source_text="some text",
            extracted={"a": "", "b": None},
        )
    dispatch.assert_not_called()
    assert isinstance(report, HallucinationReport)
    assert report.flags == []


def test_detect_hallucinations_returns_flags():
    judge = LLMJudge(model_provider="azure")
    fake = (
        '{"flags": [{"field": "org", "value": "Luvata Pori Oy",'
        ' "severity": "wrong", "reason": "Speaker did not name an employer"}]}'
    )
    with patch.object(judge, "_dispatch_text", return_value=(fake, 100, 30)) as dispatch:
        report = judge.detect_hallucinations(
            source_text="Moi, täällä Matti Möttönen. 26.8.25 huomasin pihalla...",
            extracted={"name": "Matti Möttönen", "org": "Luvata Pori Oy"},
        )
    dispatch.assert_called_once()
    assert len(report.flags) == 1
    assert isinstance(report.flags[0], HallucinationFlag)
    assert report.flags[0].field == "org"
    assert report.flags[0].severity == "wrong"
    assert report.usage.input_tokens == 100
    assert report.usage.output_tokens == 30


def test_detect_hallucinations_drops_empty_fields_before_dispatch():
    judge = LLMJudge(model_provider="azure")
    captured = {}

    def fake_dispatch(user_prompt, system_prompt):
        captured["user"] = user_prompt
        return ('{"flags": []}', 50, 10)

    with patch.object(judge, "_dispatch_text", side_effect=fake_dispatch):
        judge.detect_hallucinations(
            source_text="src",
            extracted={"keep": "value", "drop_empty": "", "drop_none": None},
        )
    assert "drop_empty" not in captured["user"]
    assert "drop_none" not in captured["user"]
    assert "keep" in captured["user"]


def test_detect_hallucinations_passes_field_descriptions_through():
    judge = LLMJudge(model_provider="azure")
    captured = {}

    def fake_dispatch(user_prompt, system_prompt):
        captured["user"] = user_prompt
        return ('{"flags": []}', 60, 5)

    with patch.object(judge, "_dispatch_text", side_effect=fake_dispatch):
        judge.detect_hallucinations(
            source_text="src",
            extracted={"a": "v"},
            field_descriptions={"a": "rule for a"},
        )
    assert "rule for a" in captured["user"]
