"""SRT and WebVTT subtitle utilities.

Convert Whisper transcription segments to subtitle formats, parse existing
subtitles, and chunk segments for semantic search embedding.
"""

from __future__ import annotations

import re


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    """Convert Whisper transcription segments to SRT subtitle format.

    Each segment must have ``start`` (float seconds), ``end`` (float seconds),
    and ``text`` (str) keys.

    Args:
        segments: List of segment dicts from Whisper (``{start, end, text}``).

    Returns:
        SRT-formatted string.
    """
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg["start"])
        end = _format_srt_time(seg["end"])
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments: list[dict]) -> str:
    """Convert Whisper transcription segments to WebVTT subtitle format.

    Args:
        segments: List of segment dicts from Whisper (``{start, end, text}``).

    Returns:
        WebVTT-formatted string.
    """
    lines: list[str] = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        start = _format_vtt_time(seg["start"])
        end = _format_vtt_time(seg["end"])
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
    return "\n".join(lines)


_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _parse_timestamp(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(srt_content: str) -> list[dict]:
    """Parse an SRT string into a list of segment dicts.

    Returns:
        List of ``{index, start, end, text}`` dicts.
    """
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", srt_content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # Find the timestamp line
        ts_line_idx = -1
        for idx, line in enumerate(lines):
            if _SRT_TIME_RE.search(line):
                ts_line_idx = idx
                break

        if ts_line_idx < 0:
            continue

        match = _SRT_TIME_RE.search(lines[ts_line_idx])
        if not match:
            continue

        g = match.groups()
        start = _parse_timestamp(g[0], g[1], g[2], g[3])
        end = _parse_timestamp(g[4], g[5], g[6], g[7])
        text = "\n".join(lines[ts_line_idx + 1 :]).strip()

        # Try to get index from line before timestamp
        index = None
        if ts_line_idx > 0:
            try:
                index = int(lines[ts_line_idx - 1].strip())
            except ValueError:
                pass

        if text:
            segments.append({"index": index, "start": start, "end": end, "text": text})

    return segments


def chunk_segments(
    segments: list[dict],
    target_seconds: int = 45,
    min_seconds: int = 20,
    max_seconds: int = 90,
) -> list[dict]:
    """Group short subtitle segments into longer chunks for embedding.

    Combines adjacent segments until the chunk reaches ``target_seconds``.
    Chunks are kept between ``min_seconds`` and ``max_seconds`` when possible.

    Args:
        segments: List of segment dicts with ``start``, ``end``, ``text``.
        target_seconds: Target chunk duration in seconds (default 45).
        min_seconds: Minimum chunk duration (default 20).
        max_seconds: Maximum chunk duration (default 90).

    Returns:
        List of chunked segment dicts with ``start``, ``end``, ``text``,
        ``srt_index`` (0-based chunk index).
    """
    if not segments:
        return []

    chunks: list[dict] = []
    current_texts: list[str] = []
    current_start: float | None = None
    current_end: float = 0
    chunk_idx = 0

    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_text = seg.get("text", "").strip()
        if not seg_text:
            continue

        if current_start is None:
            current_start = seg_start

        duration = seg_end - current_start

        # If adding this segment would exceed max, flush first
        if current_texts and duration > max_seconds:
            chunks.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_texts),
                "srt_index": chunk_idx,
            })
            chunk_idx += 1
            current_texts = []
            current_start = seg_start

        current_texts.append(seg_text)
        current_end = seg_end

        # If we've reached target duration, flush
        if current_start is not None and (current_end - current_start) >= target_seconds:
            chunks.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_texts),
                "srt_index": chunk_idx,
            })
            chunk_idx += 1
            current_texts = []
            current_start = None

    # Flush remaining
    if current_texts and current_start is not None:
        # If the last chunk is very short, merge with previous
        if chunks and (current_end - current_start) < min_seconds:
            prev = chunks[-1]
            prev["end"] = current_end
            prev["text"] = prev["text"] + " " + " ".join(current_texts)
        else:
            chunks.append({
                "start": current_start,
                "end": current_end,
                "text": " ".join(current_texts),
                "srt_index": chunk_idx,
            })

    return chunks


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS for display.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted string like ``"02:35"``.
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"
