"""Fail-closed release result validation and bounded real-client runner contracts."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_script("release_check")
smoke = _load_script("release_smoke")


def _passed_result(provider="azure", model="release-model"):
    return {
        "ok": True,
        "authenticated_live": True,
        "provider": provider,
        "backend": "native",
        "model": model,
        "checks": {name: {"ok": True} for name in gate.REQUIRED_CHECKS},
    }


def test_ci_required_provider_cannot_be_removed_from_configured_matrix():
    targets = gate.select_targets(
        "openai",
        {"RELEASE_OPENAI_MODEL": "openai-model", "RELEASE_AZURE_MODEL": "azure-deployment"},
        ["azure"],
    )
    assert [target["provider"] for target in targets] == ["azure", "openai"]
    assert targets[0]["model"] == "azure-deployment"


def test_ci_keeps_native_azure_when_litellm_backend_is_selected():
    targets = gate.select_targets(
        "azure",
        {"RELEASE_AZURE_MODEL": "deployment", "RELEASE_AZURE_BACKENDS": "litellm"},
        ["azure"],
    )
    assert [target["backend"] for target in targets] == ["native", "litellm"]


def test_litellm_azure_uses_explicit_deployment_endpoint_and_version():
    config = smoke.backend_config(
        {
            "provider": "azure",
            "model": "deployment",
            "api_key": "test",
            "azure_endpoint": "https://example.openai.azure.com",
            "api_version": "version",
        },
        "azure",
        "litellm",
    )
    assert config["provider"] == "litellm"
    assert config["model"] == "azure/deployment"
    assert config["base_url"] == "https://example.openai.azure.com"
    assert config["api_version"] == "version"


@pytest.mark.parametrize("providers", ["", "azure,", "unsupported"])
def test_empty_or_invalid_provider_matrix_fails(providers):
    with pytest.raises(ValueError):
        gate.select_targets(providers, {"RELEASE_AZURE_MODEL": "model"})


def test_a_credential_without_explicit_model_cannot_select_a_target():
    with pytest.raises(ValueError, match="RELEASE_AZURE_MODEL"):
        gate.select_targets("azure", {"AZURE_API_KEY": "fake-key"})


def test_success_requires_real_authentication_and_all_components():
    target = {"provider": "azure", "model": "release-model"}
    result = _passed_result()
    assert gate.validate_live_result(result, target, 0)
    result["authenticated_live"] = False
    assert not gate.validate_live_result(result, target, 0)
    result["authenticated_live"] = True
    del result["checks"]["data_extractor"]
    assert not gate.validate_live_result(result, target, 0)


def test_failed_process_or_wrong_model_cannot_claim_success():
    target = {"provider": "azure", "model": "release-model"}
    assert not gate.validate_live_result(_passed_result(), target, 1)
    assert not gate.validate_live_result(_passed_result(model="another-model"), target, 0)


def test_selected_embedding_model_is_required_in_result():
    target = {"provider": "azure", "model": "release-model", "embedding_model": "embed-model"}
    result = _passed_result()
    assert not gate.validate_live_result(result, target, 0)
    result["checks"]["embedder"] = {"ok": True}
    result["embedding_model"] = "embed-model"
    assert gate.validate_live_result(result, target, 0)


def test_wheel_version_comes_from_gaik_metadata(tmp_path):
    path = tmp_path / "gaik.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("gaik-0.8.0.dist-info/METADATA", "Name: gaik\nVersion: 0.8.0\n")
    assert gate.wheel_version(path) == "0.8.0"


def _distributions(tmp_path, *, missing_sql=None, repository_data=False):
    source = tmp_path / "source"
    source.mkdir()
    files = {"__init__.py": b"", "py.typed": b"", "sql/schema.sql": b"SELECT 1;"}
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    directory = tmp_path / "dist"
    directory.mkdir()
    metadata = b"Name: gaik\nVersion: 0.8.0\n"
    with zipfile.ZipFile(directory / "gaik-0.8.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("gaik-0.8.0.dist-info/METADATA", metadata)
        for name, content in files.items():
            if missing_sql != "wheel" or not name.endswith(".sql"):
                wheel.writestr("gaik/" + name, content)
    with tarfile.open(directory / "gaik-0.8.0.tar.gz", "w:gz") as archive:
        archived = {
            "implementation_layer/src/gaik/" + name: content
            for name, content in files.items()
            if missing_sql != "sdist" or not name.endswith(".sql")
        }
        archived["PKG-INFO"] = metadata
        if repository_data:
            archived["implementation_layer/toolkit_demo_app/public/demo.mp4"] = b"video"
        for name, content in archived.items():
            member = tarfile.TarInfo("gaik-0.8.0/" + name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return directory, source


def test_distribution_validation_preserves_sql_typing_and_source(tmp_path):
    directory, source = _distributions(tmp_path)
    report = gate.validate_distributions(directory, "0.8.0", source)
    assert len(report) == 2
    assert all(item["runtime_files"] == 3 and len(item["sha256"]) == 64 for item in report)


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_distribution_validation_rejects_missing_runtime_asset(tmp_path, artifact):
    directory, source = _distributions(tmp_path, missing_sql=artifact)
    with pytest.raises(ValueError, match="runtime files differ"):
        gate.validate_distributions(directory, "0.8.0", source)


def test_distribution_validation_rejects_repository_data(tmp_path):
    directory, source = _distributions(tmp_path, repository_data=True)
    with pytest.raises(ValueError, match="allowlist"):
        gate.validate_distributions(directory, "0.8.0", source)


def test_distribution_validation_rejects_oversized_artifact(tmp_path, monkeypatch):
    directory, source = _distributions(tmp_path)
    monkeypatch.setattr(gate, "MAX_DISTRIBUTION_BYTES", 1)
    with pytest.raises(ValueError, match="packaging budget"):
        gate.validate_distributions(directory, "0.8.0", source)


def test_distribution_validation_requires_sdist_as_well_as_wheel(tmp_path):
    directory, source = _distributions(tmp_path)
    next(directory.glob("*.tar.gz")).unlink()
    with pytest.raises(ValueError, match="exactly one"):
        gate.validate_distributions(directory, "0.8.0", source)


def test_request_budget_blocks_transport_and_caps_output():
    class Client:
        provider = "azure"
        model = "release-model"
        raw = None

        def __init__(self):
            self.calls = []

        def chat(self, messages, **kwargs):
            self.calls.append(kwargs)

    actual = Client()
    bounded = smoke.BoundedClient(actual, max_calls=1, output_tokens=128)
    bounded.chat([{"role": "user", "content": "test"}])
    with pytest.raises(RuntimeError, match="budget"):
        bounded.chat([{"role": "user", "content": "test"}])
    assert actual.calls == [{"max_completion_tokens": 128}]


def test_command_deadline_terminates_a_running_process():
    with pytest.raises(subprocess.TimeoutExpired):
        gate._run_command([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.1)


def test_raw_client_budget_preserves_raw_component_branch_and_sampling_kwargs():
    from gaik.software_components.llm.base import ProviderClient

    calls = []

    def actual_parse(**kwargs):
        calls.append(kwargs)
        return "real-result"

    raw = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=actual_parse))),
        chat=SimpleNamespace(completions=SimpleNamespace(create=actual_parse)),
        embeddings=SimpleNamespace(create=actual_parse),
    )
    wrapped = smoke.BoundedOpenAIClient(raw, "azure", smoke.CallBudget(1, 256))
    assert not isinstance(wrapped, ProviderClient)
    assert wrapped.beta.chat.completions.parse(model="gpt-6-luna", temperature=0) == "real-result"
    assert calls == [{"model": "gpt-6-luna", "temperature": 0, "max_completion_tokens": 256}]
    with pytest.raises(RuntimeError, match="budget"):
        wrapped.chat.completions.create(model="gpt-6-luna")
