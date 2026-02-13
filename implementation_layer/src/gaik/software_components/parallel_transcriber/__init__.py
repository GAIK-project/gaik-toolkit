"""Parallel Audio/Video Transcription

Production-quality parallel transcription pipeline using FFmpeg chunking
and Azure OpenAI Whisper / GPT-4o Transcribe Diarize.

Main Classes:
    - ParallelTranscriber: High-level pipeline orchestrator
    - TranscriptionConfig: All tuneable parameters
    - TranscriptionResult: Transcription output with save/plain_text support

Models:
    - TranscriptionModel: Enum for model selection (WHISPER, GPT4O_DIARIZE)

Cancellation:
    - TranscriptionCancelled: Exception raised on cancellation
    - SimpleCancellation: Thread-safe cancellation flag

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration (from shared config)
    - create_openai_client: Create OpenAI client from config

Requirements:
    - ``openai`` (core gaik dependency)
    - ``ffmpeg`` + ``ffprobe`` on ``$PATH`` (system dependency)

Example::

    from gaik.software_components.parallel_transcriber import (
        ParallelTranscriber, TranscriptionConfig,
    )
    from gaik.software_components.config import get_openai_config

    api_cfg = get_openai_config(use_azure=True)
    config = TranscriptionConfig(chunk_duration_minutes=15)
    transcriber = ParallelTranscriber(api_cfg, config)
    result = transcriber.transcribe("interview.mp4")
    print(result.plain_text)
    result.save("output/")
"""

__all__: list[str] = []

# --- Models (no extra dependencies) ---
try:
    from .models import (  # noqa: F401
        SimpleCancellation,
        TranscriptionCancelled,
        TranscriptionModel,
        TranscriptionResult,
    )

    __all__.extend(
        [
            "TranscriptionModel",
            "TranscriptionResult",
            "TranscriptionCancelled",
            "SimpleCancellation",
        ]
    )
except ImportError:
    pass

# --- SRT utilities (no extra dependencies) ---
try:
    from .srt import parse_srt_content  # noqa: F401

    __all__.append("parse_srt_content")
except ImportError:
    pass

# --- Configuration ---
try:
    from .config import TranscriptionConfig  # noqa: F401

    __all__.append("TranscriptionConfig")
except ImportError:
    pass

# --- Pipeline (requires openai) ---
try:
    from .pipeline import ParallelTranscriber  # noqa: F401

    __all__.append("ParallelTranscriber")
except ImportError:
    pass

# --- Shared OpenAI config (from gaik.software_components.config) ---
try:
    from gaik.software_components.config import (  # noqa: F401
        create_openai_client,
        get_openai_config,
    )

    __all__.extend(["get_openai_config", "create_openai_client"])
except ImportError:
    pass
