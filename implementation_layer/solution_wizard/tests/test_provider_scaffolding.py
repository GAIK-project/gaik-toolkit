"""Execute generated PoCs with real workflow/config/schema plumbing and fake inference."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc

EXAMPLES = Path(__file__).parent.parent / "examples"
MODELS = {
    "azure": "gpt-6-luna",
    "openai": "gpt-6-luna",
    "google": "gemini-test",
    "aitta": "google/gemma-4-31b-it",
    "litellm": "openai/gpt-6-luna",
}


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch):
    import dotenv

    # Import config before clearing env: it loads .env once at module import.
    from gaik.software_components.llm import config  # noqa: F401

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    for key in os.environ:
        if (
            key.startswith(
                ("OPENAI_", "AZURE_", "AITTA_", "GOOGLE_", "GEMINI_", "LITELLM_", "LLM_")
            )
            or key == "EMBEDDING_MODEL"
        ):
            monkeypatch.delenv(key, raising=False)
    for prefix in ("OPENAI", "AZURE", "GOOGLE", "AITTA", "LITELLM"):
        monkeypatch.setenv(f"{prefix}_API_KEY", f"fake-{prefix.lower()}")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://azure.invalid/")


def _blueprint(example, models, *, judge=False):
    bp = Blueprint.from_file(EXAMPLES / example)
    bp.models = models
    bp.target_output_spec = {
        "schema_name": "Contact",
        "fields": ["name"],
        "required_fields": ["name"],
    }
    if not judge:
        bp.components.selected_building_blocks = [
            x for x in bp.components.selected_building_blocks if x != "LLMJudge"
        ]
        bp.workflow.steps = [step for step in bp.workflow.steps if step.component != "LLMJudge"]
    return bp


def _load_runner(poc_dir, monkeypatch):
    monkeypatch.delitem(sys.modules, "provider_config", raising=False)
    monkeypatch.syspath_prepend(str(poc_dir))
    spec = importlib.util.spec_from_file_location("generated_provider_poc", poc_dir / "run_poc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pdf(path):
    import fitz

    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Name: Ada")
        pdf.save(path)


def _fake_extraction(monkeypatch, captured):
    from gaik.software_components.extractor import extractor

    def parse(*, config, response_format, messages, **kwargs):
        captured.append(config)
        assert "Name: Ada" in messages[-1]["content"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=response_format(name="Ada")))],
            usage=None,
        )

    monkeypatch.setattr(extractor, "_parse_with", parse)


@pytest.mark.parametrize("provider", MODELS)
def test_generated_document_runs_each_provider_through_real_pipeline(
    tmp_path, monkeypatch, provider
):
    from gaik.software_components.parsers.vision import VisionParser

    parsed, extracted = [], []

    def vision(self, messages):
        parsed.append(self._request_config)
        assert any(part.get("type") == "image_url" for part in messages[-1]["content"])
        return "Name: Ada"

    monkeypatch.setattr(VisionParser, "_chat_content", vision)
    _fake_extraction(monkeypatch, extracted)
    bp = _blueprint(
        "document_extraction_blueprint.json",
        {"provider": provider, "extraction_model": MODELS[provider]},
    )
    result = scaffold_poc(bp, tmp_path)
    poc = result["poc_dir"]
    _pdf(poc / "sample_input" / "contact.pdf")
    runner = _load_runner(poc, monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(poc / "run_poc.py")])
    runner.main()
    assert json.loads((poc / "output" / "contact_result.json").read_text()) == [{"name": "Ada"}]
    assert parsed[0]["provider"] == extracted[0]["provider"] == provider
    assert parsed[0]["model"] == extracted[0]["model"] == MODELS[provider]
    assert extracted[0]["api_key"] == f"fake-{provider}"
    if provider == "aitta":
        assert parsed[0]["base_url"] == "https://aitta-api.csc.fi/openai/v1"
    requirements = (poc / "requirements.txt").read_text()
    for selected, extra in (("google", "llm-google"), ("litellm", "llm-litellm")):
        assert (f"gaik[{extra}]" in requirements) == (selected == provider)


def test_generated_audio_uses_separate_openai_and_aitta_credentials(tmp_path, monkeypatch):
    from gaik.software_components.transcriber import Transcriber

    transcribed, extracted = [], []

    def transcribe(self, file_path, **kwargs):
        transcribed.append(self.api_config)
        assert self._resolve_transcription_model() == "gpt-4o-transcribe"
        return SimpleNamespace(raw_transcript="Name: Ada", enhanced_transcript="Name: Ada")

    monkeypatch.setattr(Transcriber, "transcribe", transcribe)
    _fake_extraction(monkeypatch, extracted)
    bp = _blueprint(
        "incident_reporting_blueprint.json",
        {
            "provider": "aitta",
            "extraction_model": MODELS["aitta"],
            "base_url": "https://aitta.invalid/openai/v1",
            "transcription_config": {
                "provider": "openai",
                "transcription_model": "gpt-4o-transcribe",
            },
        },
    )
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    (poc / "sample_input" / "note.wav").write_bytes(b"fake audio; inference is stubbed")
    runner = _load_runner(poc, monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(poc / "run_poc.py")])
    runner.main()
    assert json.loads((poc / "output" / "note_ticket.json").read_text()) == [{"name": "Ada"}]
    assert transcribed[0]["provider"] == "openai"
    assert transcribed[0]["api_key"] == "fake-openai"
    assert transcribed[0]["base_url"] is None
    assert transcribed[0]["model"] == "gpt-6-luna"
    assert extracted[0]["provider"] == "aitta"
    assert extracted[0]["api_key"] == "fake-aitta"
    assert extracted[0]["base_url"] == "https://aitta.invalid/openai/v1"


def test_audio_provider_guard_applies_at_generation_and_after_config_edit(tmp_path, monkeypatch):
    bp = _blueprint("incident_reporting_blueprint.json", {"provider": "aitta"})
    with pytest.raises(ValueError, match="OpenAI/Azure transcription_config"):
        scaffold_poc(bp, tmp_path)
    bp.models["transcription_config"] = {"provider": "openai"}
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    runner = _load_runner(poc, monkeypatch)
    config = runner.load_config()
    config["stages"]["transcription"]["provider"] = "google"
    with pytest.raises(ValueError, match="stages.transcription"):
        runner.get_stage_config(config, "transcription")


def test_stage_overrides_and_legacy_config_are_resolved_before_validation(tmp_path, monkeypatch):
    bp = _blueprint(
        "document_extraction_blueprint.json",
        {
            "provider": "openai_compatible",
            "model": "served-model",
            "base_url": "https://inference.invalid/v1",
        },
    )
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    runner = _load_runner(poc, monkeypatch)
    stage = runner.get_stage_config(runner.load_config(), "extraction")
    assert stage["base_url"] == "https://inference.invalid/v1"
    assert stage["model"] == "served-model"
    legacy = runner.get_stage_config(
        {"use_azure": False, "models": {"extraction": "legacy-model"}}, "extraction"
    )
    assert legacy["provider"] == "openai"
    assert legacy["model"] == "legacy-model"
    azure = runner.get_stage_config({"provider": "azure_openai"}, "extraction")
    assert azure["provider"] == "azure"


def test_generated_config_omits_secrets_and_requires_explicit_embedding_model(tmp_path):
    bp = _blueprint("rag_workflow_blueprint.json", {"provider": "aitta"})
    with pytest.raises(ValueError, match="embedding_model"):
        scaffold_poc(bp, tmp_path)
    bp.models["embedding_config"] = {"provider": "google"}
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    config = yaml.safe_load((poc / "config.yaml").read_text())
    assert config["stages"]["embedding"]["provider"] == "google"
    assert "api_key" not in (poc / "config.yaml").read_text()
    bp.models["embedding_config"]["api_key"] = "not-allowed"
    with pytest.raises(ValueError, match="Keep credentials"):
        scaffold_poc(bp, tmp_path)


def test_custom_azure_audio_deployment_and_resource_reach_component(tmp_path, monkeypatch):
    from gaik.software_components.transcriber import Transcriber

    seen = []

    def transcribe(self, file_path, **kwargs):
        seen.append(self.api_config)
        assert self._resolve_transcription_model() == "my-audio-deployment"
        return SimpleNamespace(raw_transcript="Name: Ada", enhanced_transcript="")

    monkeypatch.setattr(Transcriber, "transcribe", transcribe)
    _fake_extraction(monkeypatch, [])
    bp = _blueprint(
        "incident_reporting_blueprint.json",
        {
            "provider": "aitta",
            "transcription_config": {
                "provider": "azure",
                "transcription_model": "my-audio-deployment",
                "azure_endpoint": "https://other-azure.invalid/",
                "azure_audio_endpoint": "https://audio-azure.invalid/",
            },
        },
    )
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    (poc / "sample_input" / "note.wav").write_bytes(b"stub audio")
    runner = _load_runner(poc, monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(poc / "run_poc.py")])
    runner.main()
    assert seen[0]["azure_endpoint"] == "https://other-azure.invalid/"
    assert seen[0]["azure_audio_endpoint"] == "https://audio-azure.invalid/"
    assert seen[0]["api_key"] == "fake-azure"
    bp.models["transcription_config"] = {
        "provider": "azure",
        "base_url": "https://ambiguous.invalid/v1",
    }
    with pytest.raises(ValueError, match="azure_endpoint or azure_audio_endpoint"):
        scaffold_poc(bp, tmp_path)
    config = runner.load_config()
    config["stages"]["transcription"] = bp.models["transcription_config"]
    with pytest.raises(ValueError, match="azure_endpoint or azure_audio_endpoint"):
        runner.get_stage_config(config, "transcription")


def test_generated_rag_indexes_and_answers_with_independent_stages(tmp_path, monkeypatch):
    from gaik.software_components.llm.base import ChatResponse
    from gaik.software_components.RAG.answer_generator import generator
    from gaik.software_components.RAG.embedder import embedder
    from gaik.software_modules.RAG_workflow import pipeline
    from langchain_core.documents import Document

    configurations, calls = {}, []

    class InferenceStub:
        raw = None

        def __init__(self, config):
            self.provider = config["provider"]
            self.model = config["model"]
            configurations[self.provider] = config

        def chat(self, messages, **kwargs):
            assert "Name: Ada" in messages[-1]["content"]
            calls.append(("answer", self.provider, kwargs["model"]))
            return ChatResponse("Ada", self.model, self.provider)

        def embed(self, texts, **kwargs):
            calls.append(("embed", self.provider, kwargs["model"]))
            return [[1.0, 0.0] for _ in texts]

        def chat_parsed(self, *args, **kwargs):
            raise AssertionError("not used")

        def chat_stream(self, *args, **kwargs):
            raise AssertionError("not used")

    class DocumentConversionStub:
        def __init__(self, *, vision_config):
            configurations["parser"] = vision_config

        def convert_doc_to_chunks_with_vision(self, path, **kwargs):
            assert Path(path).is_file()
            return [Document(page_content="Name: Ada", metadata={"source": "contact.pdf"})]

    class StoreStub:
        def __init__(self, **kwargs):
            self.persist = kwargs["persist"]
            self.persist_path = kwargs["persist_path"]

        def add(self, documents, vectors):
            assert vectors == [[1.0, 0.0]]
            self.documents = documents

        def search(self, vector, **kwargs):
            assert vector == [1.0, 0.0]
            return [(doc, 1.0) for doc in self.documents]

    monkeypatch.setattr(pipeline, "VisionRagParser", DocumentConversionStub)
    monkeypatch.setattr(pipeline, "VectorStore", StoreStub)
    monkeypatch.setattr(embedder, "build_compat_client", InferenceStub)
    monkeypatch.setattr(generator, "build_compat_client", InferenceStub)
    bp = _blueprint(
        "rag_workflow_blueprint.json",
        {
            "provider": "aitta",
            "extraction_model": MODELS["aitta"],
            "parser_config": {"provider": "google", "model": "gemini-vision"},
            "embedding_config": {"provider": "openai", "embedding_model": "text-embedding-3-small"},
            "answer_config": {"provider": "litellm", "model": "openai/gpt-6-luna"},
        },
    )
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    _pdf(poc / "sample_input" / "contact.pdf")
    runner = _load_runner(poc, monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(poc / "run_poc.py"), "--query", "What is the name?"])
    runner.main()
    assert json.loads((poc / "output" / "query_result.json").read_text())["answer"] == "Ada"
    assert configurations["parser"]["provider"] == "google"
    assert configurations["parser"]["api_key"] == "fake-google"
    assert configurations["openai"]["api_key"] == "fake-openai"
    assert configurations["litellm"]["api_key"] == "fake-litellm"
    assert calls == [
        ("embed", "openai", "text-embedding-3-small"),
        ("embed", "openai", "text-embedding-3-small"),
        ("answer", "litellm", "openai/gpt-6-luna"),
    ]
    dependencies = (poc / "requirements.txt").read_text()
    assert "gaik[llm-google]" in dependencies and "gaik[llm-litellm]" in dependencies


def test_bundled_promoted_hybrid_keeps_wiring_and_separate_providers(tmp_path, monkeypatch):
    from gaik.software_components.transcriber import Transcriber
    from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge
    from solution_wizard import scaffolder

    seen, extracted = [], []

    def transcribe(self, file_path, **kwargs):
        assert self._resolve_transcription_model() == "audio-deployment"
        seen.append(("transcription", self.api_config["provider"]))
        return SimpleNamespace(raw_transcript="Name: Ada", enhanced_transcript="")

    def judge(self, source_text, extracted):
        assert "AUDIO TRANSCRIPT:" in source_text and "DOCUMENT:" in source_text
        assert extracted == {"name": "Ada"}
        seen.append(("judge", self.config["provider"]))
        return SimpleNamespace(flags=[])

    monkeypatch.setattr(Transcriber, "transcribe", transcribe)
    monkeypatch.setattr(LLMJudge, "detect_hallucinations", judge)
    _fake_extraction(monkeypatch, extracted)
    bp = _blueprint(
        "incident_reporting_blueprint.json",
        {
            "provider": "aitta",
            "transcription_config": {
                "provider": "azure",
                "transcription_model": "audio-deployment",
            },
            "judge_config": {"provider": "google"},
        },
    )
    bp.components.selected_modules = []
    bp.components.selected_building_blocks = [
        "Transcriber",
        "PyMuPDFParser",
        "DataExtractor",
        "LLMJudge",
    ]
    pattern = "hybrid_dataextractor_pymupdfparser_transcriber_831947a5"
    # Isolate the promoted catalog key: this test executes the actual bundled template.
    monkeypatch.setattr(scaffolder, "_derive_pattern_key", lambda blueprint: pattern)
    generated = scaffold_poc(bp, tmp_path)
    assert generated["pattern"] == pattern and generated["template_wired"] is True
    poc = generated["poc_dir"]
    (poc / "sample_input" / "note.wav").write_bytes(b"stub audio")
    _pdf(poc / "sample_input" / "contact.pdf")
    runner = _load_runner(poc, monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(poc / "run_poc.py")])
    runner.main()
    assert json.loads((poc / "output" / "result.json").read_text()) == {"name": "Ada"}
    assert json.loads((poc / "output" / "validation.json").read_text())["passed"] is True
    assert seen == [("transcription", "azure"), ("judge", "google")]
    assert extracted[0]["provider"] == "aitta"
