"""
SRT subtitle processing utilities.

Ported from QAdental's ``srt_utils.py`` — time conversion, parsing,
overlap-based deduplication, and text extraction.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def time_to_seconds(time_str: str) -> float:
    """Convert an SRT timestamp (``HH:MM:SS,mmm``) to seconds.

    Both comma and dot are accepted as the fractional separator.
    """
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds_and_ms = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds_and_ms


def seconds_to_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (``HH:MM:SS,mmm``)."""
    # Whole milliseconds first: formatting 59.9996 s on its own rounds the
    # seconds field up to "60,000".
    total_ms = max(0, round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_text_for_comparison(text: str) -> str:
    """Normalize text for duplicate detection (lowercase, strip punctuation)."""
    normalized = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(normalized.split())


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_srt_content(srt_content: str) -> list[dict]:
    """Parse SRT content into a list of subtitle dicts.

    Each dict has keys: ``start_time``, ``end_time``, ``start_seconds``,
    ``end_seconds``, ``text``.
    """
    subtitles: list[dict] = []
    blocks = srt_content.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        start_time_str, end_time_str = lines[1].split(" --> ")
        text = "\n".join(lines[2:])

        subtitles.append(
            {
                "start_time": start_time_str.strip(),
                "end_time": end_time_str.strip(),
                "start_seconds": time_to_seconds(start_time_str.strip()),
                "end_seconds": time_to_seconds(end_time_str.strip()),
                "text": text.strip(),
            }
        )

    return subtitles


# ---------------------------------------------------------------------------
# Combining / overlap deduplication
# ---------------------------------------------------------------------------


def _first_own_start(srt_content: str, overlap_start: float) -> float | None:
    """Seconds from a chunk's own start to its first subtitle that is not all overlap.

    ``0.0`` when that subtitle began in the leading overlap; ``None`` when the
    chunk has no subtitle past its leading overlap.
    """
    for subtitle in parse_srt_content(srt_content):
        if subtitle["end_seconds"] > overlap_start:
            return max(0.0, subtitle["start_seconds"] - overlap_start)
    return None


def combine_srt_chunks(
    srt_transcriptions: list[str],
    chunk_metadata: list[dict] | None = None,
) -> str:
    """Combine multiple SRT chunks into a single SRT file.

    Timestamps are adjusted so each chunk continues from the correct
    absolute position.  When *chunk_metadata* is provided (from overlap-based
    splitting), the overlap between two chunks is taken from one of them: a
    subtitle that ends before a chunk's own start belongs to the chunk before,
    and one that starts in a chunk's trailing overlap belongs to the chunk
    after, from that chunk's first subtitle on. A subtitle that crosses the
    boundary is kept from both, unless both chunks give it the same text.

    Args:
        srt_transcriptions: List of SRT content strings (one per chunk).
        chunk_metadata: Optional list of dicts with ``overlap_start``,
            ``overlap_end``, and ``nominal_start`` keys.

    Returns:
        Combined SRT content with sequential subtitle numbers and adjusted
        timestamps.
    """
    if not srt_transcriptions:
        return ""
    if len(srt_transcriptions) == 1:
        return srt_transcriptions[0]

    logger.debug("Combining %d SRT transcriptions …", len(srt_transcriptions))

    # Extract overlap info
    overlap_info: list[dict] = []
    if chunk_metadata:
        for chunk in chunk_metadata:
            overlap_info.append(
                {
                    "overlap_start": chunk.get("overlap_start", 0),
                    "overlap_end": chunk.get("overlap_end", 0),
                    "nominal_start": chunk.get("nominal_start", 0),
                }
            )

    combined_srt = ""
    current_subtitle_number = 1
    time_offset = 0.0
    # Recent subtitle texts for duplicate detection: normalized_text → end_seconds
    recent_texts: dict[str, float] = {}

    for chunk_index, srt_content in enumerate(srt_transcriptions):
        if not srt_content.strip():
            continue

        blocks = srt_content.strip().split("\n\n")

        chunk_overlap_start = 0.0
        if overlap_info and chunk_index < len(overlap_info):
            chunk_overlap_start = overlap_info[chunk_index].get("overlap_start", 0)
            if chunk_index > 0:
                time_offset = overlap_info[chunk_index]["nominal_start"]

        # Where the next chunk takes over, in this chunk's own time: at the
        # next chunk's first subtitle of its own. What starts later in this
        # chunk's trailing overlap is in the next chunk too. No cut when the
        # next chunk has no subtitle of its own: then only this chunk holds it.
        chunk_cut: float | None = None
        next_index = chunk_index + 1
        if (
            next_index < len(overlap_info)
            and next_index < len(srt_transcriptions)
            and overlap_info[chunk_index]["overlap_end"] > 0
        ):
            next_start = _first_own_start(
                srt_transcriptions[next_index], overlap_info[next_index]["overlap_start"]
            )
            if next_start is not None:
                chunk_cut = (
                    chunk_overlap_start
                    + overlap_info[next_index]["nominal_start"]
                    - overlap_info[chunk_index]["nominal_start"]
                    + next_start
                )

        # Texts of the chunks before this one, for the duplicate check below.
        earlier_texts = dict(recent_texts)

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            start_time, end_time = lines[1].split(" --> ")
            original_start = time_to_seconds(start_time)
            original_end = time_to_seconds(end_time)

            # Skip subtitles that start in the overlap with the next chunk
            if chunk_cut is not None and original_start >= chunk_cut:
                continue

            # Skip subtitles entirely within the overlap region (already in prev chunk)
            if chunk_index > 0 and chunk_overlap_start > 0:
                if original_end <= chunk_overlap_start:
                    continue
                if original_start < chunk_overlap_start:
                    original_start = chunk_overlap_start

            # Adjust timestamps
            if chunk_index == 0:
                start_seconds = original_start
                end_seconds = original_end
            else:
                adjusted_start = original_start - chunk_overlap_start
                adjusted_end = original_end - chunk_overlap_start
                start_seconds = time_offset + adjusted_start
                end_seconds = time_offset + adjusted_end

            subtitle_text = "\n".join(lines[2:])

            # Text-based duplicate detection. With overlap metadata a duplicate
            # is the same text from an earlier chunk that was still running when
            # this subtitle starts: both chunks transcribed the same speech. The
            # same words said again after that one ended are kept.
            normalized_text = _normalize_text_for_comparison(subtitle_text)
            if chunk_index > 0 and overlap_info:
                earlier_end = earlier_texts.get(normalized_text)
                if earlier_end is not None and start_seconds < earlier_end:
                    continue
            elif chunk_index > 0 and normalized_text in recent_texts:
                if abs(start_seconds - recent_texts[normalized_text]) < 5:
                    continue

            new_start = seconds_to_time(start_seconds)
            new_end = seconds_to_time(end_seconds)

            combined_srt += f"{current_subtitle_number}\n"
            combined_srt += f"{new_start} --> {new_end}\n"
            combined_srt += f"{subtitle_text}\n\n"

            recent_texts[normalized_text] = end_seconds
            current_subtitle_number += 1

        # Prune old entries to limit memory growth
        if chunk_index > 0:
            cutoff_time = time_offset - 60
            recent_texts = {k: v for k, v in recent_texts.items() if v > cutoff_time}

    logger.debug("Combined SRT: %d subtitles", current_subtitle_number - 1)
    return combined_srt.strip()


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text_from_srt(srt_content: str) -> str:
    """Extract plain text from SRT content, stripping timestamps and numbers."""
    text_lines: list[str] = []
    for line in srt_content.split("\n"):
        stripped = line.strip()
        if stripped.isdigit() or "-->" in stripped or not stripped:
            continue
        text_lines.append(stripped)
    return " ".join(text_lines)
