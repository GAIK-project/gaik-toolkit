import pytest
from gaik.software_components.llm.parameters import normalize_chat_kwargs


@pytest.mark.parametrize(
    "model",
    ["gpt-6-luna", "gpt-6-sol", "azure/gpt-6-astra", "gpt-5.6-terra", "gpt-6.1-sol"],
)
@pytest.mark.parametrize("effort", [None, "low", "medium", "high", "xhigh", "max"])
def test_reasoning_omits_incompatible_sampling_and_preserves_effort(model, effort):
    options = {"temperature": 0, "top_p": 1, "max_tokens": 128}
    if effort is not None:
        options["reasoning_effort"] = effort
    result = normalize_chat_kwargs(model, options)
    assert result == {
        "max_completion_tokens": 128,
        **({"reasoning_effort": effort} if effort is not None else {}),
    }
    assert options["temperature"] == 0


def test_nonreasoning_sol_keeps_sampling():
    options = {"temperature": 0, "top_p": 1, "reasoning_effort": "none"}
    assert normalize_chat_kwargs("gpt-6-sol", options) == options


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-sol"])
@pytest.mark.parametrize("effort", ["none", "minimal", "typo"])
def test_invalid_always_reasoning_effort_fails_before_network(model, effort):
    with pytest.raises(ValueError, match="reasoning_effort"):
        normalize_chat_kwargs(model, {"reasoning_effort": effort})


def test_deployment_alias_uses_explicit_family_and_effort():
    assert normalize_chat_kwargs(
        "my-prod",
        {"temperature": 0},
        config={"model_family": "gpt-6-astra", "reasoning_effort": "high"},
    ) == {"reasoning_effort": "high"}


def test_legacy_options_unchanged():
    options = {"temperature": 0, "max_tokens": 42}
    assert normalize_chat_kwargs("legacy-deployment", options) == options


def test_conflicting_limits_fail():
    with pytest.raises(ValueError, match="one token limit"):
        normalize_chat_kwargs("gpt-6-luna", {"max_tokens": 1, "max_completion_tokens": 2})


def test_reasoning_tools_require_responses():
    with pytest.raises(ValueError, match="Responses API"):
        normalize_chat_kwargs("gpt-6-astra", {"tools": [{"type": "function"}]})


@pytest.mark.parametrize(
    "config",
    [{"provider": "openai"}, {"provider": "azure"}, {"use_azure": True}, {"use_azure": False}],
)
@pytest.mark.parametrize("model", ["gpt-5.4", "gpt-5-mini", "o3", "o4-mini"])
def test_openai_reasoning_models_get_max_completion_tokens(config, model):
    # o-series and gpt-5.x reject max_tokens.
    options = {"temperature": 0, "max_tokens": 64}
    assert normalize_chat_kwargs(model, options, config=config) == {
        "temperature": 0,
        "max_completion_tokens": 64,
    }


@pytest.mark.parametrize("config", [{"provider": "azure"}, {"use_azure": True}])
@pytest.mark.parametrize("model", ["gpt-4o", "my-deployment"])
def test_other_openai_models_keep_max_tokens(config, model):
    # Older Azure API versions and compatible servers behind legacy configs only know max_tokens.
    options = {"max_tokens": 64}
    assert normalize_chat_kwargs(model, options, config=config) == options
    assert normalize_chat_kwargs(
        "my-deployment", options, config={**config, "model_family": "gpt-5.4"}
    ) == {"max_completion_tokens": 64}


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible", "litellm"])
def test_compatible_servers_keep_max_tokens(provider):
    options = {"max_tokens": 64}
    assert normalize_chat_kwargs(
        "google/gemma-4-31b-it", options, config={"provider": provider}
    ) == (options)


def test_conflicting_limits_fail_for_openai_api():
    with pytest.raises(ValueError, match="one token limit"):
        normalize_chat_kwargs(
            "gpt-5.4", {"max_tokens": 1, "max_completion_tokens": 2}, config={"provider": "openai"}
        )


def test_shared_openai_client_sends_max_completion_tokens():
    from types import SimpleNamespace

    from gaik.software_components.llm import create_llm_client, get_llm_config

    client = create_llm_client(get_llm_config("openai", api_key="test", model="gpt-5.4"))
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None, model="m")

    client.raw.chat.completions.create = create
    try:
        client.chat([{"role": "user", "content": "Hi"}], max_tokens=64)
    finally:
        client.raw.close()
    assert calls[0]["max_completion_tokens"] == 64
    assert "max_tokens" not in calls[0]


@pytest.mark.parametrize(
    ("model", "config", "expected"),
    [
        ("gpt-6-luna", None, True),
        ("gpt-6-sol", None, True),
        ("gpt-6-luna-2026-09-22", None, True),
        ("azure/gpt-6-luna", None, True),
        ("gpt-5.6-sol", None, True),
        ("gpt-5.6-luna", None, True),
        ("gpt-5.6-terra", None, True),
        ("production", {"model_family": "gpt-6-luna"}, True),
        ("gpt-6-astra", None, False),
        ("gpt-6-rosalind", None, False),
        ("gpt-6-cyber", None, False),
        ("gpt-6.1-sol", None, False),
        ("gpt-6.1-terra", None, False),
        ("gpt-6-luna-prod", None, False),
        ("production", {"model_family": "gpt-6-astra"}, False),
        ("production", None, False),
        ("gpt-5.4", None, False),
        ("gpt-4o", None, False),
        ("claude-sonnet-5-5", None, False),
    ],
)
def test_accepts_effort_none_is_an_allowlist(model, config, expected):
    # Only for an effort gaik picks itself: an unknown GPT-6 name gets no "none".
    from gaik.software_components.llm.parameters import _accepts_effort_none

    assert _accepts_effort_none(model, config) is expected


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6-rosalind"])
def test_explicit_none_is_still_validated_by_the_family_rule(model):
    # A caller's own "none" is checked as before: only Astra and gpt-6.x reject it here.
    assert normalize_chat_kwargs(model, {"reasoning_effort": "none"}) == {
        "reasoning_effort": "none"
    }
