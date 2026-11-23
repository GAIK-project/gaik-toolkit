"""Template-level fixes: audio stage config, transcription format, schema defaults.

These run the generated helper code against stubs, so they need no gaik install.
"""

import json
import sys
import types
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"


@pytest.fixture
def provider_config(monkeypatch):
    def get_llm_config(provider, **settings):
        return {"provider": provider, **settings}

    llm = types.ModuleType("gaik.software_components.llm")
    llm.get_llm_config = get_llm_config
    providers = types.ModuleType("gaik.software_components.llm.providers")
    providers.resolve_provider = lambda name: name
    for name, mod in {
        "gaik": types.ModuleType("gaik"),
        "gaik.software_components": types.ModuleType("gaik.software_components"),
        "gaik.software_components.llm": llm,
        "gaik.software_components.llm.providers": providers,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    namespace: dict = {}
    source = (TEMPLATES / "_common" / "provider_config.py.tmpl").read_text(encoding="utf-8")
    exec(compile(source, "provider_config.py", "exec"), namespace)
    return types.SimpleNamespace(**namespace, _ns=namespace)


def test_audio_model_in_stage_model_goes_to_transcription_model(provider_config):
    config = {
        "stages": {
            "transcription": {"provider": "azure", "model": "gpt-4o-transcribe"},
            "extraction": {"provider": "azure", "model": "chat-model"},
        }
    }
    result = provider_config.get_stage_config(config, "transcription")
    assert result["transcription_model"] == "gpt-4o-transcribe"
    # the transcript enhancer calls chat completions with `model`: never the audio model
    assert result["model"] == "chat-model"


def test_transcription_stage_without_explicit_stage_uses_models_block(provider_config):
    config = {
        "provider": "azure",
        "models": {"transcription": "whisper", "extraction": "chat-model"},
    }
    result = provider_config.get_stage_config(config, "transcription")
    assert result["transcription_model"] == "whisper"
    assert result["model"] == "chat-model"


def test_chat_model_of_another_provider_is_not_borrowed(provider_config):
    config = {
        "stages": {
            "transcription": {"provider": "azure", "transcription_model": "whisper"},
            "extraction": {"provider": "anthropic", "model": "claude-x"},
        }
    }
    result = provider_config.get_stage_config(config, "transcription")
    assert "model" not in result


@pytest.mark.parametrize(
    "model,wanted,expected",
    [
        ("gpt-4o-transcribe", "srt", "text"),
        ("gpt-4o-transcribe", "vtt", "text"),
        ("gpt-4o-transcribe", "json", "json"),
        ("gpt-4o-transcribe", "text", "text"),
        ("whisper", "srt", "srt"),
        (None, "srt", "srt"),
    ],
)
def test_transcription_response_format(provider_config, model, wanted, expected):
    cfg = {"transcription_model": model}
    assert provider_config.transcription_response_format(cfg, wanted) == expected


@pytest.mark.parametrize("template", ["audio_to_structured", "document_to_structured"])
def test_non_string_field_default_is_reset_to_null(template, tmp_path, capsys):
    source = (TEMPLATES / template / "run_poc.py.tmpl").read_text(encoding="utf-8")
    start = source.index("def _normalise_field_defaults")
    end = source.index("def _load_schema_if_fresh")
    namespace = {"json": json, "Path": Path}
    exec(source[start:end], namespace)
    # the real file layout: gaik writes {"model_name", "requirements_type", "requirements": {...}}
    requirements = {
        "model_name": "Ticket",
        "requirements_type": "single",
        "requirements": {
            "use_case_name": "ticket",
            "fields": [
                {"field_name": "a", "default": "x", "has_explicit_default": True},
                {"field_name": "b", "default": [], "has_explicit_default": True},
                {"field_name": "c", "default": None, "has_explicit_default": False},
            ],
        },
    }
    path = tmp_path / "output_schema_requirements.json"
    path.write_text(json.dumps(requirements), encoding="utf-8")

    namespace["_normalise_field_defaults"](tmp_path, "output_schema")

    fields = json.loads(path.read_text(encoding="utf-8"))["requirements"]["fields"]
    assert fields[0]["default"] == "x" and fields[0]["has_explicit_default"] is True
    assert fields[1]["default"] is None and fields[1]["has_explicit_default"] is False
    assert fields[2]["default"] is None
    assert "WARNING" in capsys.readouterr().out


def test_missing_requirements_file_is_left_alone(tmp_path):
    source = (TEMPLATES / "audio_to_structured" / "run_poc.py.tmpl").read_text(encoding="utf-8")
    namespace = {"json": json, "Path": Path}
    exec(
        source[
            source.index("def _normalise_field_defaults") : source.index(
                "def _load_schema_if_fresh"
            )
        ],
        namespace,
    )
    namespace["_normalise_field_defaults"](tmp_path, "output_schema")
    assert list(tmp_path.iterdir()) == []


SKILL = Path(__file__).parent.parent / "SKILL.md"
CARDS = Path(__file__).parent.parent / "registries" / "component_reference_cards.json"


def test_skill_tells_the_agent_paths_are_not_json_and_to_key_manifests_once():
    text = SKILL.read_text(encoding="utf-8")

    assert "`Path` objects are not JSON" in text
    assert 'spec.model_dump(mode="json")' in text
    # The manifest lookup is the scaffolded helper's now (#251).
    assert "do not write your own lookup" in text


def test_the_report_writer_card_warns_that_spec_sources_are_paths():
    cards = json.loads(CARDS.read_text(encoding="utf-8"))

    sources = cards["ReportWriter"]["spec_fields"]["sources"]

    assert "Path objects" in sources and "json.dumps" in sources


def test_env_placeholder_is_resolved_when_the_variable_is_set(provider_config, monkeypatch):
    monkeypatch.setenv("ANSWER_DEPLOYMENT", "real-chat")
    config = {"stages": {"answer": {"provider": "azure", "model": "env:ANSWER_DEPLOYMENT"}}}

    assert provider_config.get_stage_config(config, "answer")["model"] == "real-chat"


@pytest.mark.parametrize("spelling", ["env:ANSWER_DEPLOYMENT", "ENV:ANSWER_DEPLOYMENT"])
def test_unset_env_placeholder_is_dropped_with_a_warning(
    provider_config, monkeypatch, capsys, spelling
):
    monkeypatch.delenv("ANSWER_DEPLOYMENT", raising=False)
    config = {"stages": {"answer": {"provider": "azure", "model": spelling}}}

    result = provider_config.get_stage_config(config, "answer")

    # the literal text must never reach the model API as a deployment name
    assert "model" not in result
    # provider_config prints its warnings on stderr.
    assert "ANSWER_DEPLOYMENT" in capsys.readouterr().err


def test_env_placeholder_in_the_models_block_is_handled_too(provider_config, monkeypatch):
    monkeypatch.delenv("CHAT_DEPLOYMENT", raising=False)
    config = {"provider": "azure", "models": {"extraction": "env:CHAT_DEPLOYMENT"}}

    assert "model" not in provider_config.get_stage_config(config, "extraction")


def test_plain_values_are_left_alone(provider_config):
    config = {
        "stages": {"answer": {"provider": "azure", "model": "chat-model", "top_k": 5}},
        "language": "en",
    }

    result = provider_config.get_stage_config(config, "answer")

    assert result["model"] == "chat-model" and result["top_k"] == 5
    assert config["stages"]["answer"]["model"] == "chat-model"  # the config is not mutated


def _needs_keys(provider_config):
    """get_llm_config as gaik has it: a provider without its key raises ValueError."""
    import os

    def get_llm_config(provider, **settings):
        if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise ValueError(
                "OPENAI_API_KEY not found in environment; provide 'api_key' explicitly"
            )
        result = {"provider": provider, **settings}
        if provider == "azure":  # gaik fills Azure's own defaults
            result.setdefault("model", "azure-chat-default")
            result.setdefault("embedding_model", "text-embedding-3-small")
        return result

    provider_config._ns["get_llm_config"] = get_llm_config


def test_a_stage_on_a_provider_without_a_key_runs_on_azure_when_azure_is_there(
    provider_config, monkeypatch, capsys
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_API_KEY", "k")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.invalid/")
    _needs_keys(provider_config)
    config = {
        "stages": {
            "extraction": {"provider": "openai", "model": "gpt-6-luna"},
            "embedding": {"provider": "openai", "model": "text-embedding-3-large"},
        }
    }

    chat = provider_config.get_stage_config(config, "extraction")
    embedding = provider_config.get_stage_config(config, "embedding")

    # a model of the other provider's catalog is not an Azure deployment: dropped, and
    # Azure's own default takes its place
    assert chat["provider"] == "azure" and chat["model"] == "azure-chat-default"
    assert embedding["provider"] == "azure"
    assert embedding["embedding_model"] == "text-embedding-3-small"
    out = capsys.readouterr().out
    assert "WARNING" in out and "Azure" in out and "dropped" in out


def test_a_missing_key_is_still_an_error_when_azure_is_not_there_either(
    provider_config, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
    _needs_keys(provider_config)
    config = {"stages": {"extraction": {"provider": "openai"}}}

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        provider_config.get_stage_config(config, "extraction")


def test_a_provider_that_has_its_key_is_left_alone(provider_config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_API_KEY", "k")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.invalid/")
    _needs_keys(provider_config)
    config = {"stages": {"extraction": {"provider": "openai", "model": "gpt-6-luna"}}}

    result = provider_config.get_stage_config(config, "extraction")

    assert result["provider"] == "openai" and result["model"] == "gpt-6-luna"


def test_other_errors_are_not_turned_into_azure(provider_config, monkeypatch):
    monkeypatch.setenv("AZURE_API_KEY", "k")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.invalid/")

    def get_llm_config(provider, **settings):
        raise ValueError("unsupported model family")

    provider_config._ns["get_llm_config"] = get_llm_config
    config = {"stages": {"extraction": {"provider": "openai"}}}

    with pytest.raises(ValueError, match="unsupported model family"):
        provider_config.get_stage_config(config, "extraction")


def test_self_hosted_whisper_keeps_its_own_path(provider_config, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_API_KEY", "k")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.invalid/")
    _needs_keys(provider_config)
    config = {
        "stages": {"transcription": {"provider": "openai", "transcription_model": "whisper_local"}}
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["provider"] == "openai" and result["transcription_model"] == "whisper_local"


def test_skill_names_azure_as_the_provider_of_a_sandbox_poc():
    text = SKILL.read_text(encoding="utf-8")

    assert "Provider of a PoC that runs in the wizard's sandbox: `azure`" in text
    assert "do not pick `openai` as a neutral default" in text


def test_skill_gives_the_extraction_prompt_rules_from_uc05():
    """Each rule answers a miss that recurred in every UC05 run (#255)."""
    text = SKILL.read_text(encoding="utf-8")

    assert "Show each citation format as a filled-in example, never as a placeholder" in text
    assert "Normalise dates to ISO 8601" in text
    assert "A statement that something was *not* decided is not a decision" in text
    assert "Record a gap once" in text
    assert "cite the\n  recording *and* the agenda page" in text
    # The hybrid path refines the scaffolded prompt; it is pointed at the same rules.
    assert "applying the citation, date and decision rules of Step 4.2" in text


def test_skill_says_a_finished_entrypoint_has_no_todo_markers():
    """#252: the api refuses a package whose run_poc.py has TODO/FIXME markers; the
    agent must know the rule, or an ordinary note keeps a working package not ready."""
    text = SKILL.read_text(encoding="utf-8")

    assert "A finished `run_poc.py` has no TODO/FIXME markers" in text
    assert "put follow-up ideas" in text and "in `README.md`" in text
