"""Judge shared-config routing supports text/image calls without mixing credentials."""

from types import SimpleNamespace

import pytest
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.validators.llm_judge import LLMJudge


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible", "google", "anthropic", "azure"])
def test_judge_config_routes_text_and_retains_usage(monkeypatch, provider):
    from gaik.software_components.validators.llm_judge import llm_judge

    configs = []
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return ChatResponse(
            text='{"equivalent":true,"severity":"ok","score":5,"reason":"same"}',
            model="judge-model",
            provider=provider,
            usage={"prompt_tokens": 4, "completion_tokens": 2},
        )

    client = SimpleNamespace(chat=chat)
    monkeypatch.setattr(llm_judge, "create_llm_client", lambda cfg: configs.append(cfg) or client)
    config = {"provider": provider, "model": "judge-model", "api_key": "provided-key"}
    judge = LLMJudge(config=config)
    result = judge.judge_text_pair("First sentence", "Equivalent sentence")
    assert result.equivalent
    assert result.usage.provider == provider
    assert result.usage.total_tokens == 6
    assert configs == [config]
    assert calls[0][1]["model"] == "judge-model"
    assert calls[0][1]["max_tokens"] == 4096
    assert "response_format" not in calls[0][1]


def test_judge_shared_images_use_canonical_image_parts(monkeypatch):
    from gaik.software_components.validators.llm_judge import llm_judge

    calls = []

    def chat(messages, **kwargs):
        calls.append(messages)
        return ChatResponse(text='{"flags":[]}', model="vision-model", provider="aitta")

    monkeypatch.setattr(llm_judge, "create_llm_client", lambda cfg: SimpleNamespace(chat=chat))
    judge = LLMJudge(config={"provider": "aitta", "model": "vision-model", "api_key": "key"})
    judge.validate([b"page-one", b"page-two"], extracted={"name": "Ada"})
    content = calls[0][1]["content"]
    assert content[0]["type"] == "text"
    assert len(content) == 3
    assert all(
        item["image_url"]["url"].startswith("data:image/png;base64,") for item in content[1:]
    )


def test_legacy_explicit_azure_overrides_false_flag():
    judge = LLMJudge(model_provider="azure", use_azure=False)
    assert judge.use_azure is True
    assert judge.model == "gpt-6-luna"


def test_legacy_openai_default_is_current_luna():
    assert LLMJudge(model_provider="openai", use_azure=False).model == "gpt-6-luna"


def test_legacy_astra_invalid_reasoning_fails_before_http(monkeypatch):
    from gaik.software_components.parsers.multimodal_parser import config

    monkeypatch.setattr(
        config,
        "get_openai_config",
        lambda **kwargs: {"api_key": "test", "model": "gpt-6-astra", "use_azure": False},
    )

    def unexpected_request(**kwargs):
        pytest.fail("Invalid Astra reasoning effort must fail before an HTTP request")

    monkeypatch.setattr(
        config,
        "create_openai_client",
        lambda cfg: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=unexpected_request))
        ),
    )
    judge = LLMJudge(
        model_provider="openai", use_azure=False, model="gpt-6-astra", reasoning_effort="none"
    )
    with pytest.raises(ValueError, match="reasoning_effort"):
        judge._call_openai_text("Evaluate this", "Be accurate")


def test_additional_provider_uses_shared_environment_loader(monkeypatch):
    from gaik.software_components.validators.llm_judge import llm_judge

    monkeypatch.setattr(
        llm_judge,
        "get_llm_config",
        lambda provider: {
            "provider": provider,
            "model": "configured-model",
            "api_key": "configured-key",
        },
    )
    judge = LLMJudge(model_provider="aitta")
    assert judge.model == "configured-model"
    assert judge.config["api_key"] == "configured-key"
