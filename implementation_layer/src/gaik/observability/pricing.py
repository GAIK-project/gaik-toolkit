"""Token pricing tables shared across gaik components.

Rates are USD per million tokens in ``(input, output)`` order. Reasoning /
thinking tokens are billed at the output rate across all three providers.

Sources (2026-03-25):
- OpenAI: https://developers.openai.com/api/docs/pricing
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
- Google Gemini: https://ai.google.dev/gemini-api/docs/pricing

Tables use prefix matching (see :func:`lookup_price`) so that sibling models
like ``gemini-3.1-flash`` vs ``gemini-3.1-flash-lite`` resolve to the right
row regardless of date suffixes.
"""

from __future__ import annotations

from typing import Literal

Provider = Literal["openai", "claude", "google"]

OPENAI_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "gpt-5.5-deployment": (5.00, 30.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5-mini": (0.75, 4.50),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}

ANTHROPIC_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-3-5": (0.80, 4.00),
    "claude-haiku-3": (0.25, 1.25),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-sonnet-3": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-opus-4-1": (15.00, 75.00),
    "claude-opus-4": (15.00, 75.00),
}

GEMINI_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "gemini-3-flash": (0.50, 3.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-pro": (2.00, 12.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
}

_TABLE_BY_PROVIDER: dict[Provider, dict[str, tuple[float, float]]] = {
    "openai": OPENAI_PRICING_PER_M,
    "claude": ANTHROPIC_PRICING_PER_M,
    "google": GEMINI_PRICING_PER_M,
}


def lookup_price(provider: Provider, model: str) -> tuple[float, float]:
    """Return ``(input_per_M, output_per_M)`` USD rates for a model.

    Uses longest-prefix matching so ``gemini-3.1-flash-lite-preview`` resolves
    to the ``gemini-3.1-flash-lite`` row rather than ``gemini-3-flash``.
    Returns ``(0.0, 0.0)`` if no prefix matches — caller should treat that as
    "pricing unknown" and still report zero cost.
    """
    table = _TABLE_BY_PROVIDER.get(provider, {})
    matches = [(p, rates) for p, rates in table.items() if model.startswith(p)]
    if not matches:
        return (0.0, 0.0)
    return max(matches, key=lambda x: len(x[0]))[1]


def compute_cost_usd(
    provider: Provider,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Compute cost in USD for a completed call.

    ``output_tokens`` should already include reasoning/thinking tokens —
    these are billed at the output rate.
    """
    input_rate, output_rate = lookup_price(provider, model)
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
