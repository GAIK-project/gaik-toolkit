import pytest
from gaik.observability.pricing import lookup_price


@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_gpt6_standard_short_context_estimate(provider):
    assert lookup_price(provider, "gpt-6-luna") == (0.10, 0.50)
    assert lookup_price(provider, "gpt-6-sol") == (2.0, 10.0)
    assert lookup_price(provider, "gpt-6-astra") == (10.0, 50.0)


def test_native_provider_aliases_preserve_pricing():
    assert lookup_price("vertex", "gemini-2.5-flash") == lookup_price("google", "gemini-2.5-flash")
    assert lookup_price("anthropic_foundry", "claude-sonnet-4-6") == lookup_price(
        "claude", "claude-sonnet-4-6"
    )


def test_custom_endpoint_does_not_inherit_model_vendors_price():
    assert lookup_price("aitta", "gpt-6-luna") == (0.0, 0.0)
    assert lookup_price("openai_compatible", "gpt-6-luna") == (0.0, 0.0)


@pytest.mark.parametrize(
    ("model", "rates"),
    [
        ("claude-sonnet-5", (2.00, 10.00)),
        ("claude-opus-5-5", (4.00, 20.00)),
        ("claude-opus-5", (5.00, 25.00)),
        ("claude-opus-4-8", (5.00, 25.00)),
        ("claude-opus-4-7", (5.00, 25.00)),
        ("claude-fable-5-1", (10.00, 50.00)),
        ("claude-haiku-4-5", (1.00, 5.00)),
        ("claude-opus-4-1", (15.00, 75.00)),
    ],
)
def test_claude_list_prices_in_parser_and_judge_tables(model, rates):
    # The judge kept its own Claude copy, which drifted: Haiku 4.5 and Opus 4.7
    # at older models' prices, Sonnet 5 and Opus 5.5 missing and so "free".
    from gaik.software_components.validators.llm_judge.pricing import lookup_judge_price

    assert lookup_price("anthropic_foundry", model) == rates
    assert lookup_judge_price(model) == rates


@pytest.mark.parametrize(
    ("model", "rates"),
    [
        ("gpt-5.5", (5.00, 30.00)),
        ("gpt-5.4", (2.50, 15.00)),
        ("gpt-5.4-mini", (0.75, 4.50)),
        ("gpt-5-mini", (0.25, 2.00)),
        ("gpt-5.1", (1.25, 10.00)),
    ],
)
def test_openai_list_prices_agree_between_parser_and_judge(model, rates):
    # OpenAI list prices, checked 2026-09-27. The judge's own copy had gpt-5.5
    # at 3/15, gpt-5.4 at 2.5/10 and gpt-5.4-mini at 0.25/2; the shared table
    # had gpt-5-mini at 0.75/4.5.
    from gaik.software_components.validators.llm_judge.pricing import lookup_judge_price

    assert lookup_price("openai", model) == rates
    assert lookup_judge_price(model) == rates
