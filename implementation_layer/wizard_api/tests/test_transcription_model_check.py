"""A PoC whose transcription stage would get the chat model is refused before it runs.

The scaffolder gives every stage the blueprint's chat model unless the stage names
its own. An audio pipeline without a transcription model therefore sent audio to
the chat model, and the provider refused it at the first run while the package
check had passed. The blueprint check tells the agent which field to set; the
package check stops a package that already has the wrong setting.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml
from wizard_api.services import artifact_sync, poc_service, scaffold_guard

requires_scaffolder = pytest.mark.skipif(
    not poc_service.solution_wizard_available(),
    reason="solution_wizard is not installed",
)

_AUDIO = {
    "use_case": {
        "id": "uc",
        "name": "Meeting notes",
        "description": "Turn a recorded call into structured notes.",
        "domain": "service",
    },
    "technical_spec": {"input_types": ["audio"]},
    "target_output_spec": {
        "schema_name": "CallNotes",
        "fields": ["topic"],
        "field_types": {"topic": "str"},
    },
    "components": {
        "selected_modules": [
            {"id": "audio_to_structured_data", "name": "audio_to_structured_data"}
        ],
        "selected_building_blocks": [],
    },
    "models": {"provider": "azure", "extraction_model": "chat-deployment"},
}


def _blueprint(models=None, **components):
    blueprint = copy.deepcopy(_AUDIO)
    if models is not None:
        blueprint["models"] = models
    if components:
        blueprint["components"] = {
            "selected_modules": [],
            "selected_building_blocks": [],
            **components,
        }
    return blueprint


# --- blueprint ---------------------------------------------------------------


def test_an_audio_blueprint_without_a_transcription_model_is_refused() -> None:
    found = scaffold_guard.problems(_blueprint())

    assert found and found[0].startswith("models.transcription_model is not set")
    assert "models.transcription_config.model" in found[0]


@pytest.mark.parametrize(
    "models",
    [
        {"provider": "azure", "extraction_model": "chat-deployment", "transcription_model": "a"},
        {
            "provider": "azure",
            "extraction_model": "chat-deployment",
            "transcription_config": {"model": "audio-deployment"},
        },
        {
            "provider": "azure",
            "extraction_model": "chat-deployment",
            "transcription_config": {"transcription_model": "audio-deployment"},
        },
    ],
)
def test_an_audio_blueprint_that_names_a_transcription_model_passes(models) -> None:
    assert scaffold_guard.transcription_model_problems(_blueprint(models)) == []


def test_an_audio_blueprint_without_model_settings_keeps_the_default() -> None:
    # No chat model to inherit: the scaffolder's transcription default applies.
    assert scaffold_guard.transcription_model_problems(_blueprint({})) == []


@pytest.mark.parametrize(
    "components",
    [
        {"selected_building_blocks": ["Transcriber"]},
        {"selected_building_blocks": ["ParallelTranscriber"]},
        {"selected_modules": [{"id": "AudioToStructuredData", "name": "audio"}]},
    ],
)
def test_each_transcribing_component_is_recognised(components) -> None:
    assert scaffold_guard.transcription_model_problems(_blueprint(**components))


def test_a_transcriber_named_in_a_workflow_step_is_recognised() -> None:
    blueprint = _blueprint(selected_building_blocks=["DataExtractor"])
    blueprint["workflow"] = {
        "steps": [
            {"id": "listen", "name": "Listen", "type": "automated_task", "component": "Transcriber"}
        ]
    }

    assert scaffold_guard.transcription_model_problems(blueprint)


def test_a_document_blueprint_is_unaffected() -> None:
    blueprint = _blueprint(
        selected_modules=[{"id": "documents_to_structured_data", "name": "documents"}]
    )

    assert scaffold_guard.transcription_model_problems(blueprint) == []
    assert scaffold_guard.problems(blueprint) == []


def _generate(tmp_path, blueprint):
    path = artifact_sync.artifact_path(str(tmp_path), artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blueprint, fh)
    return poc_service.generate_poc(
        {"use_case": {"title": "Meeting notes"}}, session_id="audio", output_dir=str(tmp_path)
    )


@requires_scaffolder
def test_generation_refuses_an_audio_blueprint_without_a_transcription_model(tmp_path) -> None:
    with pytest.raises(poc_service.UnscaffoldableBlueprintError, match="transcription_model"):
        _generate(tmp_path, _blueprint())

    assert not (tmp_path / "poc" / "run_poc.py").exists()


@requires_scaffolder
def test_a_generated_audio_package_with_a_transcription_model_passes_the_check(tmp_path) -> None:
    models = dict(_AUDIO["models"], transcription_model="audio-deployment")
    _generate(tmp_path, _blueprint(models))

    poc = tmp_path / "poc"
    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["transcription"]["transcription_model"] == "audio-deployment"
    assert poc_service._transcription_problems(str(poc)) == []


# --- package -------------------------------------------------------------------

AUDIO_ENTRYPOINT = (
    "from gaik.software_modules.audio_to_structured_data import AudioToStructuredData\n"
    "from provider_config import get_stage_config\n"
    "audio_config = get_stage_config(config, 'transcription')\n"
)
DOCUMENT_ENTRYPOINT = (
    "from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData\n"
)


def _package(tmp_path: Path, transcription: dict, entrypoint=AUDIO_ENTRYPOINT, models=None) -> str:
    poc = tmp_path / "poc"
    poc.mkdir()
    (poc / "run_poc.py").write_text(entrypoint, encoding="utf-8")
    # Every scaffolded package has it; without it the import check (which runs
    # when gaik is installed) reports provider_config as missing from the image.
    (poc / "provider_config.py").write_text(
        "def get_stage_config(config, stage):\n    return config['stages'][stage]\n",
        encoding="utf-8",
    )
    (poc / "requirements.txt").write_text("gaik[audio]\n", encoding="utf-8")
    (poc / "README.md").write_text("# PoC\n", encoding="utf-8")
    config = {
        "provider": "azure",
        "models": models
        if models is not None
        else {"transcription": "", "extraction": "chat-deployment"},
        "stages": {
            "transcription": {"provider": "azure", **transcription},
            "extraction": {"provider": "azure", "model": "chat-deployment"},
        },
    }
    (poc / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(poc)


def test_a_package_whose_transcription_stage_has_the_chat_model_is_refused(tmp_path) -> None:
    poc = _package(tmp_path, {"model": "chat-deployment"})

    problems = poc_service.package_problems(poc)

    assert len(problems) == 1
    assert "stages.transcription.transcription_model" in problems[0]
    assert not poc_service.package_is_ready(poc)


def test_a_package_with_no_transcription_model_anywhere_is_refused(tmp_path) -> None:
    assert poc_service.package_problems(_package(tmp_path, {}))


def test_a_package_with_a_transcription_model_is_ready(tmp_path) -> None:
    poc = _package(tmp_path, {"model": "chat-deployment", "transcription_model": "audio"})

    assert poc_service.package_problems(poc) == []


def test_a_stage_model_of_its_own_counts_as_named(tmp_path) -> None:
    assert poc_service.package_problems(_package(tmp_path, {"model": "audio-deployment"})) == []


def test_the_package_transcription_default_counts_as_named(tmp_path) -> None:
    poc = _package(
        tmp_path, {}, models={"transcription": "audio-default", "extraction": "chat-deployment"}
    )

    assert poc_service.package_problems(poc) == []


def test_a_package_that_does_not_transcribe_is_unaffected(tmp_path) -> None:
    # The scaffolder writes every stage into config.yaml; only one the code reads counts.
    poc = _package(tmp_path, {"model": "chat-deployment"}, entrypoint=DOCUMENT_ENTRYPOINT)

    assert poc_service.package_problems(poc) == []


def test_a_helper_that_only_mentions_a_transcriber_does_not_make_a_package_transcribe(
    tmp_path,
) -> None:
    # Every scaffolded package has provider_config.py, whose docstring names the Transcriber.
    poc = _package(tmp_path, {"model": "chat-deployment"}, entrypoint=DOCUMENT_ENTRYPOINT)
    Path(poc, "provider_config.py").write_text(
        "def local_transcriber_options(config, audio_config):\n"
        '    """Transcriber arguments for self-hosted Whisper."""\n'
        "    return {}  # ParallelTranscriber takes the same\n",
        encoding="utf-8",
    )

    assert poc_service.package_problems(poc) == []


@pytest.mark.parametrize(
    "code",
    [
        "from gaik.software_components.transcriber import Transcriber\n",
        "import gaik.software_components.transcriber as t\nt.ParallelTranscriber()\n",
        "x = Transcriber(api_config={})\n",
        "this does not parse: Transcriber(\n",
    ],
)
def test_code_that_uses_a_transcriber_still_counts(tmp_path, code) -> None:
    poc = _package(tmp_path, {"model": "chat-deployment"}, entrypoint=DOCUMENT_ENTRYPOINT)
    Path(poc, "helper.py").write_text(code, encoding="utf-8")

    assert poc_service.package_problems(poc)


@requires_scaffolder
def test_the_package_the_scaffolder_writes_for_such_a_blueprint_is_refused(tmp_path) -> None:
    """The package check stops this package even when it was scaffolded past the guard."""
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.scaffolder import scaffold_poc

    scaffold_poc(Blueprint.model_validate(_blueprint()), tmp_path)
    poc = tmp_path / "poc"
    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["transcription"].get("model") == "chat-deployment"

    problems = poc_service._transcription_problems(str(poc))

    assert problems and "transcription model" in problems[0]
