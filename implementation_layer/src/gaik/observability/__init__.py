"""Shared observability primitives for gaik components.

Exposes a uniform ``UsageRecord`` (tokens, duration, derived cost) plus
provider-specific normalizers and a small timing helper. Components
that call an LLM should report results via these types so downstream
consumers (logging, dashboards, compliance pipelines) get a consistent
shape regardless of which component produced the call.
"""

from .pricing import (
    ANTHROPIC_PRICING_PER_M,
    GEMINI_PRICING_PER_M,
    OPENAI_PRICING_PER_M,
    Provider,
    compute_cost_usd,
    lookup_price,
)
from .providers import openai_usage_to_dict
from .timing import measure_duration
from .usage import UsageRecord, build_usage_record

__all__ = [
    "ANTHROPIC_PRICING_PER_M",
    "GEMINI_PRICING_PER_M",
    "OPENAI_PRICING_PER_M",
    "Provider",
    "UsageRecord",
    "build_usage_record",
    "compute_cost_usd",
    "lookup_price",
    "measure_duration",
    "openai_usage_to_dict",
]
