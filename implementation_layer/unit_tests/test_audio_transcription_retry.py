"""AudioToStructuredData transcribes again when a field named in retry_when_empty is empty."""

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
HALF = "Reporter Test Person. The pump leaks."
CUT = "The pump leaks."


class RateLimitedError(Exception):
    """Stands in for a provider's 429."""

    status_code = 429


class RefusedError(Exception):
    """Stands in for a refusal that would come back on every try."""

    status_code = 400


def _record(text):
    return {
        "reporter": "Test Person" if text in (FULL, HALF) else None,
        "asset_id": "A-1" if text == FULL else None,
        "decision": "",
        "note": None,
    }


def _install(monkeypatch, transcripts, nested=False):
    """Fake the transcriber with ``transcripts`` in call order; return the call log.

    An exception in ``transcripts`` is raised by that call. With ``nested`` the
    extractor answers as for a nested-list schema: the fields are in the items.
    """
    calls = {"transcribe": 0, "extract": [], "save_json": []}

    def transcribe(**kwargs):
        text = transcripts[calls["transcribe"]]
        calls["transcribe"] += 1
        if isinstance(text, Exception):
            raise text
        return SimpleNamespace(raw_transcript=text, enhanced_transcript=None)

    class Extractor:
        def __init__(self, config, **kwargs):
            pass

        def extract(self, **kwargs):
            text = kwargs["documents"][0]
            calls["extract"].append(text)
            calls["save_json"].append(kwargs.get("save_json"))
            if nested:
                return [{"incidents": [_record(text), {**_record(CUT), "note": "second"}]}]
            return [_record(text)]

    monkeypatch.setattr(
        module, "Transcriber", lambda **kwargs: SimpleNamespace(transcribe=transcribe)
    )
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


def test_empty_watched_field_triggers_one_retry(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == FULL
    assert result.extracted_fields[0]["asset_id"] == "A-1"
    assert result.transcription_attempts == 2
    assert result.empty_fields == []


def test_worse_retry_keeps_the_first_run(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT])
    result = _run(transcription_retries=1)
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


@pytest.mark.parametrize("bad", ["reporter", [""], [1], 5, b"reporter"])
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


def test_default_makes_two_retries(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT, FULL])
    result = _run()
    assert calls["transcribe"] == 3
    assert result.transcription_attempts == 3
    assert result.empty_fields == []


def test_retry_count_caps_the_retries(monkeypatch):
    calls = _install(monkeypatch, [CUT, CUT, FULL])
    result = _run(transcription_retries=1)
    assert calls["transcribe"] == 2
    assert result.empty_fields == ["reporter", "asset_id"]


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


def test_a_generator_of_names_is_read_once_and_kept(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    result = _run(retry_when_empty=(name for name in WATCH))
    assert calls["transcribe"] == 2
    assert result.empty_fields == []


# --- nested-list schema: the named fields are in the items ------------------


def test_nested_items_that_state_the_fields_are_not_retried(monkeypatch):
    # The second item has no reporter; the first does, so the audio stated it.
    calls = _install(monkeypatch, [FULL], nested=True)
    result = _run()
    assert calls["transcribe"] == 1
    assert result.empty_fields == []


def test_nested_items_without_the_fields_are_retried(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL], nested=True)
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == FULL
    assert result.empty_fields == []


def test_nested_container_without_items_counts_every_field_as_empty():
    spec = FieldSpec(field_name="reporter", field_type="str", description="Reporter")
    req = ExtractionRequirements(use_case_name="uc", fields=[spec])
    assert module._empty_fields([{"incidents": []}], [spec], req) == ["reporter"]


# --- a retry that fails keeps the best result -------------------------------


def test_a_transient_error_on_a_retry_uses_that_try_and_tries_again(monkeypatch):
    calls = _install(monkeypatch, [CUT, RateLimitedError(), FULL])
    result = _run()
    assert calls["transcribe"] == 3
    assert result.transcription.raw_transcript == FULL
    assert result.transcription_attempts == 3
    assert result.empty_fields == []


def test_another_error_on_a_retry_ends_the_retries_with_the_first_result(monkeypatch):
    calls = _install(monkeypatch, [CUT, RefusedError(), FULL])
    result = _run()
    assert calls["transcribe"] == 2
    assert result.transcription.raw_transcript == CUT
    assert result.empty_fields == ["reporter", "asset_id"]


def test_transient_errors_on_every_retry_keep_the_first_result(monkeypatch):
    calls = _install(monkeypatch, [CUT, RateLimitedError(), TimeoutError()])
    result = _run()
    assert calls["transcribe"] == 3
    assert result.transcription.raw_transcript == CUT
    assert result.transcription_attempts == 3


def test_an_error_on_the_first_transcription_still_raises(monkeypatch):
    _install(monkeypatch, [RateLimitedError()])
    with pytest.raises(RateLimitedError):
        _run()


# --- save_json writes the result returned -----------------------------------


def test_save_json_writes_the_result_returned_not_the_last_attempt(monkeypatch, tmp_path):
    import json

    calls = _install(monkeypatch, [HALF, CUT, CUT])
    path = tmp_path / "result.json"
    result = _run(extract_options={"save_json": True, "json_path": str(path)})

    assert calls["transcribe"] == 3
    assert result.transcription.raw_transcript == HALF
    assert set(calls["save_json"]) == {False}  # no attempt writes on its own
    assert json.loads(path.read_text(encoding="utf-8")) == result.extracted_fields


# --- a generated schema is checked before the audio is transcribed ----------


def _generated(monkeypatch):
    class Generator:
        def __init__(self, config):
            self.item_requirements = REQUIREMENTS

        def generate_schema(self, user_requirements):
            return type("Schema", (), {})

    monkeypatch.setattr(module, "SchemaGenerator", Generator)


def test_a_name_the_generated_schema_lacks_is_refused_before_transcribing(monkeypatch):
    calls = _install(monkeypatch, [FULL])
    _generated(monkeypatch)
    with pytest.raises(ValueError, match="asset_identifier"):
        module.AudioToStructuredData(api_config=CONFIG).run(
            file_path="synthetic.wav",
            user_requirements="reporter, asset id",
            retry_when_empty=["asset_identifier"],
        )
    assert calls["transcribe"] == 0


def test_a_generated_schema_retries_for_its_named_fields(monkeypatch):
    calls = _install(monkeypatch, [CUT, FULL])
    _generated(monkeypatch)
    result = module.AudioToStructuredData(api_config=CONFIG).run(
        file_path="synthetic.wav",
        user_requirements="reporter, asset id",
        retry_when_empty=WATCH,
    )
    assert calls["transcribe"] == 2
    assert result.empty_fields == []
