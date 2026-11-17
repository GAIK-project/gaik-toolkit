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
    assert "ANSWER_DEPLOYMENT" in capsys.readouterr().err


def test_an_unset_env_value_is_named_once_however_many_stages_read_it(
    provider_config, monkeypatch, capsys
):
    monkeypatch.setenv("ANSWER_DEPLOYMENT", "   ")  # blank counts as unset
    config = {
        "stages": {
            "answer": {"provider": "azure", "model": "env:ANSWER_DEPLOYMENT"},
            "extraction": {"provider": "azure", "model": "chat-model"},
        }
    }

    assert "model" not in provider_config.get_stage_config(config, "answer")
    provider_config.get_stage_config(config, "extraction")

    assert capsys.readouterr().err.count("WARNING") == 1


@pytest.mark.parametrize(
    ("value", "expected"), [("chat-deployment", "chat-deployment"), (None, None)]
)
def test_env_value_in_the_models_block_is_resolved_too(
    provider_config, monkeypatch, value, expected
):
    if value is None:
        monkeypatch.delenv("CHAT_DEPLOYMENT", raising=False)
    else:
        monkeypatch.setenv("CHAT_DEPLOYMENT", value)
    config = {"provider": "azure", "models": {"extraction": "env:CHAT_DEPLOYMENT"}}

    assert provider_config.get_stage_config(config, "extraction").get("model") == expected


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


@pytest.mark.parametrize("enhancer", ["enhancer-model", "transcript-enhancer"])
def test_an_explicit_enhancement_model_is_kept(provider_config, enhancer):
    """Beside a transcription_model, `model` is the enhancement model whatever its name."""
    config = {
        "stages": {
            "transcription": {
                "provider": "azure",
                "transcription_model": "whisper",
                "model": enhancer,
            },
            "extraction": {"provider": "azure", "model": "chat-model"},
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "whisper"
    assert result["model"] == enhancer


@pytest.mark.parametrize(
    "addresses",
    [
        {"azure_endpoint": "https://chat-resource.example/"},
        {"base_url": "https://chat-resource.example/openai/v1"},
    ],
)
def test_the_chat_model_of_another_endpoint_is_not_borrowed(provider_config, addresses):
    """A deployment name belongs to one resource: the extraction stage's may not exist
    where the transcription stage sends the enhancement."""
    config = {
        "stages": {
            "transcription": {"provider": "azure", "model": "gpt-4o-transcribe"},
            "extraction": {"provider": "azure", "model": "chat-model", **addresses},
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["transcription_model"] == "gpt-4o-transcribe"
    assert "model" not in result


def test_the_models_block_is_not_read_when_the_config_has_stages(provider_config):
    """With stages, models.extraction is a summary; an extraction stage without a model
    uses the provider default, so the enhancement does not get the summary's model."""
    config = {
        "models": {"extraction": "old-chat-model"},
        "stages": {
            "transcription": {"provider": "azure", "model": "gpt-4o-transcribe"},
            "extraction": {"provider": "azure"},
        },
    }

    assert "model" not in provider_config.get_stage_config(config, "transcription")


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


def test_self_hosted_whisper_written_as_model_reads_no_credentials(provider_config):
    """With no external model API, whisper_local needs no OpenAI/Azure key: the stage
    is built without get_llm_config, also when the name was written as `model`."""

    def get_llm_config(provider, **settings):
        raise ValueError("OPENAI_API_KEY not found in environment")

    provider_config.get_stage_config.__globals__["get_llm_config"] = get_llm_config
    config = {
        "governance": {"external_model_api_allowed": False},
        "stages": {"transcription": {"provider": "openai", "model": "whisper_local"}},
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result == {
        "transcription_model": "whisper_local",
        "provider": "openai",
        "use_azure": False,
    }


def test_a_borrowed_deployment_keeps_its_model_family(provider_config):
    """gaik reads a custom Azure deployment's family from model_family (llm/parameters.py)."""
    config = {
        "stages": {
            "transcription": {"provider": "azure", "model": "gpt-4o-transcribe"},
            "extraction": {
                "provider": "azure",
                "model": "prod-chat",
                "model_family": "gpt-6-luna",
            },
        }
    }

    result = provider_config.get_stage_config(config, "transcription")

    assert result["model"] == "prod-chat" and result["model_family"] == "gpt-6-luna"


def test_a_chat_deployment_named_for_transcripts_stays_the_chat_model(provider_config):
    """'transcript-cleaner' is a chat deployment; only audio-model names move."""
    config = {"stages": {"transcription": {"provider": "azure", "model": "transcript-cleaner"}}}

    result = provider_config.get_stage_config(config, "transcription")

    assert result["model"] == "transcript-cleaner"
    assert "transcription_model" not in result


@pytest.mark.parametrize("name", ["AZURE_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "DB_PASSWORD"])
def test_an_env_value_never_names_a_credential(provider_config, monkeypatch, name):
    """Its value would be sent, and printed in errors, as a model name or address."""
    monkeypatch.setenv(name, "secret-value")
    config = {"stages": {"answer": {"provider": "azure", "model": f"env:{name}"}}}

    with pytest.raises(ValueError, match="names a credential"):
        provider_config.get_stage_config(config, "answer")
