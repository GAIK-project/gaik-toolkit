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
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePath

from gaik.software_components._log_names import file_tag
from gaik.software_components.input_limits import PROBE_TIMEOUT_SECONDS, media_input_args

from .config import TranscriptionConfig
from .models import ChunkSpec

logger = logging.getLogger(__name__)

# The same ffprobe timeout as the input limit checks.
FFPROBE_TIMEOUT_SECONDS = PROBE_TIMEOUT_SECONDS
# Decoding reads the whole recording; six hours of audio decode in well under this.
DECODE_TIMEOUT_SECONDS = 600


# How far a chunk's encoded length may fall short of the length asked for before it is
# retried (and, after the retry, counts as a gap when audio continues past it): MP3
# frames and seeking cost fractions of a second. Lengths, not file sizes, so the check
# holds at every bitrate.
_CHUNK_LENGTH_TOLERANCE_SECONDS = 1.0
# The least audio a chunk must hold, and must add past the chunks before it, to be
# sent: OpenAI refuses audio under 0.1 s, and a model asked about a fraction of a second
# of near-silence can make words up. FFmpeg encodes a chunk that starts past the end of
# the audio as empty, so this only decides about a real tail, which at 0.25 s is part
# of a word at most; a longer tail shorter than the tolerance above is kept.
_MIN_TAIL_SECONDS = 0.25


def _paths_tagged(exc: BaseException, *paths: str | PurePath | None, limit: int = 300) -> str:
    """``"OSError: ... file 3f9a1c2b.mp3"``: the error with every spelling of each path,
    and of the folder it is in, replaced by its tag.

    Like :func:`~gaik.software_components._log_names.error_text`, but the spellings of
    all the paths are replaced together, longest first: path by path, one path's name
    tagged inside another's spelling first would leave that other's folders in the text.
    A file's name and stem are replaced only as a whole word (a recording named
    ``audio.mp3`` leaves "audio stream" alone): the stem only before an extension, a
    quote or a path separator.
    """
    text = f"{type(exc).__name__}: {exc}"
    # spelling -> (tag, how it must stand in the text)
    tags: dict[str, tuple[str, str]] = {}
    for path in paths:
        if not path:
            continue
        whole = str(path)
        pure = PurePath(whole)
        tag = file_tag(whole)
        for form in (whole, whole.replace("\\", "\\\\")):
            # A path given as a bare file name is matched as a name, as a whole word.
            tags.setdefault(form, (tag, "path" if re.search(r"[\\/]", form) else "name"))
        tags.setdefault(pure.name, (tag, "name"))
        tags.setdefault(pure.stem, (tag, "stem"))
        folder = str(pure.parent)
        if folder not in (".", "", pure.anchor):
            folder_tag = "folder " + file_tag(folder).split(" ", 1)[1]
            for form in (folder, folder.replace("\\", "\\\\")):
                tags.setdefault(form, (folder_tag, "path"))
    for form in sorted(tags, key=len, reverse=True):
        if len(form) < 3:
            continue
        tag, kind = tags[form]
        if kind == "path":
            text = text.replace(form, tag)
            continue
        after = r"(?![\w-])" if kind == "name" else r"(?=\.\w|['\"\\/])"
        text = re.sub(rf"(?<![\w.-]){re.escape(form)}{after}", lambda _m, t=tag: t, text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _encoded_seconds(chunk_path: Path) -> float | None:
    """Length in seconds of an encoded chunk; 0.0 when it holds no readable audio, and
    None when reading its length timed out, so its length is not known."""
    try:
        return get_audio_duration(chunk_path, decode_timeout=FFPROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        logger.warning("Reading the length of %s timed out", file_tag(chunk_path))
        return None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning(
            "Could not read the length of %s: %s",
            file_tag(chunk_path),
            _paths_tagged(exc, chunk_path),
        )
        return 0.0


def _clock(seconds: float) -> str:
    """``seconds`` as ``H:MM:SS``, for naming a stretch of a recording."""
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


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


def get_audio_duration(
    file_path: str | Path,
    *,
    timeout: float = FFPROBE_TIMEOUT_SECONDS,
    decode_timeout: float = DECODE_TIMEOUT_SECONDS,
) -> float:
    """Get duration in seconds using ``ffprobe``.

    A file whose container holds no duration (ffprobe prints ``N/A``), such as a
    WebM that a browser wrote while it recorded, is measured by decoding its audio.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        subprocess.CalledProcessError: If ffprobe fails, or ffmpeg cannot decode
            a file without a duration.
        subprocess.TimeoutExpired: If ffprobe runs longer than *timeout* seconds,
            or decoding longer than *decode_timeout* seconds.
        ValueError: If neither ffprobe nor decoding gives a length.
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
            *media_input_args(file_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        logger.info("%s has no duration in its header; decoding it", file_tag(file_path))
        return decoded_audio_seconds(file_path, timeout=decode_timeout)


def decoded_audio_seconds(
    file_path: str | Path, *, timeout: float = DECODE_TIMEOUT_SECONDS
) -> float:
    """Length in seconds of the first audio stream, measured by decoding all of it.

    Raises:
        subprocess.CalledProcessError: If ffmpeg cannot open or decode the file.
        subprocess.TimeoutExpired: If decoding runs longer than *timeout* seconds.
        ValueError: If ffmpeg decodes no audio.
    """
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            *media_input_args(file_path),
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-progress",
            "pipe:1",
            "-nostats",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    # -progress ends with the position of the last decoded sample.
    for line in reversed(result.stdout.splitlines()):
        key, _, value = line.partition("=")
        if key == "out_time_us" and value.strip().isdigit() and int(value) > 0:
            return int(value) / 1_000_000
    raise ValueError(f"No audio could be decoded from {Path(file_path).name}")


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
                *media_input_args(file_path),
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
                *media_input_args(file_path),
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
        *media_input_args(input_path),
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

    logger.info("Extracting audio: %s -> %s", file_tag(input_path), file_tag(output_path))

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    # communicate() drains both pipes — prevents 64 KB buffer deadlock
    try:
        _stdout, stderr = process.communicate(timeout=cfg.ffmpeg_chunk_timeout_seconds)
    except subprocess.TimeoutExpired:
        # communicate() leaves the process running on a timeout: stop it and
        # collect it before the error goes on.
        process.kill()
        process.communicate()
        raise

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

    Each chunk's encoded length is read back with ffprobe. A chunk FFmpeg fails on,
    or one shorter than asked for, is retried sequentially. After the retry, a
    chunk that still fails, or one that is short while audio continues past its
    end, stops the split and names its time range. Chunks past the real end of the
    audio, which a file whose header overstates its length produces, are skipped
    and logged, and a split in which no chunk holds audio raises.

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
        RuntimeError: If ffmpeg is not available, no chunk holds audio, or a
            chunk cannot be created in full even on retry; the message names the
            missing time ranges.
    """
    if not check_ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH")

    cfg = config or TranscriptionConfig()
    audio_file_path = str(audio_file_path)
    total_specs = len(specs)
    max_workers = max(1, min(total_specs, cfg.ffmpeg_split_workers))
    output_dir = specs[0].chunk_path.parent

    logger.info(
        "Splitting %d chunks (workers=%d, threads_per=%d)",
        total_specs,
        max_workers,
        cfg.ffmpeg_threads_per_process,
    )

    def _encode_chunk(spec: ChunkSpec) -> dict:
        """Encode a single chunk. Returns dict with 'file'+'metadata' on success,
        or 'error'+'index' on failure."""
        if check_cancelled:
            check_cancelled()

        cmd = [
            "ffmpeg",
            # stderr then holds the error alone, not the banner and progress lines.
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(spec.actual_start),
            *media_input_args(audio_file_path),
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
                # FFmpeg's message names the input and the chunk file (built from the
                # input's name): it goes into the error raised to the caller, and the
                # log line keeps only the exit code.
                msg = f"FFmpeg exit {process.returncode}: {stderr[:300]}"
                logger.error("Chunk %d failed: FFmpeg exit %d", spec.index + 1, process.returncode)
                return {"error": msg, "index": spec.index}

            chunk_path = spec.chunk_path
            if not chunk_path.exists():
                msg = "FFmpeg did not create output file"
                logger.error("Chunk %d: %s", spec.index + 1, msg)
                return {"error": msg, "index": spec.index}

            seconds = _encoded_seconds(chunk_path)
            logger.info(
                "Chunk %d/%d (%.1f s of %.1f s, %.1f MB)",
                spec.index + 1,
                total_specs,
                seconds if seconds is not None else float("nan"),
                spec.duration,
                chunk_path.stat().st_size / (1024 * 1024),
            )

            return {
                "file": str(chunk_path),
                "seconds": seconds,
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
            logger.error(
                "Error creating chunk %d: %s",
                spec.index + 1,
                _paths_tagged(
                    exc, audio_file_path, Path(audio_file_path).absolute(), spec.chunk_path
                ),
            )
            spec.chunk_path.unlink(missing_ok=True)
            return {"error": f"{type(exc).__name__}: {exc}", "index": spec.index}

    # ── Parallel pass ─────────────────────────────────────────────
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_encode_chunk, specs))

    tolerance = _CHUNK_LENGTH_TOLERANCE_SECONDS
    least = _MIN_TAIL_SECONDS

    def _is_short(result: dict) -> bool:
        # A chunk whose length could not be read is retried like a short one.
        if result["seconds"] is None:
            return True
        return result["seconds"] < specs[result["metadata"]["index"]].duration - tolerance

    # ── Sequential retry for failed and short chunks ─────────────
    retry_indices = [
        r["index"] if "error" in r else r["metadata"]["index"]
        for r in results
        if "error" in r or _is_short(r)
    ]
    if retry_indices:
        logger.warning(
            "%d/%d chunks failed or came out short in parallel pass, retrying sequentially",
            len(retry_indices),
            total_specs,
        )
        for index in retry_indices:
            retry = _encode_chunk(specs[index])
            if "file" in retry and not _is_short(retry):
                logger.info("Chunk %d recovered on retry", index + 1)
            results[index] = retry

    failed = [r for r in results if "error" in r]
    # A chunk whose length is still unknown may hold audio: a gap, not an empty tail.
    for r in results:
        if "file" in r and r["seconds"] is None:
            index = r["metadata"]["index"]
            Path(r["file"]).unlink(missing_ok=True)
            failed.append(
                {"error": f"the length of chunk {index + 1} could not be read", "index": index}
            )
    encoded = [r for r in results if "file" in r and r["seconds"] is not None]

    # The audio ends where the last chunk that holds audio ends. A file whose header
    # overstates its length gives chunks past that point, which are skipped; a chunk
    # that is short while audio continues past it is a gap.
    audio_ends = [
        specs[r["metadata"]["index"]].actual_start + r["seconds"]
        for r in encoded
        if r["seconds"] > least
    ]
    if not audio_ends and not failed:
        raise RuntimeError(
            f"None of the {total_specs} chunks holds any audio, so there is nothing to transcribe."
        )
    audio_end = max(audio_ends, default=0.0)

    successful: list[dict] = []
    covered_until = 0.0
    for r in encoded:
        spec = specs[r["metadata"]["index"]]
        needed_until = min(spec.actual_start + spec.duration, audio_end)
        chunk_end = spec.actual_start + r["seconds"]
        if max(chunk_end, covered_until) < needed_until - tolerance:
            failed.append(
                {
                    "error": (
                        f"chunk {spec.index + 1} holds {r['seconds']:.1f} s of "
                        f"{spec.duration:.1f} s, with audio after it"
                    ),
                    "index": spec.index,
                }
            )
        elif r["seconds"] <= least or chunk_end <= covered_until + least:
            # Nothing, or too little to send, that the chunks before it do not already
            # hold. _MIN_TAIL_SECONDS, not the tolerance: a recording that ends 0.8 s
            # past the previous chunk's end overlap has 0.8 s more to transcribe.
            logger.warning(
                "Chunk %d adds %.2f s past the chunks before it, at the end of the "
                "recording; skipping",
                spec.index + 1,
                max(0.0, min(r["seconds"], chunk_end - covered_until)),
            )
            Path(r["file"]).unlink(missing_ok=True)
            continue
        else:
            successful.append(r)
        covered_until = max(covered_until, chunk_end)
    for r in successful:
        r.pop("seconds")
    failed.sort(key=lambda r: r["index"])

    logger.info(
        "Chunk splitting complete: %d succeeded, %d failed",
        len(successful),
        len(failed),
    )

    if failed:
        missing = ", ".join(
            f"{_clock(spec.actual_start)}-{_clock(spec.actual_start + spec.duration)}"
            for spec in (specs[r["index"]] for r in failed)
        )
        detail = "; ".join(r["error"] for r in failed[:5])
        raise RuntimeError(
            f"{len(failed)} of {total_specs} chunks could not be created, so the "
            f"recording would be transcribed with gaps ({missing}). Errors: {detail}"
        )

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
