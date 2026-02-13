"""
Data models for parallel transcription.

Enums, result types, chunk specifications, and cancellation primitives.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


class TranscriptionModel(StrEnum):
    """Available transcription models."""

    WHISPER = "whisper"
    GPT4O_DIARIZE = "gpt-4o-transcribe-diarize"


@dataclass
class ChunkSpec:
    """Specification for a single audio chunk to be encoded by FFmpeg."""

    index: int
    nominal_start: float
    actual_start: float
    duration: float
    overlap_start: float
    overlap_end: float
    chunk_path: Path

    @property
    def is_last(self) -> bool:
        """Marker set externally after all specs are computed."""
        return getattr(self, "_is_last", False)

    @is_last.setter
    def is_last(self, value: bool) -> None:
        self._is_last = value


@dataclass
class TranscriptionResult:
    """Final result of a parallel transcription run."""

    content: str
    format: Literal["text", "srt", "vtt", "json", "verbose_json"]
    language: str
    model_used: str
    total_chunks: int = 1
    total_duration_seconds: float = 0.0

    @property
    def plain_text(self) -> str:
        """Extract plain text from the content, stripping SRT/VTT formatting."""
        if self.format == "text":
            return self.content
        # Strip SRT/VTT timestamps and sequence numbers
        from .srt import extract_text_from_srt

        return extract_text_from_srt(self.content)

    def save(self, path: str | Path, *, encoding: str = "utf-8") -> Path:
        """Save transcription content to a file.

        Args:
            path: Output file path (or directory — extension is added automatically).
            encoding: File encoding (default utf-8).

        Returns:
            The Path that was written.
        """
        ext_map = {
            "srt": ".srt",
            "vtt": ".vtt",
            "text": ".txt",
            "json": ".json",
            "verbose_json": ".json",
        }
        p = Path(path)
        if p.is_dir():
            p = p / f"transcription{ext_map.get(self.format, '.txt')}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.content, encoding=encoding)
        logger.info("Saved transcription to %s", p)
        return p


class TranscriptionCancelled(Exception):  # noqa: N818
    """Raised when a transcription is cancelled via the cancellation protocol."""


@dataclass
class SimpleCancellation:
    """Thread-safe cancellation flag using :class:`threading.Event`.

    Usage::

        cancel = SimpleCancellation()
        transcriber.transcribe(file, check_cancelled=cancel.check)
        # From another thread:
        cancel.cancel()
    """

    _event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        """Signal cancellation."""
        self._event.set()

    def check(self) -> None:
        """Raise :class:`TranscriptionCancelled` if cancelled."""
        if self._event.is_set():
            raise TranscriptionCancelled("Transcription cancelled")

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()
