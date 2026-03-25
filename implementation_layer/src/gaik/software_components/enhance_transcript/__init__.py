"""Transcript enhancement package entry point."""

from __future__ import annotations

__all__ = []

try:
    from gaik.software_components.config import create_openai_client, get_openai_config

    __all__.extend(["get_openai_config", "create_openai_client"])
except ImportError:
    pass

try:
    from .enhance_transcript import (
        DEFAULT_MODEL_AZURE,
        DEFAULT_MODEL_OPENAI,
        PASS1_SYSTEM_PROMPT,
        PASS2_SYSTEM_PROMPT,
        CorrectionSummary,
        DiffChunk,
        TranscriptEnhancer,
        TranscriptEnhancerResult,
    )

    __all__.extend(
        [
            "TranscriptEnhancer",
            "TranscriptEnhancerResult",
            "CorrectionSummary",
            "DiffChunk",
            "DEFAULT_MODEL_AZURE",
            "DEFAULT_MODEL_OPENAI",
            "PASS1_SYSTEM_PROMPT",
            "PASS2_SYSTEM_PROMPT",
        ]
    )
except ImportError:
    pass
