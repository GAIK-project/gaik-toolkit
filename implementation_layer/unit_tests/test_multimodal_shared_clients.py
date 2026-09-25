"""Shared-config multimodal components use canonical messages and validated outputs."""

import base64
import json
from types import SimpleNamespace

import fitz
import httpx
import pytest
from gaik.software_components.extractor.schema import ExtractionRequirements, FieldSpec
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.parsers.multimodal_parser import MultimodalParser
from gaik.software_components.parsers.multimodal_parser.chat_content import (
    build_chat_document_content,
)
from gaik.software_components.vision_extractor import VisionExtractor
from pydantic import BaseModel


class Name(BaseModel):
    name: str


class _SharedClient:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.raw = SimpleNamespace(close=self.close)

    def close(self):
        self.closed = True

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return ChatResponse(
            text="# Parsed\n\nName: Ada",
            model="served-vision",
            provider="aitta",
            usage={
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "total_tokens": 5,
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        )

    def chat_parsed(self, messages, response_format, **kwargs):
        self.calls.append((messages, kwargs))
        return response_format(name="Ada")


def _pdf(path):
    with fitz.open() as document:
        document.new_page().insert_text((20, 20), "First page")
        document.new_page().insert_text((20, 20), "Second page")
        document.save(path)


def test_pdf_is_rendered_as_ordered_png_messages(tmp_path):
    path = tmp_path / "two-pages.pdf"
    _pdf(path)
    content = build_chat_document_content([path], "Read these pages")
    assert content[0] == {"type": "text", "text": "Read these pages"}
    labels = [item["text"] for item in content[1:] if item["type"] == "text"]
    assert labels == ["two-pages.pdf, page 1", "two-pages.pdf, page 2"]
    images = [item["image_url"]["url"] for item in content if item["type"] == "image_url"]
    assert len(images) == 2
    for url in images:
        assert url.startswith("data:image/png;base64,")
        assert base64.b64decode(url.split(",", 1)[1]).startswith(b"\x89PNG")


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible", "google", "anthropic", "azure"])
def test_multimodal_parser_routes_shared_config(monkeypatch, tmp_path, provider):
    from gaik.software_components import llm

    path = tmp_path / "input.pdf"
    _pdf(path)
    client = _SharedClient()
    configs = []

    def create(config):
        configs.append(config)
        return client

    monkeypatch.setattr(llm, "create_llm_client", create)
    config = {"provider": provider, "model": "served-vision", "api_key": "test-key"}
    result = MultimodalParser(api_config=config).parse(path)
    assert "Name: Ada" in result.clean_markdown
    assert result.usage.input_tokens == 2
    assert result.usage.output_tokens == 3
    assert result.usage.thinking_tokens == 1
    assert result.usage.total_tokens == 5
    assert configs == [config]
    assert len(client.calls[0][0][1]["content"]) == 5
    assert client.calls[0][1]["max_tokens"] == 32768
    assert "reasoning_effort" not in client.calls[0][1]
    assert ("timeout" in client.calls[0][1]) is (provider == "anthropic")
    assert client.closed


@pytest.mark.parametrize("effort", [None, "none"])
def test_shared_parser_accepts_any_legacy_reasoning_effort(monkeypatch, tmp_path, effort):
    from gaik.software_components import llm

    path = tmp_path / "input.pdf"
    _pdf(path)
    client = _SharedClient()
    monkeypatch.setattr(llm, "create_llm_client", lambda config: client)
    config = {"provider": "azure", "model": "gpt-6-luna", "api_key": "test-key"}
    result = MultimodalParser(api_config=config, reasoning_effort=effort).parse(path)
    assert "Name: Ada" in result.clean_markdown
    assert "reasoning_effort" not in client.calls[0][1]


def test_legacy_parser_validates_reasoning_effort_per_provider(monkeypatch):
    monkeypatch.setattr(MultimodalParser, "_build_config", lambda self: {"model": "test-model"})
    assert MultimodalParser(model_provider="openai", reasoning_effort="none").reasoning_effort == (
        "none"
    )
    for provider, effort in [("claude", "none"), ("google", "none"), ("openai", None)]:
        with pytest.raises(ValueError, match="Unsupported reasoning_effort"):
            MultimodalParser(model_provider=provider, reasoning_effort=effort)


@pytest.mark.parametrize("configured_timeout", [None, 1200.0])
@pytest.mark.parametrize("provider", ["anthropic", "anthropic_foundry"])
@pytest.mark.parametrize("component", ["parser", "extractor"])
def test_anthropic_shared_call_skips_sdk_streaming_guard(
    tmp_path, component, provider, configured_timeout
):
    pytest.importorskip("anthropic")
    path = tmp_path / "input.pdf"
    _pdf(path)
    timeouts = []

    def handle(request):
        timeouts.append(request.extensions["timeout"]["read"])
        block = (
            {"type": "text", "text": "# Parsed\n\nName: Ada"}
            if component == "parser"
            else {"type": "tool_use", "id": "toolu_test", "name": "Name", "input": {"name": "Ada"}}
        )
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [block],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        # 32768 non-streaming tokens make the SDK refuse a request without a timeout.
        config = {
            "provider": provider,
            "model": "claude-test",
            "api_key": "test-key",
            "resource": "test-resource",
            "http_client": http_client,
            "max_retries": 0,
            "timeout": configured_timeout,
        }
        if component == "parser":
            result = MultimodalParser(api_config=config).parse(path)
            assert "Name: Ada" in result.clean_markdown
            assert (result.usage.input_tokens, result.usage.output_tokens) == (2, 3)
        else:
            data, _ = VisionExtractor(api_config=config)._call_shared(
                [path], "system", "user", Name
            )
            assert data == {"name": "Ada"}
    assert timeouts == [configured_timeout or 900.0]


def test_webp_image_keeps_media_type_without_platform_mapping(monkeypatch, tmp_path):
    import mimetypes

    # Python < 3.13 has no built-in .webp mapping.
    monkeypatch.setattr(mimetypes, "guess_type", lambda *args, **kwargs: (None, None))
    path = tmp_path / "scan.webp"
    path.write_bytes(b"synthetic-webp")
    content = build_chat_document_content([path], "Read this image")
    assert content[-1]["image_url"]["url"].startswith("data:image/webp;base64,")


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible", "google", "anthropic", "azure"])
def test_vision_extractor_uses_shared_structured_output(monkeypatch, tmp_path, provider):
    from gaik.software_components import llm

    path = tmp_path / "input.png"
    path.write_bytes(b"synthetic-image")
    client = _SharedClient()
    configs = []
    monkeypatch.setattr(llm, "create_llm_client", lambda config: configs.append(config) or client)
    config = {"provider": provider, "model": "served-vision", "api_key": "test-key"}
    extractor = VisionExtractor(api_config=config)
    requirements = ExtractionRequirements(
        use_case_name="name",
        fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
    )
    result = extractor.extract(
        file_paths=[path],
        user_requirements="Extract the name",
        extraction_model=Name,
        requirements=requirements,
    )
    assert result.data == {"name": "Ada"}
    assert result.usage is None
    assert configs == [config]
    assert client.calls[0][0][1]["content"][-1]["type"] == "image_url"
    assert client.closed


def test_vision_schema_generation_keeps_same_provider(monkeypatch):
    from gaik.software_components.vision_extractor import vision_extractor

    configs = []
    requirements = object()

    def generator(config):
        configs.append(config)
        return SimpleNamespace(generate_schema=lambda prompt: Name, item_requirements=requirements)

    monkeypatch.setattr(vision_extractor, "SchemaGenerator", generator)
    config = {"provider": "aitta", "model": "vision-model", "api_key": "aitta-key"}
    extractor = VisionExtractor(api_config=config, model="override-model")
    assert extractor._resolve_schema("Extract name", None) == (Name, requirements)
    assert configs == [{**config, "model": "override-model"}]
    assert config["model"] == "vision-model"


@pytest.mark.parametrize("injected_transport", [False, True])
@pytest.mark.parametrize("component", ["parser", "extractor"])
def test_failed_model_call_respects_transport_ownership(
    monkeypatch, tmp_path, injected_transport, component
):
    from gaik.software_components import llm

    path = tmp_path / "input.pdf"
    _pdf(path)
    client = _SharedClient()

    def fail(*args, **kwargs):
        raise RuntimeError("provider failed")

    client.chat = fail
    client.chat_parsed = fail
    monkeypatch.setattr(llm, "create_llm_client", lambda config: client)
    config = {"provider": "aitta", "model": "model"}
    if injected_transport:
        config["http_client"] = object()
    with pytest.raises(RuntimeError, match="provider failed"):
        if component == "parser":
            MultimodalParser(api_config=config).parse(path)
        else:
            VisionExtractor(api_config=config)._call_shared([path], "system", "user", Name)
    assert client.closed is not injected_transport


def test_parser_then_extractor_can_reuse_caller_http_client(tmp_path):
    path = tmp_path / "input.pdf"
    _pdf(path)
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        structured = "response_format" in requests[-1]
        content = '{"name":"Ada"}' if structured else "# Parsed\n\nName: Ada"
        return httpx.Response(
            200,
            json={
                "id": "chat_test",
                "object": "chat.completion",
                "created": 0,
                "model": "served-vision",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        config = {
            "provider": "aitta",
            "api_key": "test",
            "model": "served-vision",
            "http_client": http_client,
            "max_retries": 0,
        }
        parsed = MultimodalParser(api_config=config).parse(path)
        assert "Name: Ada" in parsed.clean_markdown
        assert not http_client.is_closed
        requirements = ExtractionRequirements(
            use_case_name="name",
            fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
        )
        extracted = VisionExtractor(api_config=config).extract(
            file_paths=[path],
            user_requirements="Extract the name",
            extraction_model=Name,
            requirements=requirements,
        )
        assert extracted.data == {"name": "Ada"}
        assert not http_client.is_closed
    assert http_client.is_closed
    assert len(requests) == 2
