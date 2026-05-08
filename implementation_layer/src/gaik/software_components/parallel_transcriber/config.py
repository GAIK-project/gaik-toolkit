"""
Configuration for parallel transcription.

All tuneable knobs live in :class:`TranscriptionConfig`.  Sensible defaults
are provided; override via constructor kwargs or :meth:`from_env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from .models import TranscriptionModel


@dataclass
class TranscriptionConfig:
    """All parameters that control the parallel transcription pipeline.

    Defaults match the production values used in QAdental.
    """

    # --- Chunk sizing ---
    chunk_duration_minutes: int = 20
    chunk_overlap_seconds: float = 15.0
    max_single_file_mb: float = 24.0

    # --- GPT-4o specific ---
    gpt4o_chunk_duration_minutes: int = 23  # 25 min API limit minus 2 min safety margin

    # --- Whisper Local (on-prem) specific ---
    # On-prem servers typically run Whisper on a single GPU and process one
    # request at a time. Default chunking matches the Azure Whisper params,
    # parallelism is conservative (2) so the GPU queue stays small.
    whisper_local_chunk_duration_minutes: int = 20
    whisper_local_chunk_parallelism: int = 2
    whisper_local_request_timeout_seconds: int = 1800  # per chunk POST timeout
    whisper_local_max_audio_minutes: float = 360.0  # hard cap (6 h) before refusing

    # --- Parallelism ---
    ffmpeg_split_workers: int = 3
    transcription_workers: int = 3
    ffmpeg_threads_per_process: int = 1
    gpt4o_chunk_parallelism: int = 4

    # --- Timeouts ---
    ffmpeg_chunk_timeout_seconds: int = 3600
    api_timeout_seconds: int = 180

    # --- Retry ---
    max_retries: int = 2
    retry_base_delay_seconds: float = 1.0
    max_429_retries: int = 4

    # --- Audio encoding ---
    audio_bitrate: str = "128k"
    audio_sample_rate: int = 16000
    audio_channels: int = 1

    # --- Output ---
    response_format: Literal["text", "srt", "vtt", "json", "verbose_json"] = "srt"
    language: str | None = None  # None → auto-detect
    prompt: str | None = None  # Optional Whisper prompt

    # --- Model selection ---
    model: TranscriptionModel = TranscriptionModel.WHISPER

    @classmethod
    def from_env(cls) -> TranscriptionConfig:
        """Build a config by reading environment variables (all optional).

        Supported env vars (with defaults from the dataclass):

        - ``CHUNK_DURATION_MINUTES``
        - ``CHUNK_OVERLAP_SECONDS``
        - ``MAX_SINGLE_FILE_MB``
        - ``GPT4O_CHUNK_DURATION_MINUTES``
        - ``WHISPER_LOCAL_CHUNK_DURATION_MINUTES``
        - ``WHISPER_LOCAL_CHUNK_PARALLELISM``
        - ``WHISPER_LOCAL_REQUEST_TIMEOUT_SECONDS``
        - ``WHISPER_LOCAL_MAX_AUDIO_MINUTES``
        - ``FFMPEG_SPLIT_WORKERS``
        - ``TRANSCRIPTION_WORKERS``
        - ``FFMPEG_THREADS_PER_PROCESS`` / ``FFMPEG_THREADS``
        - ``GPT4O_CHUNK_PARALLELISM``
        - ``FFMPEG_CHUNK_TIMEOUT_SECONDS``
        - ``API_TIMEOUT_SECONDS`` / ``AZURE_OPENAI_TIMEOUT_SECONDS``
        - ``MAX_RETRIES``
        - ``RETRY_BASE_DELAY_SECONDS``
        - ``MAX_429_RETRIES``
        - ``AUDIO_BITRATE``
        - ``AUDIO_SAMPLE_RATE``
        - ``AUDIO_CHANNELS``
        - ``RESPONSE_FORMAT``
        - ``TRANSCRIPTION_LANGUAGE``
        - ``WHISPER_PROMPT``
        - ``TRANSCRIPTION_MODEL``
        """

        def _int(name: str, *alt_names: str, default: int | None = None) -> int | None:
            for n in (name, *alt_names):
                val = os.getenv(n)
                if val is not None:
                    return int(val)
            return default

        def _float(name: str, *alt_names: str, default: float | None = None) -> float | None:
            for n in (name, *alt_names):
                val = os.getenv(n)
                if val is not None:
                    return float(val)
            return default

        def _str(name: str, *alt_names: str, default: str | None = None) -> str | None:
            for n in (name, *alt_names):
                val = os.getenv(n)
                if val is not None:
                    return val
            return default

        kwargs: dict = {}

        v = _int("CHUNK_DURATION_MINUTES")
        if v is not None:
            kwargs["chunk_duration_minutes"] = v

        v_f = _float("CHUNK_OVERLAP_SECONDS")
        if v_f is not None:
            kwargs["chunk_overlap_seconds"] = v_f

        v_f = _float("MAX_SINGLE_FILE_MB")
        if v_f is not None:
            kwargs["max_single_file_mb"] = v_f

        v = _int("GPT4O_CHUNK_DURATION_MINUTES")
        if v is not None:
            kwargs["gpt4o_chunk_duration_minutes"] = v

        v = _int("WHISPER_LOCAL_CHUNK_DURATION_MINUTES")
        if v is not None:
            kwargs["whisper_local_chunk_duration_minutes"] = v

        v = _int("WHISPER_LOCAL_CHUNK_PARALLELISM")
        if v is not None:
            kwargs["whisper_local_chunk_parallelism"] = v

        v = _int("WHISPER_LOCAL_REQUEST_TIMEOUT_SECONDS")
        if v is not None:
            kwargs["whisper_local_request_timeout_seconds"] = v

        v_f = _float("WHISPER_LOCAL_MAX_AUDIO_MINUTES")
        if v_f is not None:
            kwargs["whisper_local_max_audio_minutes"] = v_f

        v = _int("FFMPEG_SPLIT_WORKERS")
        if v is not None:
            kwargs["ffmpeg_split_workers"] = v

        v = _int("TRANSCRIPTION_WORKERS")
        if v is not None:
            kwargs["transcription_workers"] = v

        v = _int("FFMPEG_THREADS_PER_PROCESS", "FFMPEG_THREADS")
        if v is not None:
            kwargs["ffmpeg_threads_per_process"] = v

        v = _int("GPT4O_CHUNK_PARALLELISM")
        if v is not None:
            kwargs["gpt4o_chunk_parallelism"] = v

        v = _int("FFMPEG_CHUNK_TIMEOUT_SECONDS")
        if v is not None:
            kwargs["ffmpeg_chunk_timeout_seconds"] = v

        v = _int("API_TIMEOUT_SECONDS", "AZURE_OPENAI_TIMEOUT_SECONDS")
        if v is not None:
            kwargs["api_timeout_seconds"] = v

        v = _int("MAX_RETRIES")
        if v is not None:
            kwargs["max_retries"] = v

        v_f = _float("RETRY_BASE_DELAY_SECONDS")
        if v_f is not None:
            kwargs["retry_base_delay_seconds"] = v_f

        v = _int("MAX_429_RETRIES")
        if v is not None:
            kwargs["max_429_retries"] = v

        v_s = _str("AUDIO_BITRATE")
        if v_s is not None:
            kwargs["audio_bitrate"] = v_s

        v = _int("AUDIO_SAMPLE_RATE")
        if v is not None:
            kwargs["audio_sample_rate"] = v

        v = _int("AUDIO_CHANNELS")
        if v is not None:
            kwargs["audio_channels"] = v

        v_s = _str("RESPONSE_FORMAT")
        if v_s is not None:
            kwargs["response_format"] = v_s  # type: ignore[assignment]

        v_s = _str("TRANSCRIPTION_LANGUAGE")
        if v_s is not None:
            kwargs["language"] = v_s

        v_s = _str("WHISPER_PROMPT")
        if v_s is not None:
            kwargs["prompt"] = v_s

        v_s = _str("TRANSCRIPTION_MODEL")
        if v_s is not None:
            kwargs["model"] = TranscriptionModel(v_s)

        return cls(**kwargs)
