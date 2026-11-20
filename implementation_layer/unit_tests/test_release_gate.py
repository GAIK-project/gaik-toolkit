"""Fail-closed release result validation and bounded real-client runner contracts."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from functools import partialmethod
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


_TRANSCRIPTION_ENV = {
    "RELEASE_AZURE_TRANSCRIPTION_MODEL": "transcribe-deployment",
    "RELEASE_OPENAI_TRANSCRIPTION_MODEL": "openai-transcribe",
}


def test_ci_required_provider_cannot_be_removed_from_configured_matrix():
    targets = gate.select_targets(
        "openai",
        {
            "RELEASE_OPENAI_MODEL": "openai-model",
            "RELEASE_AZURE_MODEL": "azure-deployment",
            **_TRANSCRIPTION_ENV,
        },
        ["azure"],
    )
    assert [target["provider"] for target in targets] == ["azure", "openai"]
    assert targets[0]["model"] == "azure-deployment"


def test_ci_keeps_native_azure_when_litellm_backend_is_selected():
    targets = gate.select_targets(
        "azure",
        {"RELEASE_AZURE_MODEL": "deployment", "RELEASE_AZURE_BACKENDS": "litellm"}
        | _TRANSCRIPTION_ENV,
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


def test_source_tracing_is_a_required_live_check():
    target = {"provider": "azure", "model": "release-model"}
    assert "source_tracing" in gate.REQUIRED_CHECKS
    assert "source_tracing" in smoke.REQUIRED_CHECKS
    result = _passed_result()
    assert gate.validate_live_result(result, target, 0)
    del result["checks"]["source_tracing"]
    assert not gate.validate_live_result(result, target, 0)
    result["checks"]["source_tracing"] = {"ok": False}
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


def test_an_audio_provider_needs_an_explicit_transcription_model():
    with pytest.raises(ValueError, match="RELEASE_AZURE_TRANSCRIPTION_MODEL"):
        gate.select_targets("azure", {"RELEASE_AZURE_MODEL": "deployment"})
    with pytest.raises(ValueError, match="RELEASE_OPENAI_TRANSCRIPTION_MODEL"):
        gate.select_targets("openai", {"RELEASE_OPENAI_MODEL": "model"})
    (target,) = gate.select_targets(
        "azure", {"RELEASE_AZURE_MODEL": "deployment", "AZURE_TRANSCRIPTION_MODEL": "transcribe"}
    )
    assert target["transcription_model"] == "transcribe"


@pytest.mark.parametrize(
    ("providers", "environ", "expected"),
    [
        (
            "azure",
            {"RELEASE_AZURE_BACKENDS": "native,litellm"},
            [("azure", "native", "transcribe-deployment"), ("azure", "litellm", "")],
        ),
        # A LiteLLM-only selection must not drop the check.
        (
            "azure",
            {"RELEASE_AZURE_BACKENDS": "litellm"},
            [("azure", "litellm", "transcribe-deployment")],
        ),
        (
            "openai",
            {"RELEASE_OPENAI_MODEL": "openai-model", "RELEASE_OPENAI_BACKENDS": "litellm"},
            [("openai", "litellm", "openai-transcribe")],
        ),
    ],
)
def test_transcription_is_certified_once_per_provider(providers, environ, expected):
    targets = gate.select_targets(
        providers, {"RELEASE_AZURE_MODEL": "deployment", **environ, **_TRANSCRIPTION_ENV}
    )
    assert [
        (target["provider"], target["backend"], target["transcription_model"]) for target in targets
    ] == expected


def test_a_provider_without_an_audio_api_cannot_select_a_transcription_model():
    (target,) = gate.select_targets("google", {"RELEASE_GOOGLE_MODEL": "gemini"})
    assert target["transcription_model"] == ""
    with pytest.raises(ValueError, match="no audio API"):
        gate.select_targets(
            "google",
            {"RELEASE_GOOGLE_MODEL": "gemini", "RELEASE_GOOGLE_TRANSCRIPTION_MODEL": "model"},
        )


def test_selected_transcription_model_is_required_in_result():
    target = {"provider": "azure", "model": "release-model", "transcription_model": "transcribe"}
    result = _passed_result()
    assert not gate.validate_live_result(result, target, 0)
    result["checks"]["transcription"] = {"ok": True}
    assert not gate.validate_live_result(result, target, 0)
    result["transcription_model"] = "transcribe"
    assert gate.validate_live_result(result, target, 0)
    result["checks"]["transcription"] = {"ok": False}
    assert not gate.validate_live_result(result, target, 0)


class _FakeAudioSegment:
    """Stands in for pydub's decoded fixture and its chunks, so no ffmpeg is needed."""

    def __init__(self, duration_ms=12_792):
        self.duration_ms = duration_ms

    def __len__(self):
        return self.duration_ms

    def __getitem__(self, item):
        return _FakeAudioSegment(min(item.stop, self.duration_ms) - item.start)

    def export(self, out_f, format="mp3", **kwargs):
        Path(out_f).write_bytes(b"chunk")


_SENTENCES = (
    "Huoltoteknikko Matti Virtanen ilmoittaa, että pumppu vuotaa kattilahuoneessa.",
    "Vuoto havaittiin maanantaina kello yhdeksän, ja kiireellisyys on korkea.",
)
_BOTH_SENTENCES = " ".join(_SENTENCES)


def _fake_audio_provider(monkeypatch, replies):
    """Route the Transcriber to a fake raw audio client that returns (or raises) the
    replies in request order: the single request, then the two chunks."""
    import gaik.software_components.transcriber.transcriber as transcriber_module

    received = []
    outcomes = iter(replies)

    def create(**kwargs):
        received.append({key: value for key, value in kwargs.items() if key != "file"})
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage=None)

    raw = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(transcriber_module, "_create_audio_client", lambda config: raw)
    # The Transcriber decodes through _decode_audio, which runs ffmpeg itself.
    monkeypatch.setattr(transcriber_module, "_decode_audio", lambda path: _FakeAudioSegment())
    monkeypatch.setattr(transcriber_module.time, "sleep", lambda seconds: None)
    return received


def _transcription_check(tmp_path, max_calls=24):
    budget = smoke.CallBudget(max_calls, 2048)
    config = {"use_azure": False, "api_key": "test-key"}
    return smoke.transcription_check(config, "gpt-4o-transcribe", budget, tmp_path), budget


def test_transcription_check_certifies_both_requests_without_keeping_transcripts(
    monkeypatch, tmp_path
):
    received = _fake_audio_provider(monkeypatch, [_BOTH_SENTENCES, *_SENTENCES])
    observation, budget = _transcription_check(tmp_path)

    assert "prompt" not in received[0]
    assert received[1]["prompt"] == smoke.TRANSCRIPTION_CONTEXT
    assert received[2]["prompt"].endswith(_SENTENCES[0])
    assert budget.calls == 3
    assert observation["single_requests"] == 1 and observation["chunk_requests"] == 2
    assert observation["anchor_hits"] == {"single": [4, 4], "chunks": [4, 4], "of": 4}
    assert "Huoltoteknikko" not in json.dumps(observation)


@pytest.mark.parametrize(
    ("replies", "message"),
    [
        # The single request skips the first sentence, as gpt-4o-transcribe did on
        # robotic speech.
        ([_SENTENCES[1], *_SENTENCES], "lost a sentence"),
        # The second chunk comes back in English.
        ([_BOTH_SENTENCES, _SENTENCES[0], "The leak was found on Monday."], "lost a sentence"),
        # The second chunk request fails; the Transcriber raises, naming its time range.
        ([_BOTH_SENTENCES, _SENTENCES[0], RuntimeError("chunk failed")], "request failed"),
    ],
)
def test_transcription_check_fails_on_a_lost_sentence_or_a_failed_chunk(
    monkeypatch, tmp_path, replies, message
):
    _fake_audio_provider(monkeypatch, replies)
    with pytest.raises(AssertionError, match=message):
        _transcription_check(tmp_path)


def test_transcription_check_fails_if_the_default_request_carries_a_prompt(monkeypatch, tmp_path):
    from gaik.software_components.transcriber import Transcriber

    # The regression of issue #100: an instruction sent as every request's prompt.
    monkeypatch.setattr(
        Transcriber,
        "__init__",
        partialmethod(Transcriber.__init__, default_prompt="Detect the language."),
    )
    _fake_audio_provider(monkeypatch, [_BOTH_SENTENCES, *_SENTENCES])
    with pytest.raises(AssertionError, match="without a prompt"):
        _transcription_check(tmp_path)


def test_transcription_check_fails_on_a_changed_fixture(monkeypatch, tmp_path):
    changed = tmp_path / "changed.mp3"
    changed.write_bytes(b"not the fixture")
    monkeypatch.setattr(smoke, "TRANSCRIPTION_FIXTURE", changed)
    received = _fake_audio_provider(monkeypatch, [])
    with pytest.raises(AssertionError, match="fixture changed"):
        _transcription_check(tmp_path)
    assert received == []


def test_transcription_requests_count_against_the_shared_budget(monkeypatch, tmp_path):
    received = _fake_audio_provider(monkeypatch, [_BOTH_SENTENCES, *_SENTENCES])
    # Two calls left: the single request and the first chunk; the budget refuses the
    # second chunk before it reaches the provider, and the check stops on the budget.
    with pytest.raises(RuntimeError, match="Live release request budget exceeded"):
        _transcription_check(tmp_path, max_calls=2)
    assert len(received) == 2


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
