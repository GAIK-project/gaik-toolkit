"""Audio and Video Transcription

This module provides audio/video transcription using OpenAI Whisper with optional GPT enhancement.

Main Classes:
    - Transcriber: High-level transcription API with chunking and enhancement
    - TranscriptionResult: Container for raw and enhanced transcripts

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration for transcription
    - create_openai_client: Create OpenAI client from config

Utilities:
    - split_and_transcribe: Chunk and transcribe long audio files
    - split_and_transcribe_with_context: Transcribe with context awareness
    - post_process_transcript: Enhance transcript using GPT
    - DEFAULT_PROMPT: Default transcription prompt for Whisper

Example:
    >>> from gaik.transcriber import Transcriber, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> transcriber = Transcriber(config)
    >>> result = transcriber.transcribe("audio.mp3", enhance=True)
    >>> result.save("output/")
"""

__all__ = []

# Configuration (requires openai, python-dotenv)
try:
    from gaik.config import create_openai_client, get_openai_config
    __all__.extend(["get_openai_config", "create_openai_client"])
except ImportError:
    pass

# Transcription (requires openai, pydub)
try:
    from .transcriber import (
        DEFAULT_PROMPT,
        Transcriber,
        TranscriptionResult,
        post_process_transcript,
        split_and_transcribe,
        split_and_transcribe_with_context,
    )
    __all__.extend([
        "Transcriber",
        "TranscriptionResult",
        "split_and_transcribe",
        "split_and_transcribe_with_context",
        "post_process_transcript",
        "DEFAULT_PROMPT",
    ])
except ImportError:
    pass
