"""Modules can mix audio/vision providers with separate text and embedding providers."""

import importlib
from types import SimpleNamespace

import pytest

SHARED = {"provider": "openai", "api_key": "shared-test-key", "model": "shared-model"}
TEXT = {"provider": "aitta", "api_key": "aitta-test-key", "model": "text-model"}
MEDIA = {"provider": "azure", "api_key": "azure-test-key", "model": "media-model"}


@pytest.mark.parametrize("kind", ["audio", "documents"])
@pytest.mark.parametrize("shared", [SHARED, None])
def test_pipeline_uses_separate_media_and_extraction_configs(monkeypatch, kind, shared):
    module_name = f"gaik.software_modules.{kind}_to_structured_data.pipeline"
    module = importlib.import_module(module_name)
    monkeypatch.setattr(
        module,
        "get_openai_config",
        lambda **kwargs: pytest.fail(
            "Fully configured stages must not load unrelated default credentials"
        ),
    )
    calls = {}
    requirements = object()
    schema = type("Result", (), {})

    class SchemaGenerator:
        def __init__(self, config):
            calls["schema_config"] = config
            self.item_requirements = requirements

        def generate_schema(self, **kwargs):
            return schema

    class Extractor:
        def __init__(self, config, **kwargs):
            calls["extractor_config"] = config

        def extract(self, **kwargs):
            calls["documents"] = kwargs["documents"]
            return [{"value": "ok"}]

    monkeypatch.setattr(module, "SchemaGenerator", SchemaGenerator)
    monkeypatch.setattr(module, "DataExtractor", Extractor)
    if kind == "audio":

        def transcriber(**kwargs):
            calls["media_config"] = kwargs["api_config"]
            return SimpleNamespace(
                transcribe=lambda **kwargs: SimpleNamespace(
                    raw_transcript="synthetic input", enhanced_transcript=None
                )
            )

        monkeypatch.setattr(module, "Transcriber", transcriber)
        pipeline = module.AudioToStructuredData(
            api_config=shared, transcription_config=MEDIA, extraction_config=TEXT
        )
    else:

        def parser(**kwargs):
            calls["media_config"] = kwargs["openai_config"]
            return SimpleNamespace(convert_pdf=lambda *args, **kwargs: ["synthetic input"])

        monkeypatch.setattr(module, "VisionParser", parser)
        pipeline = module.DocumentsToStructuredData(
            api_config=shared, parser_config=MEDIA, extraction_config=TEXT
        )
    result = pipeline.run(file_path="synthetic", user_requirements="Extract the value")
    assert result.extracted_fields == [{"value": "ok"}]
    assert calls["schema_config"] == TEXT
    assert calls["extractor_config"] == TEXT
    assert calls["media_config"] == MEDIA
    assert calls["documents"] == ["synthetic input"]


@pytest.mark.parametrize("kind", ["audio", "documents"])
def test_omitted_stage_configs_keep_shared_config(kind):
    module = importlib.import_module(f"gaik.software_modules.{kind}_to_structured_data.pipeline")
    if kind == "audio":
        pipeline = module.AudioToStructuredData(api_config=SHARED)
        assert pipeline.transcription_config is SHARED
    else:
        pipeline = module.DocumentsToStructuredData(api_config=SHARED)
        assert pipeline.parser_config is SHARED
    assert pipeline.extraction_config is SHARED


@pytest.mark.parametrize("shared", [SHARED, None])
def test_rag_can_use_three_distinct_provider_configs(monkeypatch, shared):
    module = importlib.import_module("gaik.software_modules.RAG_workflow.pipeline")
    monkeypatch.setattr(
        module,
        "get_openai_config",
        lambda **kwargs: pytest.fail(
            "Fully configured stages must not load unrelated default credentials"
        ),
    )
    calls = {}

    def capture(name):
        def constructor(**kwargs):
            calls[name] = kwargs
            return object()

        return constructor

    for name in ("VisionRagParser", "Embedder", "VectorStore", "Retriever", "AnswerGenerator"):
        monkeypatch.setattr(module, name, capture(name))
    embedding = {"provider": "google", "api_key": "google-test-key", "embedding_model": "embed"}
    module.RAGWorkflow(
        api_config=shared, parser_config=MEDIA, embedding_config=embedding, answer_config=TEXT
    )
    assert calls["VisionRagParser"]["vision_config"] == MEDIA
    assert calls["Embedder"]["config"] == embedding
    assert calls["AnswerGenerator"]["config"] == TEXT


def test_rag_omitted_stage_configs_keep_shared_config(monkeypatch):
    module = importlib.import_module("gaik.software_modules.RAG_workflow.pipeline")
    for name in ("VisionRagParser", "Embedder", "VectorStore", "Retriever", "AnswerGenerator"):
        monkeypatch.setattr(module, name, lambda **kwargs: object())
    pipeline = module.RAGWorkflow(api_config=SHARED)
    assert pipeline.parser_config is SHARED
    assert pipeline.embedding_config is SHARED
    assert pipeline.answer_config is SHARED
