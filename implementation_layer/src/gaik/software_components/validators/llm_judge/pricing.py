"""Per-million-token rates for known LLM-as-judge models.

Pattern mirrors `software_components.parsers.multimodal_parser.pricing`.
Add a new prefix when a new judge model rotates in.

Sources (2026):
- Gemini: https://ai.google.dev/gemini-api/docs/pricing
- Anthropic: https://www.anthropic.com/pricing
- OpenAI: https://openai.com/api/pricing/
- Azure OpenAI: customer-specific deal; values below are the public list price.
"""

from __future__ import annotations

# (input_per_M_USD, output_per_M_USD)
JUDGE_PRICING_PER_M: dict[str, tuple[float, float]] = {
    # OpenAI / Azure
    "gpt-5.5": (3.00, 15.00),
    "gpt-5.4": (2.50, 10.00),
    "gpt-5.4-mini": (0.25, 2.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    # Anthropic
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    # Google
    "gemini-3-flash": (0.50, 3.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-3.1-pro": (2.00, 12.00),
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
