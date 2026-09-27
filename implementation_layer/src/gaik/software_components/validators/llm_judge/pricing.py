"""Per-million-token rates for LLM-as-judge models.

The judge reads the shared tables in :mod:`gaik.observability.pricing`, so a
model is priced in one place. It used to keep its own copy, which drifted:
GPT-5.5, GPT-5.4 and GPT-5.4-mini, Haiku 4.5 and Opus 4.7 at other models'
prices, and Sonnet 5 and Opus 5.5 missing (reported as free).
"""

from __future__ import annotations

from gaik.observability.pricing import (
    ANTHROPIC_PRICING_PER_M,
    GEMINI_PRICING_PER_M,
    OPENAI_PRICING_PER_M,
)

# (input_per_M_USD, output_per_M_USD). The prefixes do not overlap across
# providers (gpt-, claude-, gemini-), so one merged table is unambiguous.
JUDGE_PRICING_PER_M: dict[str, tuple[float, float]] = {
    **OPENAI_PRICING_PER_M,
    **ANTHROPIC_PRICING_PER_M,
    **GEMINI_PRICING_PER_M,
}


def lookup_judge_price(model: str) -> tuple[float, float]:
    """Return (input_per_M_USD, output_per_M_USD) for *model*.

    Matches by longest-prefix so a new model id like ``gemini-3-flash-Q3``
    still resolves to the closest known rate. Returns ``(0.0, 0.0)`` when no
    prefix matches; callers see ``cost_usd == 0.0`` and know the table needs
    an update.
    """
    best: tuple[float, float] = (0.0, 0.0)
    best_len = 0
    for prefix, rates in JUDGE_PRICING_PER_M.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = rates, len(prefix)
    return best


def compute_judge_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of one call given token counts."""
    in_rate, out_rate = lookup_judge_price(model)
    return (in_rate * input_tokens + out_rate * output_tokens) / 1_000_000
