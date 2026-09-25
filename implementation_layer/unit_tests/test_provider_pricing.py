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
