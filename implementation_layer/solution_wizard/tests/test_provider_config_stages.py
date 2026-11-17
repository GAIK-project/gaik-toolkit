"""The PoC's provider_config.py: env: values and the transcription stage's models.

The helper runs against a stub of gaik's get_llm_config, so these need no gaik install.
"""

import sys
import types
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402

TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"
EXAMPLES = Path(__file__).parent.parent / "examples"


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
    return types.SimpleNamespace(**namespace)


# ---------------------------------------------------------------------------
# env: values
# ---------------------------------------------------------------------------


def test_env_value_is_resolved_when_the_variable_is_set(provider_config, monkeypatch):
    monkeypatch.setenv("ANSWER_DEPLOYMENT", "real-chat")
    config = {"stages": {"answer": {"provider": "azure", "model": "env:ANSWER_DEPLOYMENT"}}}

    assert provider_config.get_stage_config(config, "answer")["model"] == "real-chat"


@pytest.mark.parametrize("spelling", ["env:ANSWER_DEPLOYMENT", "ENV:ANSWER_DEPLOYMENT"])
def test_unset_env_value_is_dropped_with_a_warning(provider_config, monkeypatch, capsys, spelling):
    monkeypatch.delenv("ANSWER_DEPLOYMENT", raising=False)
    config = {"stages": {"answer": {"provider": "azure", "model": spelling}}}

    result = provider_config.get_stage_config(config, "answer")

    # The literal text must never reach the model API as a deployment name.
    assert "model" not in result
    assert "ANSWER_DEPLOYMENT" in capsys.readouterr().out


def test_env_value_in_the_models_block_is_resolved_too(provider_config, monkeypatch):
    monkeypatch.delenv("CHAT_DEPLOYMENT", raising=False)
    config = {"provider": "azure", "models": {"extraction": "env:CHAT_DEPLOYMENT"}}

    assert "model" not in provider_config.get_stage_config(config, "extraction")


def test_plain_values_are_left_alone_and_the_config_is_not_changed(provider_config):
    config = {
        "stages": {"answer": {"provider": "azure", "model": "chat-model", "top_k": 5}},
        "language": "en",
    }

    result = provider_config.get_stage_config(config, "answer")

    assert result["model"] == "chat-model" and result["top_k"] == 5
    assert config["stages"]["answer"]["model"] == "chat-model"


def test_a_scaffolded_env_reference_reaches_the_stage_resolved(
    provider_config, monkeypatch, tmp_path
):
    """The scaffolder accepts env:NAME for a setting; the PoC is what reads it."""
    blueprint = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    blueprint.models = {"provider": "azure", "extraction_model": "env:EXTRACTION_DEPLOYMENT"}
    scaffold_poc(blueprint, tmp_path)
    config = yaml.safe_load((tmp_path / "poc" / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["extraction"]["model"] == "env:EXTRACTION_DEPLOYMENT"
    monkeypatch.setenv("EXTRACTION_DEPLOYMENT", "chat-deployment")

    assert provider_config.get_stage_config(config, "extraction")["model"] == "chat-deployment"


# ---------------------------------------------------------------------------
# The transcription stage: audio model versus the enhancement's chat model
# ---------------------------------------------------------------------------


def test_an_audio_model_written_as_model_moves_to_transcription_model(provider_config):
    config = {
        "stages": {
            "transcription": {"provider": "azure", "model": "gpt-4o-transcribe"},
            "extraction": {"provider": "azure", "model": "chat-model"},
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "gpt-4o-transcribe"
    # The transcript enhancer calls chat completions with `model`: never the audio model.
    assert result["model"] == "chat-model"


def test_a_scaffolded_audio_stage_keeps_its_chat_model(provider_config, tmp_path):
    """The scaffolder puts the shared chat model in the transcription stage's `model`
    and names no transcription_model, so gaik's default picks the audio model. That
    chat model must stay the enhancement model, not become the transcription model."""
    blueprint = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    blueprint.models = {"provider": "azure", "extraction_model": "gpt-6-luna"}
    scaffold_poc(blueprint, tmp_path)
    config = yaml.safe_load((tmp_path / "poc" / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["transcription"] == {"provider": "azure", "model": "gpt-6-luna"}

    result = provider_config.get_stage_config(config, "transcription")

    assert result["model"] == "gpt-6-luna"
    assert "transcription_model" not in result


def test_an_explicit_enhancement_model_is_kept(provider_config):
    config = {
        "stages": {
            "transcription": {
                "provider": "azure",
                "transcription_model": "whisper",
                "model": "enhancer-model",
            },
            "extraction": {"provider": "azure", "model": "chat-model"},
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "whisper"
    assert result["model"] == "enhancer-model"


def test_a_config_without_stages_uses_the_models_block(provider_config):
    config = {
        "provider": "azure",
        "models": {"transcription": "whisper", "extraction": "chat-model"},
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "whisper"
    assert result["model"] == "chat-model"


def test_the_chat_model_of_another_provider_is_not_borrowed(provider_config):
    config = {
        "stages": {
            "transcription": {"provider": "azure", "transcription_model": "whisper"},
            "extraction": {"provider": "anthropic", "model": "claude-x"},
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert "model" not in result


def test_self_hosted_whisper_keeps_its_own_path(provider_config):
    config = {
        "governance": {"external_model_api_allowed": False},
        "stages": {"transcription": {"provider": "openai", "model": "whisper_local"}},
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "whisper_local"
    assert result["provider"] == "openai"
