"""Backward-compatible re-export of pricing tables.

The canonical location is :mod:`gaik.observability.pricing`. This shim
preserves the historical import path
``gaik.software_components.parsers.multimodal_parser.pricing`` so existing
callers keep working.
"""

from gaik.observability.pricing import (
    ANTHROPIC_PRICING_PER_M,
    GEMINI_PRICING_PER_M,
    OPENAI_PRICING_PER_M,
    Provider,
    compute_cost_usd,
    lookup_price,
)

__all__ = [
    "ANTHROPIC_PRICING_PER_M",
    "GEMINI_PRICING_PER_M",
    "OPENAI_PRICING_PER_M",
    "Provider",
    "compute_cost_usd",
    "lookup_price",
]
