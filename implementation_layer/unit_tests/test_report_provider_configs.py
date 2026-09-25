"""Report stages must retain explicit endpoints and keep provider credentials separate."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_modules.multi_source_report_generator import pipeline as report

BASE = {"provider": "aitta", "api_key": "aitta-test-key", "model": "aitta-model"}


@pytest.mark.parametrize("method", ["pdf", "image"])
def test_vision_stage_receives_report_config(monkeypatch, method):
    from gaik.software_components import parsers

    captured = {}

    def parser(config, **kwargs):
        captured.update(config)
        return SimpleNamespace(
            convert_pdf=lambda path: ["parsed"], convert_image=lambda path: "parsed"
        )

    monkeypatch.setattr(parsers, "VisionParser", parser)
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    if method == "pdf":
        assert (
            generator._parse_pdf(Path("source.pdf"), parser_choice="vision", parser_options={})
            == "parsed"
        )
    else:
        assert generator._parse_image(Path("source.png"), image_options={}) == "parsed"
    assert captured == BASE


def test_report_audio_stage_can_use_separate_config(monkeypatch):
    from gaik.software_components import transcriber

    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            transcribe=lambda *args, **kwargs: SimpleNamespace(
                enhanced_transcript=None, raw_transcript="audio"
            )
        )

    monkeypatch.setattr(transcriber, "Transcriber", create)
    audio = {"provider": "azure", "api_key": "azure-test-key"}
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    assert (
        generator._transcribe(
            Path("audio.wav"), transcriber_options={"ctor": {"api_config": audio}}
        )
        == "audio"
    )
    assert captured["api_config"] == audio


def test_explicit_legacy_vision_provider_does_not_receive_report_credentials(monkeypatch):
    from gaik.software_components import vision_extractor

    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(extract=lambda **kwargs: SimpleNamespace(data={"name": "Ada"}))

    monkeypatch.setattr(vision_extractor, "VisionExtractor", create)
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    generator._parse_image(
        Path("image.png"),
        image_options={"mode": "structured", "ctor": {"model_provider": "google"}},
    )
    assert captured == {"model_provider": "google"}


def test_provider_switch_loads_own_credentials(monkeypatch):
    from gaik.software_components import llm

    captured = {}
    monkeypatch.setattr(
        llm,
        "get_llm_config",
        lambda provider, **overrides: {
            "provider": provider,
            "api_key": "google-test-key",
            "model": "google-default",
            **overrides,
        },
    )
    monkeypatch.setattr(report, "create_llm_client", lambda config: captured.update(config))
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    generator._build_llm_client({"provider": "google", "model": "google-model"})
    assert captured == {"provider": "google", "api_key": "google-test-key", "model": "google-model"}
    assert BASE["api_key"] == "aitta-test-key"


def test_compatible_switch_validates_model_override_after_applying_it(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "compatible-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://inference.example/v1")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(report, "create_llm_client", lambda config: captured.update(config))
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    generator._build_llm_client({"provider": "openai_compatible", "model": "served-model"})
    assert captured["model"] == "served-model"
    assert captured["api_key"] == "compatible-test-key"


def test_writer_accepts_explicit_config_without_environment(monkeypatch):
    captured = {}
    monkeypatch.setattr(report, "create_llm_client", lambda config: captured.update(config))
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    writer_config = {"provider": "google", "api_key": "explicit-test-key", "model": "google"}
    generator._build_llm_client({"api_config": writer_config})
    assert captured == writer_config


def test_runtime_writer_config_is_not_sent_as_model_parameter(monkeypatch, tmp_path):
    calls = []

    class Client:
        def chat(self, messages, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                text="# Report\n\n## Section\n\nText", usage={}, model="m", provider="google"
            )

    monkeypatch.setattr(report, "create_llm_client", lambda config: Client())
    source = tmp_path / "source.txt"
    source.write_text("Synthetic evidence", encoding="utf-8")
    generator = report.MultiSourceReportGenerator(api_config=BASE)
    generator.run(
        input_paths=[source],
        sections=[{"title": "Section", "instructions": "Summarize"}],
        writer_options={"api_config": {"provider": "google", "api_key": "test", "model": "m"}},
    )
    assert len(calls) == 1
    assert "api_config" not in calls[0]


def test_saved_report_config_rejects_credentials_before_writing(tmp_path):
    target = tmp_path / "report.json"
    with pytest.raises(ValueError, match="must not contain credentials"):
        report.save_report_config(
            target,
            input_paths=[],
            sections=[{"title": "Summary", "instructions": "Summarize"}],
            writer_options={"api_config": BASE},
        )
    assert not target.exists()
