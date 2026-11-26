"""AudioToStructuredData transcribes again when a required field comes back empty."""

from types import SimpleNamespace

import pytest

from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_modules.audio_to_structured_data import pipeline as module

CONFIG = {"provider": "openai", "api_key": "test-key", "model": "test-model"}
REQUIREMENTS = ExtractionRequirements(
    use_case_name="fault_report",
    fields=[
        FieldSpec(field_name="reporter", field_type="str", description="Reporter"),
        FieldSpec(field_name="asset_id", field_type="str", description="Asset"),
        FieldSpec(field_name="note", field_type="str", description="Note", nullable=True),
    ],
)
FULL = "Reporter Test Person, asset A-1. The pump leaks."
CUT = "The pump leaks."


def _install(monkeypatch, transcripts):
    """Fake the transcriber with ``transcripts`` in call order; return the call log."""
    calls = {"transcribe": 0, "extract": []}

    def transcribe(**kwargs):
        text = transcripts[calls["transcribe"]]
        calls["transcribe"] += 1
        return SimpleNamespace(raw_transcript=text, enhanced_transcript=None)

    class Extractor:
        def __init__(self, config, **kwargs):
            pass

        def extract(self, **kwargs):
            text = kwargs["documents"][0]
            calls["extract"].append(text)
            found = text == FULL
            return [
                {
                    "reporter": "Test Person" if found else "",
                    "asset_id": "A-1" if found else "",
                    "note": None,
                }
            ]

    monkeypatch.setattr(module, "Transcriber", lambda **kwargs: SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(module, "DataExtractor", Extractor)
    return calls


def _run(**kwargs):
    return module.AudioToStructuredData(api_config=CONFIG).run(
        file_path="synthetic.wav",
        user_requirements="reporter, asset id, note",
        schema=type("Schema", (), {}),
        requirements=REQUIREMENTS,
        **kwargs,
    )


def test_complete_first_run_is_not_retried(monkeypatch):
    calls = _install(monkeypatch, [FULL])
    result = _run()
    assert calls["transcribe"] == 1
    assert result.transcription_attempts == 1
    assert result.missing_required_fields == []


def test_empty_required_field_triggers_one_retry(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == FULL
    assert result.extracted_fields[0]["asset_id"] == "A-1"
    assert result.transcription_attempts == 2
    assert result.missing_required_fields == []


def test_worse_retry_keeps_the_first_run(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == CUT
    assert result.transcription_attempts == 2
    assert result.missing_required_fields == ["reporter", "asset_id"]


def test_nullable_field_does_not_trigger_retry(monkeypatch):
    # "note" is None in every run, but it may be null.
    calls = _install(monkeypatch, [FULL, FULL])
    _run()
    assert calls["transcribe"] == 1


def test_retries_can_be_turned_off(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run(transcription_retries=0)
    assert calls["transcribe"] == 1
    assert result.missing_required_fields == ["reporter", "asset_id"]


def test_retry_count_is_honoured(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT, FULL])
    result = _run(transcription_retries=2)
    assert calls["transcribe"] == 3
    assert result.transcription_attempts == 3
    assert result.missing_required_fields == []


@pytest.mark.parametrize("bad", [-1, 1.5, True, "1"])
def test_invalid_retry_count_is_refused_before_transcribing(monkeypatch, bad):
    calls = _install(monkeypatch, [FULL])
    with pytest.raises(ValueError, match="transcription_retries"):
        _run(transcription_retries=bad)
    assert calls["transcribe"] == 0


def test_explicit_default_counts_as_empty():
    spec = FieldSpec(
        field_name="site",
        field_type="str",
        description="Site",
        default="unknown",
        has_explicit_default=True,
    )
    reqs = ExtractionRequirements(use_case_name="x", fields=[spec])
    assert module._missing_required_fields([{"site": "unknown"}], reqs) == ["site"]
    assert module._missing_required_fields([{"site": "Plant 2"}], reqs) == []


def test_requirements_without_fields_report_nothing():
    assert module._missing_required_fields([{"value": ""}], object()) == []
