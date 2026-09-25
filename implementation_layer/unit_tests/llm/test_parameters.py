import pytest
from gaik.software_components.llm.parameters import normalize_chat_kwargs


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6-sol", "azure/gpt-6-astra", "gpt-5.6-terra"])
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


@pytest.mark.parametrize("effort", ["none", "minimal", "typo"])
def test_invalid_astra_effort_fails_before_network(effort):
    with pytest.raises(ValueError, match="reasoning_effort"):
        normalize_chat_kwargs("gpt-6-astra", {"reasoning_effort": effort})


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
