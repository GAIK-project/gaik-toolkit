"""AudioToStructuredData transcribes again when a field named in retry_when_empty comes back empty."""

from types import SimpleNamespace

import pytest

from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_modules.audio_to_structured_data import pipeline as module

CONFIG = {"provider": "openai", "api_key": "test-key", "model": "test-model"}
REQUIREMENTS = ExtractionRequirements(
    use_case_name="fault_report",
    fields=[
        # Nullable, as in a wizard schema that leaves unstated values null.
        FieldSpec(field_name="reporter", field_type="str", description="Reporter", nullable=True),
        FieldSpec(field_name="asset_id", field_type="str", description="Asset", nullable=True),
        # Required but legitimately empty for this audio.
        FieldSpec(field_name="decision", field_type="str", description="Reviewer decision"),
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
                    "reporter": "Test Person" if found else None,
                    "asset_id": "A-1" if found else None,
                    "decision": "",
                    "note": None,
                }
            ]

    monkeypatch.setattr(module, "Transcriber", lambda **kwargs: SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(module, "DataExtractor", Extractor)
    return calls


WATCH = ["reporter", "asset_id"]


def _run(**kwargs):
    kwargs.setdefault("retry_when_empty", WATCH)
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
    assert result.empty_fields == []


def test_empty_required_field_triggers_one_retry(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == FULL
    assert result.extracted_fields[0]["asset_id"] == "A-1"
    assert result.transcription_attempts == 2
    assert result.empty_fields == []


def test_worse_retry_keeps_the_first_run(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == CUT
    assert result.transcription_attempts == 2
    assert result.empty_fields == ["reporter", "asset_id"]


def test_no_watched_fields_never_retries(monkeypatch):
    # The default: an empty required field ("decision") alone does not retry.
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run(retry_when_empty=None)
    assert calls["transcribe"] == 1
    assert result.transcription_attempts == 1
    assert result.empty_fields == []


def test_empty_unwatched_field_does_not_retry(monkeypatch):
    calls = _install(monkeypatch, [FULL, FULL])
    _run(retry_when_empty=["reporter"])
    assert calls["transcribe"] == 1


def test_unknown_field_name_is_refused_before_transcribing(monkeypatch):
    calls = _install(monkeypatch, [FULL])
    with pytest.raises(ValueError, match="asset_identifier"):
        _run(retry_when_empty=["asset_identifier"])
    assert calls["transcribe"] == 0


@pytest.mark.parametrize("bad", ["reporter", [""], [1]])
def test_retry_when_empty_must_be_a_list_of_names(monkeypatch, bad):
    calls = _install(monkeypatch, [FULL])
    with pytest.raises(ValueError, match="retry_when_empty"):
        _run(retry_when_empty=bad)
    assert calls["transcribe"] == 0


def test_retries_can_be_turned_off(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run(transcription_retries=0)
    assert calls["transcribe"] == 1
    assert result.empty_fields == ["reporter", "asset_id"]


def test_retry_count_is_honoured(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT, FULL])
    result = _run(transcription_retries=2)
    assert calls["transcribe"] == 3
    assert result.transcription_attempts == 3
    assert result.empty_fields == []


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
    assert module._empty_fields([{"site": "unknown"}], [spec]) == ["site"]
    assert module._empty_fields([{"site": "Plant 2"}], [spec]) == []


def test_no_records_counts_every_watched_field_as_empty():
    spec = FieldSpec(field_name="site", field_type="str", description="Site")
    assert module._empty_fields([], [spec]) == ["site"]
