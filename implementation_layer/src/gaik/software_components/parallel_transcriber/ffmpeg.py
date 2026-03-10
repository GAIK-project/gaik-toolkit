"""
FFmpeg operations for audio extraction and chunk splitting.

Ported from QAdental's ``audio/utils.py`` and ``ffmpeg_utils.py``.

IMPORTANT: Always use ``communicate()`` (not ``wait()``) when piping
stdout/stderr to avoid deadlocks.  FFmpeg writes progress to stderr;
if the pipe buffer fills (~64 KB), FFmpeg blocks and we deadlock.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .config import TranscriptionConfig
from .models import ChunkSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


def check_ffmpeg_available() -> bool:
    """Return True if both ``ffmpeg`` and ``ffprobe`` are on ``$PATH``."""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            return False
    return True


# ---------------------------------------------------------------------------
# Duration / stream queries
# ---------------------------------------------------------------------------


def get_audio_duration(file_path: str | Path) -> float:
    """Get duration in seconds using ``ffprobe``.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        subprocess.CalledProcessError: If ffprobe fails.
    """
    file_path = str(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            file_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def has_video_stream(file_path: str | Path) -> bool:
    """Return True if *file_path* contains a video stream (ffprobe)."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            timeout=30,
        )
        return len(result.stdout.strip()) > 0
    except Exception:
        return False


def has_audio_stream(file_path: str | Path) -> bool:
    """Return True if *file_path* contains an audio stream (ffprobe).

    Fail-open: returns True if ffprobe itself fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            timeout=30,
        )
        return len(result.stdout.strip()) > 0
    except Exception:
        return True  # fail-open


# ---------------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------------


def extract_audio(
    input_path: str | Path,
    output_path: str | Path,
    config: TranscriptionConfig | None = None,
) -> Path:
    """Extract audio from a video file using FFmpeg.

    Uses ``communicate()`` to drain pipes and avoid the 64 KB buffer deadlock.

    Args:
        input_path: Source video file.
        output_path: Destination audio file (mp3).
        config: Optional config for encoding parameters.

    Returns:
        Path to the created audio file.

    Raises:
        FileNotFoundError: If *input_path* does not exist.
        RuntimeError: If FFmpeg fails.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    cfg = config or TranscriptionConfig()

    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        cfg.audio_bitrate,
        "-ar",
        str(cfg.audio_sample_rate),
        "-ac",
        str(cfg.audio_channels),
        "-compression_level",
        "0",
        "-threads",
        str(cfg.ffmpeg_threads_per_process),
        "-y",
        str(output_path),
    ]

    logger.info("Extracting audio: %s -> %s", input_path.name, output_path.name)

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    # communicate() drains both pipes — prevents 64 KB buffer deadlock
    _stdout, stderr = process.communicate(timeout=cfg.ffmpeg_chunk_timeout_seconds)

    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed (exit {process.returncode}): {stderr[:500]}")

    if not output_path.exists():
        raise RuntimeError("FFmpeg did not create the output file")

    logger.info(
        "Audio extracted: %.1f MB",
        output_path.stat().st_size / (1024 * 1024),
    )
    return output_path


# ---------------------------------------------------------------------------
# Chunk spec computation
# ---------------------------------------------------------------------------


def compute_chunk_specs(
    total_duration: float,
    chunk_duration_minutes: int,
    overlap_seconds: float,
    output_dir: Path,
    file_stem: str,
) -> list[ChunkSpec]:
    """Compute chunk specifications with overlap.

    Args:
        total_duration: Total audio duration in seconds.
        chunk_duration_minutes: Nominal chunk length in minutes.
        overlap_seconds: Overlap between adjacent chunks in seconds.
        output_dir: Directory for chunk files.
        file_stem: Base name for chunk files.

    Returns:
        List of :class:`ChunkSpec` instances.
    """
    chunk_duration_seconds = chunk_duration_minutes * 60
    num_chunks = int((total_duration + chunk_duration_seconds - 1) / chunk_duration_seconds)

    specs: list[ChunkSpec] = []
    for i in range(num_chunks):
        nominal_start = i * chunk_duration_seconds
        actual_start = max(0, nominal_start - overlap_seconds) if i > 0 else 0

        if nominal_start >= total_duration:
            break

        remaining_from_nominal = total_duration - nominal_start
        base_duration = min(chunk_duration_seconds, remaining_from_nominal)

        is_last_chunk = (nominal_start + chunk_duration_seconds) >= total_duration
        end_overlap = (
            0
            if is_last_chunk
            else min(overlap_seconds, total_duration - (nominal_start + base_duration))
        )

        actual_duration = (nominal_start - actual_start) + base_duration + end_overlap

        if actual_duration < 5.0:
            logger.info("Skipping chunk %d — too short (%.1fs)", i + 1, actual_duration)
            break

        chunk_filename = f"{file_stem}_chunk_{i + 1:02d}.mp3"
        chunk_path = output_dir / chunk_filename

        spec = ChunkSpec(
            index=i,
            nominal_start=nominal_start,
            actual_start=actual_start,
            duration=actual_duration,
            overlap_start=nominal_start - actual_start,
            overlap_end=end_overlap,
            chunk_path=chunk_path,
        )
        spec.is_last = is_last_chunk
        specs.append(spec)

    return specs


# ---------------------------------------------------------------------------
# Parallel splitting
# ---------------------------------------------------------------------------


def split_into_chunks(
    audio_file_path: str | Path,
    specs: list[ChunkSpec],
    config: TranscriptionConfig | None = None,
    check_cancelled: Callable[[], None] | None = None,
    strip_video: bool = False,
) -> list[dict]:
    """Split an audio file into chunks using parallel FFmpeg processes.

    Failed chunks are retried sequentially before giving up.

    Args:
        audio_file_path: Source audio (or video when *strip_video* is True).
        specs: List of :class:`ChunkSpec` from :func:`compute_chunk_specs`.
        config: Transcription configuration.
        check_cancelled: Optional cancellation callback.
        strip_video: If True, add ``-vn`` to strip video streams.

    Returns:
        List of result dicts with ``"file"`` and ``"metadata"`` keys,
        sorted by chunk index.

    Raises:
        RuntimeError: If ffmpeg is not available or no chunks are created.
    """
    if not check_ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH")

    cfg = config or TranscriptionConfig()
    audio_file_path = str(audio_file_path)
    total_specs = len(specs)
    max_workers = max(1, min(total_specs, cfg.ffmpeg_split_workers))
    output_dir = specs[0].chunk_path.parent

    logger.info(
        "Splitting %d chunks (workers=%d, threads_per=%d, temp=%s)",
        total_specs,
        max_workers,
        cfg.ffmpeg_threads_per_process,
        output_dir,
    )

    def _encode_chunk(spec: ChunkSpec) -> dict:
        """Encode a single chunk. Returns dict with 'file'+'metadata' on success,
        or 'error'+'index' on failure."""
        if check_cancelled:
            check_cancelled()

        cmd = [
            "ffmpeg",
            "-ss",
            str(spec.actual_start),
            "-i",
            audio_file_path,
            "-t",
            str(spec.duration),
        ]
        if strip_video:
            cmd.append("-vn")
        cmd.extend(
            [
                "-acodec",
                "libmp3lame",
                "-b:a",
                cfg.audio_bitrate,
                "-ar",
                str(cfg.audio_sample_rate),
                "-ac",
                str(cfg.audio_channels),
                "-compression_level",
                "0",
                "-avoid_negative_ts",
                "make_zero",
                "-nostdin",
                "-threads",
                str(cfg.ffmpeg_threads_per_process),
                "-y",
                str(spec.chunk_path),
            ]
        )

        logger.info(
            "Creating chunk %d/%d: %.1fs–%.1fs (overlap: start=%.1fs, end=%.1fs)",
            spec.index + 1,
            total_specs,
            spec.actual_start,
            spec.actual_start + spec.duration,
            spec.overlap_start,
            spec.overlap_end,
        )

        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
            )
            _stdout, stderr = process.communicate(timeout=cfg.ffmpeg_chunk_timeout_seconds)

            if process.returncode != 0:
                msg = f"FFmpeg exit {process.returncode}: {stderr[:300]}"
                logger.error("Chunk %d failed: %s", spec.index + 1, msg)
                return {"error": msg, "index": spec.index}

            chunk_path = spec.chunk_path
            if not chunk_path.exists():
                msg = "FFmpeg did not create output file"
                logger.error("Chunk %d: %s", spec.index + 1, msg)
                return {"error": msg, "index": spec.index}

            chunk_size_mb = chunk_path.stat().st_size / (1024 * 1024)
            if chunk_size_mb <= 0.1 and not spec.is_last:
                logger.warning(
                    "Chunk %d too small (%.1f MB), skipping",
                    spec.index + 1,
                    chunk_size_mb,
                )
                chunk_path.unlink(missing_ok=True)
                return {"error": f"chunk too small ({chunk_size_mb:.2f} MB)", "index": spec.index}

            logger.info(
                "Chunk %d/%d: %s (%.1f MB)",
                spec.index + 1,
                total_specs,
                chunk_path.name,
                chunk_size_mb,
            )

            return {
                "file": str(chunk_path),
                "metadata": {
                    "index": spec.index,
                    "nominal_start": spec.nominal_start,
                    "actual_start": spec.actual_start,
                    "overlap_start": spec.overlap_start,
                    "overlap_end": spec.overlap_end,
                },
            }
        except subprocess.TimeoutExpired:
            logger.error("Chunk %d timed out", spec.index + 1)
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                pass
            spec.chunk_path.unlink(missing_ok=True)
            return {"error": "FFmpeg timed out", "index": spec.index}
        except Exception as exc:
            logger.error("Error creating chunk %d: %s", spec.index + 1, exc)
            spec.chunk_path.unlink(missing_ok=True)
            return {"error": f"{type(exc).__name__}: {exc}", "index": spec.index}

    # ── Parallel pass ─────────────────────────────────────────────
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_encode_chunk, specs))

    successful = [r for r in results if "file" in r]
    failed = [r for r in results if "error" in r]

    # ── Sequential retry for failed chunks ────────────────────────
    if failed:
        logger.warning(
            "%d/%d chunks failed in parallel pass, retrying sequentially",
            len(failed),
            total_specs,
        )
        still_failed = []
        for fail_result in failed:
            spec = specs[fail_result["index"]]
            retry = _encode_chunk(spec)
            if "file" in retry:
                logger.info("Chunk %d recovered on retry", spec.index + 1)
                successful.append(retry)
            else:
                still_failed.append(retry)
        failed = still_failed

    successful.sort(key=lambda r: r["metadata"]["index"])

    logger.info(
        "Chunk splitting complete: %d succeeded, %d failed",
        len(successful),
        len(failed),
    )

    if not successful:
        error_msgs = [r["error"] for r in failed]
        detail = "; ".join(error_msgs[:5]) if error_msgs else "unknown"
        raise RuntimeError(f"No chunks created. Errors: {detail}")

    # Save metadata for overlap deduplication
    metadata_path = output_dir / "chunk_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "overlap_seconds": specs[0].overlap_start if len(specs) > 1 else 0,
                "chunks": [r["metadata"] for r in successful],
            },
            indent=2,
        )
    )

    return successful


# ---------------------------------------------------------------------------
# Convenience: full split pipeline
# ---------------------------------------------------------------------------


def split_audio(
    audio_file_path: str | Path,
    *,
    config: TranscriptionConfig | None = None,
    check_cancelled: Callable[[], None] | None = None,
    total_duration: float | None = None,
    chunk_duration_minutes: int | None = None,
    force_by_duration: bool = False,
    strip_video: bool = False,
) -> tuple[list[str], list[dict] | None]:
    """High-level helper: measure → compute specs → split → return paths + metadata.

    Returns:
        Tuple of (chunk_file_paths, chunk_metadata_list).
        If no splitting was needed, returns ``([audio_file_path], None)``.
    """
    cfg = config or TranscriptionConfig()
    audio_file_path = Path(audio_file_path)
    if not audio_file_path.exists():
        raise FileNotFoundError(f"File not found: {audio_file_path}")

    file_size_mb = audio_file_path.stat().st_size / (1024 * 1024)

    # Skip splitting if file is small enough (unless forced)
    if not force_by_duration and not strip_video and file_size_mb <= cfg.max_single_file_mb:
        logger.info("File %.1f MB is within limits, no chunking needed", file_size_mb)
        return [str(audio_file_path)], None

    # Measure duration if not provided
    if total_duration is None:
        total_duration = get_audio_duration(str(audio_file_path))
    logger.info("Total duration: %.1f min", total_duration / 60)

    cdm = chunk_duration_minutes or cfg.chunk_duration_minutes
    output_dir = Path(tempfile.mkdtemp(prefix="parallel_transcriber_chunks_"))

    specs = compute_chunk_specs(
        total_duration=total_duration,
        chunk_duration_minutes=cdm,
        overlap_seconds=cfg.chunk_overlap_seconds,
        output_dir=output_dir,
        file_stem=audio_file_path.stem,
    )

    if not specs:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError("No chunk specs generated (audio too short?)")

    try:
        results = split_into_chunks(
            audio_file_path,
            specs,
            config=cfg,
            check_cancelled=check_cancelled,
            strip_video=strip_video,
        )
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise

    chunk_files = [r["file"] for r in results]
    chunk_metadata = [r["metadata"] for r in results]
    return chunk_files, chunk_metadata
