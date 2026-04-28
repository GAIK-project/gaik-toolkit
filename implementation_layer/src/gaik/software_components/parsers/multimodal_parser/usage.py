"""Backward-compatible re-export of usage record helpers.

The canonical location is :mod:`gaik.observability.usage`. This shim
preserves the historical import path
``gaik.software_components.parsers.multimodal_parser.usage`` so existing
callers keep working.
"""

from gaik.observability.usage import UsageRecord, build_usage_record

__all__ = ["UsageRecord", "build_usage_record"]
