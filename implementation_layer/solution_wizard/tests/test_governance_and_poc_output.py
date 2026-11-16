"""The blueprint's governance flags decide which providers a PoC may use, a provider
fallback happens only when asked for and is logged, and the generated PoC prints
counts and file names instead of the extracted content unless --verbose is given."""

import ast
import importlib.util
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import (
    _build_generic_judge_section,
    _build_source_tracing_section,
    _build_variables,
    scaffold_poc,
)
from solution_wizard.validator import validate

EXAMPLES = Path(__file__).parent.parent / "examples"
TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"
LOCAL = {"provider": "openai_compatible", "base_url": "http://localhost:8000/v1", "model": "m"}


def _document(models=None, external=True, local=False, personal="no") -> Blueprint:
    blueprint = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    if models is not None:
        blueprint.models = models
    handling = blueprint.governance.data_handling
    handling.external_model_api_allowed = external
    handling.local_processing_required = local
    handling.contains_personal_data = personal
    return blueprint


def _rule13(result):
    return [issue.message for issue in result.errors if issue.rule == 13]


def _load(path: Path, name: str, folder: Path):
    copy = folder / f"{name}.py"  # the templates end in .tmpl, which the importer skips
    copy.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, copy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- governance


@pytest.mark.parametrize(("external", "local"), [(False, False), (True, True)])
def test_a_blueprint_without_external_models_refuses_a_cloud_provider(tmp_path, external, local):
    blueprint = _document(external=external, local=local)  # the example uses azure_openai
    problems = _rule13(validate(blueprint))
    assert problems and all("'azure'" in p for p in problems)
    with pytest.raises(ValueError, match="governance"):
        scaffold_poc(blueprint, tmp_path)


def test_a_blueprint_without_external_models_never_gets_the_default_provider(tmp_path):
    blueprint = _document(models={"extraction_model": "m"}, external=False)
    problems = _rule13(validate(blueprint))
    assert len(problems) == 1 and "no provider is set for the extraction, parser" in problems[0]
    with pytest.raises(ValueError, match="default 'azure'"):
        scaffold_poc(blueprint, tmp_path)


def test_local_endpoints_satisfy_the_governance_flags(tmp_path):
    blueprint = _document(models=dict(LOCAL), external=False, local=True)
    assert _rule13(validate(blueprint)) == []
    poc = scaffold_poc(blueprint, tmp_path)["poc_dir"]
    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
    assert config["governance"]["external_model_api_allowed"] is False
    assert config["governance"]["local_processing_required"] is True
    assert config["allow_provider_fallback"] is False


def test_a_host_the_owner_lists_counts_as_local():
    models = {**LOCAL, "base_url": "https://llm.internal.example/v1"}
    assert _rule13(validate(_document(models=models, external=False)))
    models["local_endpoints"] = ["llm.internal.example"]
    assert _rule13(validate(_document(models=models, external=False))) == []


def test_a_missing_provider_is_reported_when_external_models_are_allowed():
    result = validate(_document(models={"extraction_model": "m"}))
    assert any(i.rule == 13 and "No provider is set" in i.message for i in result.warnings)
    assert _rule13(result) == []


def test_the_scaffold_says_which_stages_got_the_default_provider(tmp_path):
    notes = scaffold_poc(_document(models={"extraction_model": "m"}), tmp_path)["notes"]
    assert len(notes) == 1 and "default 'azure'" in notes[0]
    assert scaffold_poc(_document(), tmp_path / "named")["notes"] == []


def test_stages_with_their_own_local_provider_need_no_models_provider():
    models = {"parser_config": dict(LOCAL), "extraction_config": dict(LOCAL)}
    assert _rule13(validate(_document(models=models, external=False))) == []


def test_a_listed_host_may_use_plain_http_and_a_malformed_entry_is_named(tmp_path):
    models = {**LOCAL, "base_url": "http://gpu.lan:8000/v1", "local_endpoints": ["gpu.lan"]}
    blueprint = _document(models=models, external=False)
    assert _rule13(validate(blueprint)) == []
    scaffold_poc(blueprint, tmp_path)
    models["local_endpoints"] = ["http://gpu.lan:8000"]
    problems = _rule13(validate(_document(models=models, external=False)))
    assert any("must be a host name" in p for p in problems)


def test_every_component_that_calls_a_model_has_its_stages_checked():
    """A component missing from the stage map was never checked against the flags."""
    import json

    from solution_wizard.scaffolder import _COMPONENT_STAGES

    registry = json.loads(
        (Path(__file__).parent.parent / "registries" / "gaik_component_registry.json").read_text(
            encoding="utf-8"
        )
    )
    calls_a_model = {c["name"] for c in registry if c.get("supported_providers")}
    assert calls_a_model - set(_COMPONENT_STAGES) == set()


def test_a_judge_panel_on_a_cloud_provider_is_refused():
    blueprint = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    for step in blueprint.workflow.steps:
        if step.component == "LLMJudge":
            step.component = "LLMJudgePanel"
    blocks = blueprint.components.selected_building_blocks
    blueprint.components.selected_building_blocks = [
        "LLMJudgePanel" if b == "LLMJudge" else b for b in blocks
    ]
    blueprint.models = {
        **LOCAL,
        "transcription_config": {"provider": "openai", "transcription_model": "whisper_local"},
        "judge_config": {"provider": "anthropic", "model": "m"},
    }
    blueprint.governance.data_handling.external_model_api_allowed = False
    problems = _rule13(validate(blueprint))
    assert any("judge stage uses 'anthropic'" in p for p in problems)


def test_a_module_named_only_in_selected_modules_counts():
    from solution_wizard.blueprint import SelectedModule

    blueprint = _document(models={**LOCAL, "answer_config": {"provider": "openai", "model": "m"}})
    blueprint.governance.data_handling.external_model_api_allowed = False
    assert _rule13(validate(blueprint)) == []  # no step answers questions
    blueprint.components.selected_modules.append(
        SelectedModule(id="rag_workflow", name="RAGWorkflow")
    )
    assert any("answer stage uses 'openai'" in p for p in _rule13(validate(blueprint)))


@pytest.mark.parametrize("personal", ["yes", "likely", "yes (names, phone numbers)"])
def test_personal_data_sent_to_an_external_provider_is_flagged(personal):
    result = validate(_document(personal=personal))
    assert any(i.rule == 13 and "personal data" in i.message for i in result.warnings)


# --------------------------------------------------------------------------- run time


@pytest.fixture
def provider_config(tmp_path):
    return _load(
        TEMPLATES / "_common" / "provider_config.py.tmpl", "provider_config_under_test", tmp_path
    )


def test_a_stage_without_a_provider_stops_unless_the_blueprint_allows_the_fallback(
    tmp_path, monkeypatch
):
    def generated(models):
        poc = scaffold_poc(_document(models=models), tmp_path / str(len(models)))["poc_dir"]
        module = _load(poc / "provider_config.py", f"provider_config_{len(models)}", tmp_path)
        config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
        del config["stages"]["extraction"]["provider"]  # a stage left without a provider
        return module, config

    seen = []
    module, config = generated({"provider": "openai", "extraction_model": "m"})
    monkeypatch.setattr(module, "get_llm_config", lambda p, **kw: seen.append(p) or {})
    with pytest.raises(ValueError, match="No provider is set for the extraction stage"):
        module.get_stage_config(config, "extraction")
    assert seen == []

    module, config = generated(
        {"provider": "openai", "extraction_model": "m", "allow_provider_fallback": True}
    )
    assert config["allow_provider_fallback"] is True
    monkeypatch.setattr(module, "get_llm_config", lambda p, **kw: seen.append(p) or {})
    errors = io.StringIO()
    with redirect_stderr(errors):
        module.get_stage_config(config, "extraction")
    assert seen == ["openai"]
    assert "no provider is set for the extraction stage; using openai" in errors.getvalue()


def test_run_time_refuses_an_external_provider_before_reading_credentials(
    provider_config, monkeypatch
):
    def no_credentials(provider, **settings):
        raise AssertionError("credentials must not be read")

    monkeypatch.setattr(provider_config, "get_llm_config", no_credentials)
    config = {
        "governance": {"external_model_api_allowed": False},
        "stages": {"extraction": {"provider": "azure", "model": "m"}},
    }
    with pytest.raises(ValueError, match="allows no external model API"):
        provider_config.get_stage_config(config, "extraction")

    monkeypatch.setattr(provider_config, "get_llm_config", lambda p, **kw: {"provider": p})
    config["stages"]["extraction"] = dict(LOCAL)
    assert provider_config.get_stage_config(config, "extraction")["provider"] == "openai_compatible"


# --------------------------------------------------------------------------- PoC output


@pytest.fixture
def poc_output(tmp_path):
    return _load(TEMPLATES / "_common" / "poc_output.py.tmpl", "poc_output_under_test", tmp_path)


FIELDS = [{"invoice_number": "INV-SECRET-1", "total": 99.5, "notes": ""}]


def test_the_default_run_prints_counts_and_field_names_not_values(poc_output):
    out = io.StringIO()
    with redirect_stdout(out):
        poc_output.show_result(FIELDS)
    text = out.getvalue()
    assert "1 record(s), 2 of 3 field value(s) filled" in text
    assert "invoice_number" in text and "INV-SECRET-1" not in text and "99.5" not in text


def test_verbose_prints_the_values(poc_output):
    poc_output.configure(type("Args", (), {"verbose": True, "debug": False})())
    out = io.StringIO()
    with redirect_stdout(out):
        poc_output.show_result(FIELDS)
    assert "INV-SECRET-1" in out.getvalue()


def test_an_error_is_one_short_line_and_debug_shows_the_traceback(poc_output, monkeypatch):
    def main():
        raise RuntimeError("provider refused\nfull body with document text")

    monkeypatch.setattr(sys, "argv", ["run_poc.py"])
    errors = io.StringIO()
    with redirect_stderr(errors), pytest.raises(SystemExit) as done:
        poc_output.run(main)
    assert done.value.code == 1
    text = errors.getvalue()
    assert "ERROR: RuntimeError: provider refused" in text
    assert "Traceback" not in text and "document text" not in text

    monkeypatch.setattr(sys, "argv", ["run_poc.py", "--debug"])
    with pytest.raises(RuntimeError):
        poc_output.run(main)


def test_the_generated_poc_uses_the_output_helper_and_prints_no_extracted_json(tmp_path):
    poc = scaffold_poc(_document(), tmp_path)["poc_dir"]
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")
    ast.parse(run_poc)
    assert (poc / "poc_output.py").exists()
    assert "poc_output.show_result(result.extracted_fields)" in run_poc
    assert "print(json.dumps(result.extracted_fields" not in run_poc
    assert "poc_output.add_output_flags(parser)" in run_poc
    assert run_poc.rstrip().endswith("poc_output.run(main)")


@pytest.mark.parametrize("template", sorted(TEMPLATES.glob("*/run_poc.py.tmpl")), ids=str)
def test_every_poc_template_takes_the_output_flags(template):
    text = template.read_text(encoding="utf-8")
    assert "import poc_output" in text and "poc_output.configure(args)" in text
    assert text.rstrip().endswith("poc_output.run(main)")
    assert "print(json.dumps(extracted_fields" not in text
    assert "print(json.dumps(result.extracted_fields" not in text
    assert "_tb.format_exc()}" not in text


def test_judge_and_tracing_lines_show_values_only_with_verbose():
    blueprint = _document()
    blueprint.components.selected_building_blocks.append("LLMJudge")
    judge = _build_variables(blueprint, "document_to_structured")["llm_judge_section"]
    for section in (
        judge,
        _build_generic_judge_section(True),
        _build_source_tracing_section(True, "document_to_structured"),
    ):
        lines = section.splitlines()
        shown = [
            i for i, line in enumerate(lines) if "{flag.value}" in line or "{item.value!r}" in line
        ]
        assert shown, section
        for i in shown:
            assert "poc_output.VERBOSE" in lines[i] + lines[min(i + 1, len(lines) - 1)], lines[i]


def test_transcript_enhancement_is_off_when_no_external_model_is_allowed(provider_config):
    assert provider_config.external_model_forbidden(
        {"governance": {"local_processing_required": True}}
    )
    assert not provider_config.external_model_forbidden({"governance": {}})
    for template in (
        "audio_to_structured",
        "hybrid_dataextractor_pymupdfparser_transcriber_831947a5",
    ):
        text = (TEMPLATES / template / "run_poc.py.tmpl").read_text(encoding="utf-8")
        assert "enhanced_transcript=True" not in text and '"enhanced_transcript": True' not in text
        assert "not external_model_forbidden(config)" in text


def test_a_single_rag_question_prints_its_answer_only_with_verbose():
    text = (TEMPLATES / "rag" / "run_poc.py.tmpl").read_text(encoding="utf-8")
    query_branch = text[
        text.index("    if args.query:") : text.index("    else:\n        # Interactive")
    ]
    assert "if poc_output.VERBOSE:" in query_branch
    assert query_branch.index("if poc_output.VERBOSE:") < query_branch.index(
        'print(f"A: {answer}")'
    )


# --------------------------------------------------------------------------- local audio


def _local_audio(provider="openai", external=False) -> Blueprint:
    blueprint = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    blueprint.models = {
        **LOCAL,
        "transcription_config": {"provider": provider, "transcription_model": "whisper_local"},
    }
    blueprint.governance.data_handling.external_model_api_allowed = external
    return blueprint


@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_a_local_whisper_stage_scaffolds_beside_a_local_openai_compatible_stage(tmp_path, provider):
    blueprint = _local_audio(provider)
    assert _rule13(validate(blueprint)) == []
    poc = scaffold_poc(blueprint, tmp_path)["poc_dir"]
    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["transcription"]["transcription_model"] == "whisper_local"


def test_an_openai_whisper_stage_with_enhancement_on_still_refuses_openai_compatible(tmp_path):
    with pytest.raises(ValueError, match="would both read OPENAI_API_KEY"):
        scaffold_poc(_local_audio("openai", external=True), tmp_path)


def test_the_local_audio_poc_gives_the_transcriber_its_local_endpoint(tmp_path, monkeypatch):
    poc = scaffold_poc(_local_audio(), tmp_path)["poc_dir"]
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")
    assert "**local_transcriber_options(config, audio_config)" in run_poc
    module = _load(poc / "provider_config.py", "provider_config_local_audio", tmp_path)
    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))

    def no_credentials(provider, **settings):
        raise AssertionError("credentials must not be read")

    monkeypatch.setattr(module, "get_llm_config", no_credentials)
    audio_config = module.get_stage_config(config, "transcription")

    monkeypatch.delenv("LOCAL_TRANSCRIBER_API_BASE", raising=False)
    monkeypatch.delenv("LOCAL_TRANSCRIBER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="LOCAL_TRANSCRIBER_API_BASE"):
        module.local_transcriber_options(config, audio_config)

    monkeypatch.setenv("LOCAL_TRANSCRIBER_API_KEY", "test-key")
    monkeypatch.setenv("LOCAL_TRANSCRIBER_API_BASE", "https://whisper.example.com")
    with pytest.raises(ValueError, match="neither localhost nor listed"):
        module.local_transcriber_options(config, audio_config)

    monkeypatch.setenv("LOCAL_TRANSCRIBER_API_BASE", "http://localhost:8080")
    options = module.local_transcriber_options(config, audio_config)
    assert options == {"local_api_base": "http://localhost:8080", "local_api_key": "test-key"}
    assert module.local_transcriber_options(config, {"transcription_model": "whisper-1"}) == {}

    # The Transcriber the PoC builds takes the self-hosted Whisper path with these options.
    transcriber_module = pytest.importorskip("gaik.software_components.transcriber.transcriber")
    calls = []
    monkeypatch.setattr(
        transcriber_module,
        "whisper_local_transcribe",
        lambda **kw: calls.append(kw) or {"text": "ok", "segments": []},
    )
    transcriber = transcriber_module.Transcriber(
        api_config=audio_config, output_dir=tmp_path / "out", **options
    )
    assert transcriber._resolve_transcription_model() == "whisper_local"
    assert transcriber._transcribe_input_local(tmp_path / "a.wav")[0] == "ok"
    assert calls[0]["api_base"] == "http://localhost:8080"
