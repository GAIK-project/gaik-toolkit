"""Token usage accounting for the MultimodalParser."""

from __future__ import annotations

from dataclasses import dataclass

from .pricing import Provider, compute_cost_usd


@dataclass
class UsageRecord:
    """Token counts and derived cost for a single ``MultimodalParser.parse()`` call.

    Attributes:
        provider: One of ``"openai"``, ``"claude"``, ``"google"``.
        model: Model/deployment identifier the call actually used.
        input_tokens: Prompt tokens sent to the model.
        output_tokens: Completion tokens returned (includes thinking tokens
            where applicable — they are billed at the output rate).
        thinking_tokens: Subset of ``output_tokens`` spent on reasoning
            ("thinking") when the provider exposes that breakdown.
        total_tokens: Provider-reported total (``input + output``).
        duration_s: Wall-clock time for the call in seconds.
        cost_usd: Cost computed from :mod:`pricing` rates. ``0.0`` when the
            model has no entry in the pricing table.
    """

    provider: Provider
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    duration_s: float
    cost_usd: float


def build_usage_record(
    provider: Provider,
    model: str,
    usage_dict: dict[str, int],
    duration_s: float,
) -> UsageRecord:
    """Create a :class:`UsageRecord` from raw token counts + timing."""
    input_tokens = int(usage_dict.get("input_tokens", 0) or 0)
    output_tokens = int(usage_dict.get("output_tokens", 0) or 0)
    thinking_tokens = int(usage_dict.get("thinking_tokens", 0) or 0)
    total_tokens = int(
        usage_dict.get("total_tokens") or (input_tokens + output_tokens)
    )
    cost_usd = compute_cost_usd(provider, model, input_tokens, output_tokens)
    return UsageRecord(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        total_tokens=total_tokens,
        duration_s=round(duration_s, 3),
        cost_usd=round(cost_usd, 6),
    )
