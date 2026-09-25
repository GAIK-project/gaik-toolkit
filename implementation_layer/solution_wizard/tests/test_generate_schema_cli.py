"""Provider-aware schema CLI contracts without inference or real credentials."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
)
from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

SCRIPT = Path(__file__).parents[1] / "scripts" / "generate_schema.py"
FAKE_KEY = "fake-provider-credential-never-print"


@pytest.fixture
def cli(monkeypatch):
    spec = importlib.util.spec_from_file_location("_schema_cli_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module._GAIK_AVAILABLE

    for name in (
        "AZURE_API_KEY",
        "AZURE_ENDPOINT",
        "AZURE_DEPLOYMENT",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_MODEL",
        "AITTA_API_KEY",
        "AITTA_API_TOKEN",
        "AITTA_TOKEN",
        "AITTA_MODEL",
        "AITTA_BASE_URL",
        "LITELLM_MODEL",
        "LITELLM_API_KEY",
        "LITELLM_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    # This script historically defaults to Azure independently of LLM_PROVIDER.
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    return module


@pytest.fixture
def fake_generator(cli, monkeypatch):
    requirements = ExtractionRequirements(
        use_case_name="cli_record",
        fields=[FieldSpec(field_name="title", field_type="str", description="Record title")],
    )
    schema = create_extraction_model(requirements)
    captured = {}

    class FakeGenerator:
        def __init__(self, *, config):
            captured["config"] = config
            self.item_requirements = requirements

        def generate_schema(self, *, user_requirements):
            captured["requirements_text"] = user_requirements
            return schema

    monkeypatch.setattr(cli, "SchemaGenerator", FakeGenerator)
    return captured, schema, requirements


def invoke(cli, monkeypatch, tmp_path, flags):
    req_path = tmp_path / "extraction_requirements.md"
    req_path.write_text("Extract the record title.\n", encoding="utf-8")
    output_dir = tmp_path / "poc"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--requirements",
            str(req_path),
            "--output-dir",
            str(output_dir),
            *flags,
        ],
    )
    return cli.main(), req_path, output_dir / "schemas"


@pytest.mark.parametrize(
    "provider,env,model",
    [
        (
            "azure",
            {"AZURE_API_KEY": FAKE_KEY, "AZURE_ENDPOINT": "https://example.openai.azure.com"},
            "my-deployment",
        ),
        ("openai", {"OPENAI_API_KEY": FAKE_KEY}, "my-openai-model"),
        ("google", {"GOOGLE_API_KEY": FAKE_KEY}, "my-google-model"),
        ("aitta", {"AITTA_API_KEY": FAKE_KEY}, "my-aitta-model"),
        ("litellm", {"LITELLM_API_KEY": FAKE_KEY}, "openai/my-litellm-model"),
    ],
)
def test_explicit_provider_overrides_legacy_flag_and_schema_reloads(
    cli,
    fake_generator,
    monkeypatch,
    tmp_path,
    capsys,
    provider,
    env,
    model,
):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    legacy_flag = "--no-azure" if provider == "azure" else "--use-azure"
    status, req_path, schema_dir = invoke(
        cli,
        monkeypatch,
        tmp_path,
        [
            "--provider",
            provider,
            legacy_flag,
            "--model",
            model,
        ],
    )
    captured, schema, requirements = fake_generator
    assert status == 0
    assert captured["config"]["provider"] == provider
    assert captured["config"]["model"] == model
    assert captured["config"]["api_key"] == FAKE_KEY
    assert captured["requirements_text"] == req_path.read_text(encoding="utf-8")

    # Exercise the same load_schema filename/JSON contract as generated PoCs,
    # without constructing an unrelated live pipeline client.
    pipeline = object.__new__(DocumentsToStructuredData)
    loaded_schema, loaded_requirements = pipeline.load_schema(schema_dir, "output_schema")
    assert loaded_schema.__name__ == schema.__name__
    assert loaded_schema(title="Saved record").title == "Saved record"
    assert loaded_requirements == requirements
    assert (schema_dir / "output_schema.hash").read_text() == hashlib.sha256(
        req_path.read_bytes()
    ).hexdigest()
    assert json.loads((schema_dir / "output_schema.json").read_text())["properties"]["title"]
    output = capsys.readouterr()
    assert f"Provider:               {provider}" in output.out
    assert FAKE_KEY not in output.out + output.err
    assert all(FAKE_KEY not in path.read_text(encoding="utf-8") for path in schema_dir.glob("*.*"))


@pytest.mark.parametrize("flags,provider", [([], "azure"), (["--no-azure"], "openai")])
def test_legacy_cli_selects_provider_and_preserves_environment_model(
    cli,
    fake_generator,
    monkeypatch,
    tmp_path,
    flags,
    provider,
):
    monkeypatch.setenv("AZURE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AZURE_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_DEPLOYMENT", "legacy-azure-deployment")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_MODEL", "legacy-openai-model")
    status, _, _ = invoke(cli, monkeypatch, tmp_path, flags)
    assert status == 0
    config = fake_generator[0]["config"]
    assert config["provider"] == provider
    assert config["model"] == (
        "legacy-azure-deployment" if provider == "azure" else "legacy-openai-model"
    )


def test_compatible_overrides_are_applied_before_required_field_validation(
    cli,
    fake_generator,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    status, _, _ = invoke(
        cli,
        monkeypatch,
        tmp_path,
        [
            "--provider",
            "openai_compatible",
            "--model",
            "served-model",
            "--base-url",
            "https://inference.example/v1",
        ],
    )
    assert status == 0
    config = fake_generator[0]["config"]
    assert config["model"] == "served-model"
    assert config["base_url"] == "https://inference.example/v1"


def test_missing_credentials_fail_before_inference_or_schema_writes(
    cli,
    fake_generator,
    monkeypatch,
    tmp_path,
    capsys,
):
    status, _, schema_dir = invoke(cli, monkeypatch, tmp_path, ["--provider", "aitta"])
    assert status == 1
    assert not fake_generator[0]
    assert not schema_dir.exists()
    assert "AITTA_API_KEY" in capsys.readouterr().err


def test_cli_does_not_expose_a_secret_flag(cli, monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        invoke(cli, monkeypatch, tmp_path, ["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--provider" in help_text and "--base-url" in help_text
    assert "--api-key" not in help_text and "--token" not in help_text
