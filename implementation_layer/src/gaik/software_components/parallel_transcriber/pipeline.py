"""
Parallel transcription pipeline orchestrator.

Ported from QAdental's ``transcription.py``, ``transcription_gpt4o_diarize.py``,
and ``audio_pipeline.py``.  Provides a single entry point that handles:

1. Video → audio extraction (FFmpeg)
2. File-size / duration check → single-pass or chunked
3. Parallel FFmpeg splitting with overlap
4. Parallel API transcription (Whisper or GPT-4o Diarize)
5. SRT overlap-deduplication and merging
"""

from __future__ import annotations

import concurrent.futures
import difflib
import logging
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from gaik.software_components.endpoints import check_endpoint
from gaik.software_components.input_limits import InputLimitError, InputLimits
from gaik.software_components.llm.factory import assert_openai_or_azure
from gaik.software_components.llm.providers import resolve_provider

from .config import TranscriptionConfig
from .ffmpeg import (
    check_ffmpeg_available,
    extract_audio,
    get_audio_duration,
    has_audio_stream,
    has_video_stream,
    split_audio,
)
from .models import TranscriptionModel, TranscriptionResult
from .srt import combine_srt_chunks, extract_text_from_srt, seconds_to_time

logger = logging.getLogger(__name__)

# An SRT timestamp, "HH:MM:SS,mmm"; WebVTT writes the same with a dot.
_SRT_TIMESTAMP = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")

# GPT-4o Transcribe refuses any request whose audio is longer than 1400 s
# ("audio duration ... is longer than 1400 seconds which is the maximum for
# this model") — not the 25 min (1500 s) the limit is often quoted as.
_GPT4O_API_DURATION_LIMIT_SECONDS = 1400

# Single-pass ceiling, with margin: our duration probe and the API's own
# decoder need not agree to the last fraction of a second.
_MAX_GPT4O_DURATION_SECONDS = 1380

# Joining the text of two overlapping chunks from a model without timestamps: the end of
# one chunk's text and the start of the next one's are lined up over k words, for every
# k up to _MAX_WORDS_PER_SECOND words per second of shared audio (fast speech is about
# 3.5). They count as the same speech at a difflib ratio of _MIN_OVERLAP_RATIO or more
# with at least _MIN_REPEATED_WORDS words in common, or, for a short overlap, a ratio of
# _MIN_SHORT_OVERLAP_RATIO with _MIN_SHORT_OVERLAP_WORDS. Of k values whose ratios are
# within _OVERLAP_RATIO_SLACK of the best, the smallest is taken.
_MIN_REPEATED_WORDS = 4
_MIN_OVERLAP_RATIO = 0.75
_MIN_SHORT_OVERLAP_WORDS = 3
_MIN_SHORT_OVERLAP_RATIO = 0.85
_OVERLAP_RATIO_SLACK = 0.05
_MAX_WORDS_PER_SECOND = 4

# The path the SDK adds itself, at the end of an Azure endpoint's path.
_AZURE_OPENAI_SUFFIX = re.compile(r"/openai(?:/v1|/deployments(?:/.*)?)?$", re.IGNORECASE)
# Hosts whose bare /openai path is the SDK's: Azure, Azure Government, Azure China and
# Azure API Management.
_AZURE_HOST_SUFFIXES = (".azure.com", ".azure.us", ".azure.cn", ".azure-api.net")


def _azure_resource_endpoint(endpoint: str) -> str:
    """The address the SDK puts ``/openai/...`` after, from an Azure endpoint.

    A trailing ``/openai/v1`` or ``/openai/deployments/...`` is cut, a trailing bare
    ``/openai`` only on an Azure host (``*.azure.com``, ``.azure.us``, ``.azure.cn``,
    ``.azure-api.net``), with the query and a trailing
    slash: ``https://r.openai.azure.com/openai/v1`` gives ``https://r.openai.azure.com``.
    The rest of the path stays, so a gateway's ``https://gw.example.com/openai/prod``
    keeps its own path. The same cut as the Transcriber's, which this package cannot
    import (pydub).
    """
    parts = urlsplit(endpoint.strip())
    if not parts.scheme or not parts.netloc:
        return endpoint.strip().rstrip("/")
    path = parts.path.rstrip("/")
    suffix = _AZURE_OPENAI_SUFFIX.search(path)
    if suffix and (
        suffix.group(0).lower() != "/openai"
        or (parts.hostname or "").endswith(_AZURE_HOST_SUFFIXES)
    ):
        path = path[: suffix.start()]
    return f"{parts.scheme}://{parts.netloc}{path}"


def _named_like_gpt4o_transcribe(deployment: str) -> bool:
    """True for a name like ``gpt-4o-transcribe`` or ``gpt-4o-mini-transcribe``: one that
    contains ``gpt`` and not ``whisper``. Such a model takes ``json`` or ``text`` only,
    without the ``srt`` and its timestamps that Whisper gives."""
    name = deployment.lower()
    return "gpt" in name and "whisper" not in name


def _srt_cue_text(text: str) -> str:
    # A blank line ends an SRT cue, so a cue's text has none.
    return re.sub(r"\n\s*\n", "\n", text.strip())


def _text_as_srt(text: str, seconds: float) -> str:
    """One cue from 0 to ``seconds`` holding ``text``; empty for no text."""
    text = _srt_cue_text(text)
    if not text:
        return ""
    return f"1\n{seconds_to_time(0.0)} --> {seconds_to_time(seconds)}\n{text}\n"


def _word_key(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def _drop_repeated_words(
    previous: list[str], following: list[str], shared_seconds: float
) -> tuple[list[str], list[str]]:
    """Keep the words two overlapping chunks both give for their shared audio once.

    For each k from the overlap's word window down to ``_MIN_SHORT_OVERLAP_WORDS``, the
    last k words of ``previous`` are compared with the first k of ``following``,
    case-folded and without punctuation, by difflib's ratio, so a word heard differently
    in one chunk ("2023" and "2024") does not split the overlap. A k counts when its
    ratio is at least ``_MIN_OVERLAP_RATIO`` with ``_MIN_REPEATED_WORDS`` words in common,
    or ``_MIN_SHORT_OVERLAP_RATIO`` with ``_MIN_SHORT_OVERLAP_WORDS``; of the k values
    within ``_OVERLAP_RATIO_SLACK`` of the best, the smallest is taken. ``previous`` is
    cut where its first matching block starts, moved back over words just before it that
    ``following`` also has just before its block, so a word of ``previous`` that the
    lined-up stretch does not hold stays; ``following`` is kept whole, so the following
    chunk's version of the shared speech stands. Without such a k both are kept whole: a
    phrase said again away from where the chunks meet does not line them up.
    """
    window = min(
        len(previous),
        len(following),
        max(_MIN_SHORT_OVERLAP_WORDS, math.ceil(shared_seconds * _MAX_WORDS_PER_SECOND)),
    )
    # A word that is only punctuation has no key; it never matches.
    tail_keys = [_word_key(word) or f"\0a{i}" for i, word in enumerate(previous[-window:])]
    head_keys = [_word_key(word) or f"\0b{i}" for i, word in enumerate(following[:window])]
    candidates: list[tuple[int, float, int, int]] = []  # k, ratio, first block's a and b
    for words in range(window, _MIN_SHORT_OVERLAP_WORDS - 1, -1):
        matcher = difflib.SequenceMatcher(
            None, tail_keys[len(tail_keys) - words :], head_keys[:words], autojunk=False
        )
        if matcher.real_quick_ratio() < _MIN_OVERLAP_RATIO:
            continue
        ratio = matcher.ratio()
        blocks = matcher.get_matching_blocks()
        in_common = sum(block.size for block in blocks)
        if (ratio >= _MIN_OVERLAP_RATIO and in_common >= _MIN_REPEATED_WORDS) or (
            ratio >= _MIN_SHORT_OVERLAP_RATIO and in_common >= _MIN_SHORT_OVERLAP_WORDS
        ):
            candidates.append((words, ratio, blocks[0].a, blocks[0].b))
    if not candidates:
        return previous, following
    best_ratio = max(ratio for _, ratio, _, _ in candidates)
    words, _, first_a, first_b = min(
        c for c in candidates if c[1] >= best_ratio - _OVERLAP_RATIO_SLACK
    )
    cut = len(previous) - words + first_a
    # Words of following before its first matching block may be in previous just before it.
    keys = [_word_key(word) for word in following[:first_b]]
    while cut > 0 and first_b > 0 and _word_key(previous[cut - 1]) == keys[first_b - 1]:
        cut, first_b = cut - 1, first_b - 1
    return previous[:cut], following


def _text_chunks_as_srt(
    texts: list[str], chunk_metadata: list[dict] | None, last_chunk_seconds: float
) -> str:
    """Join the transcripts of overlapping chunks from a model without timestamps.

    Each chunk becomes one cue over its own stretch of the recording (from its
    nominal start to the next chunk's), and the words two chunks both give for
    their overlap are kept once (:func:`_drop_repeated_words`).
    """
    if not chunk_metadata or len(chunk_metadata) != len(texts):
        return _text_as_srt("\n".join(texts), last_chunk_seconds)
    words = [text.split() for text in texts]
    for i in range(1, len(words)):
        shared = chunk_metadata[i - 1].get("overlap_end", 0) + chunk_metadata[i].get(
            "overlap_start", 0
        )
        if shared > 0:
            words[i - 1], words[i] = _drop_repeated_words(words[i - 1], words[i], shared)
    cues: list[str] = []
    for i, chunk_words in enumerate(words):
        text = _srt_cue_text(" ".join(chunk_words))
        if not text:
            continue
        start = chunk_metadata[i]["nominal_start"]
        if i + 1 < len(words):
            end = chunk_metadata[i + 1]["nominal_start"]
        else:
            end = max(start, chunk_metadata[i]["actual_start"] + last_chunk_seconds)
        cues.append(
            f"{len(cues) + 1}\n{seconds_to_time(start)} --> {seconds_to_time(end)}\n{text}\n"
        )
    return "\n".join(cues)


class _Skipped:
    """What a chunk job returns when an earlier one failed and the run is ending."""


def _run_chunk_jobs(
    job: Callable[[tuple[int, str]], tuple[int, str]],
    chunk_files: list[str],
    max_workers: int,
) -> list[str | None]:
    """Run ``job`` over the indexed chunk files in a thread pool; results by index.

    The first job that raises ends the run: the chunks not yet started are not
    sent (each would be a paid request whose result is thrown away), the ones
    already running finish, and the error is raised.
    """
    stop = threading.Event()

    def guarded(item: tuple[int, str]):
        if stop.is_set():
            return _Skipped
        try:
            return job(item)
        except BaseException:
            stop.set()
            raise

    results: list[str | None] = [None] * len(chunk_files)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = [executor.submit(guarded, item) for item in enumerate(chunk_files)]
        for future in concurrent.futures.as_completed(futures):
            outcome = future.result()
            if outcome is _Skipped:
                continue
            index, value = outcome
            results[index] = value
    except BaseException:
        stop.set()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    executor.shutdown(wait=True)
    return results


class ParallelTranscriber:
    """High-level orchestrator for parallel audio/video transcription.

    Args:
        api_config: Dict from :func:`get_openai_config` with keys like
            ``use_azure``, ``api_key``, ``azure_endpoint``, ``api_version``,
            ``transcription_model``, etc.
        config: Optional :class:`TranscriptionConfig`.  Defaults are used
            when omitted.
        limits: Duration and size limits (``max_media_seconds``, default 6 hours;
            ``max_media_bytes``, off by default). A file over one is refused with
            :class:`~gaik.software_components.input_limits.InputLimitError` before
            audio is extracted or any transcription call is made; one whose
            duration cannot be read at all is refused before the first call.

    Example::

        from gaik.software_components.config import get_openai_config
        from gaik.software_components.parallel_transcriber import (
            ParallelTranscriber, TranscriptionConfig,
        )

        api_cfg = get_openai_config(use_azure=True)
        transcriber = ParallelTranscriber(api_cfg)
        result = transcriber.transcribe("interview.mp4")
        result.save("output/")
    """

    def __init__(
        self,
        api_config: dict,
        config: TranscriptionConfig | None = None,
        *,
        limits: InputLimits | None = None,
    ) -> None:
        cfg = config or TranscriptionConfig()
        if cfg.whisper_request_format not in (None, "srt", "json"):
            raise ValueError(
                f"whisper_request_format={cfg.whisper_request_format!r}: use 'srt', 'json' or None."
            )
        provider: str | None = None
        # Whisper Local has its own on-prem auth (api_base + key) — skip the
        # OpenAI/Azure provider check that the cloud-only models require.
        if cfg.model == TranscriptionModel.WHISPER_LOCAL:
            if not api_config.get("api_base"):
                raise ValueError(
                    "WHISPER_LOCAL requires api_config['api_base'] "
                    "(e.g. 'https://whisper.example.com:8080')"
                )
            check_endpoint(
                api_config["api_base"],
                provider="whisper_local",
                allowed_hosts=api_config.get("allowed_endpoint_hosts"),
                what="api_base",
            )
        else:
            # Resolve like create_openai_client: a bare legacy config (neither
            # ``provider`` nor ``use_azure``) means standard OpenAI, whatever LLM_PROVIDER says.
            provider = resolve_provider(config={"use_azure": False, **api_config})
            assert_openai_or_azure({"provider": provider}, component="ParallelTranscriber")
            # The GPT-4o diarize path posts the audio and key to this endpoint directly.
            # Whisper goes through create_openai_client, which checks its own address.
            endpoint = api_config.get("azure_audio_endpoint") or api_config.get("azure_endpoint")
            if endpoint and cfg.model == TranscriptionModel.GPT4O_DIARIZE:
                check_endpoint(
                    endpoint,
                    provider="azure",
                    allowed_hosts=api_config.get("allowed_endpoint_hosts"),
                    what="azure_audio_endpoint",
                )
        self._api_config = dict(api_config)
        self._provider = provider
        self._config = cfg
        self._limits = limits or InputLimits()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def check_ffmpeg() -> bool:
        """Return True if FFmpeg and ffprobe are available."""
        return check_ffmpeg_available()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def transcribe(
        self,
        file_path: str | Path,
        check_cancelled: Callable[[], None] | None = None,
        progress_callback: Callable[[str, int, int, str], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio or video file.

        Args:
            file_path: Path to audio/video file.
            check_cancelled: Callable that raises an exception (typically
                :class:`TranscriptionCancelled`) when the caller wants to
                abort.  Checked at every pipeline stage.
            progress_callback: ``(stage, current, total, message)`` callback.
                Stages: ``"extracting"``, ``"splitting"``, ``"transcribing"``,
                ``"merging"``, ``"complete"``.

        Returns:
            :class:`TranscriptionResult` with the transcribed content.

        Raises:
            InputLimitError: If the file is over ``max_media_bytes`` or
                ``max_media_seconds``, or its length cannot be read (a file that is
                not audio or video) while ``max_media_seconds`` is set.
            ValueError: If the length is needed (GPT-4o Diarize, Whisper Local, a
                recording to split) and cannot be read while ``max_media_seconds``
                is off.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        # Size and length first: a long recording becomes many paid calls.
        probed_seconds = self._limits.check_media(file_path)

        cfg = self._config
        model = cfg.model
        audio_path: Path | None = None
        temp_dir: Path | None = None  # holds the extracted audio; removed at the end

        # Fail fast if the file is a video without an audio stream
        if has_video_stream(file_path) and not has_audio_stream(file_path):
            raise ValueError(f"File contains video but no audio stream: {file_path}")

        try:
            # ── Stage 1: video → audio extraction ──────────────────────
            if has_video_stream(file_path) and has_audio_stream(file_path):
                if check_cancelled:
                    check_cancelled()
                if progress_callback:
                    progress_callback("extracting", 0, 1, "Extracting audio from video …")

                temp_dir = Path(tempfile.mkdtemp(prefix="parallel_transcriber_"))
                audio_path = temp_dir / f"{file_path.stem}.mp3"
                extract_audio(file_path, audio_path, config=cfg)

                if progress_callback:
                    progress_callback("extracting", 1, 1, "Audio extracted")
            else:
                audio_path = file_path

            # ── Stage 2: file-size check → single-pass? ───────────────
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)

            # For GPT-4o, we also need to check duration against 25-min limit
            needs_chunking = file_size_mb > cfg.max_single_file_mb
            total_duration: float | None = None

            # These backends need the length before the first call: a file that is not
            # audio or video is refused here (_measured_seconds), not with ffprobe's error.
            # A GPT-4o model on the Whisper backend has the same 1400 s per-request limit.
            gpt4o_on_whisper = model == TranscriptionModel.WHISPER and self._asks_for_json(
                self._get_whisper_deployment()
            )
            if model == TranscriptionModel.GPT4O_DIARIZE or gpt4o_on_whisper:
                total_duration = self._measured_seconds(audio_path, file_path.name)
                if total_duration > _MAX_GPT4O_DURATION_SECONDS:
                    needs_chunking = True

            # For Whisper Local, an on-prem GPU-VM POST gets a single audio
            # blob and must finish within whisper_local_request_timeout_seconds
            # (default 30 min). Anything longer than the configured chunk
            # length must be chunked, and anything past max_audio_minutes is
            # rejected so callers fall back to the cloud path immediately.
            if model == TranscriptionModel.WHISPER_LOCAL:
                total_duration = self._measured_seconds(audio_path, file_path.name)
                duration_minutes = total_duration / 60
                if duration_minutes > cfg.whisper_local_max_audio_minutes:
                    raise ValueError(
                        f"Audio too long for whisper_local "
                        f"({duration_minutes:.1f} min > "
                        f"{cfg.whisper_local_max_audio_minutes:.0f} min)"
                    )
                if duration_minutes > cfg.whisper_local_chunk_duration_minutes:
                    needs_chunking = True

            if (
                total_duration is None
                and probed_seconds is None
                and self._limits.max_media_seconds is not None
            ):
                # The first probe could not read the length: measure the audio
                # that is about to be sent, so a single pass is checked as well.
                total_duration = self._measured_seconds(audio_path, file_path.name)
            if total_duration is not None:
                self._limits.check_media_seconds(total_duration, file_path.name)

            if not needs_chunking:
                # Single-pass transcription
                logger.info("File %.1f MB within limits, single-pass transcription", file_size_mb)
                result = self._transcribe_single(
                    audio_path, model, check_cancelled, progress_callback
                )
                return result

            # ── Stage 3: measure duration ──────────────────────────────
            if total_duration is None:
                total_duration = self._measured_seconds(audio_path, file_path.name)
                self._limits.check_media_seconds(total_duration, file_path.name)
            logger.info("Total duration: %.1f min", total_duration / 60)

            if check_cancelled:
                check_cancelled()

            # ── Stage 4: choose model-specific chunk parameters ────────
            if model == TranscriptionModel.GPT4O_DIARIZE:
                # A middle chunk is padded with the overlap on *both* sides, so
                # the audio the API actually receives is chunk + 2 × overlap.
                # That sum is what has to clear the 1400 s limit.
                budget_seconds = _GPT4O_API_DURATION_LIMIT_SECONDS - 2 * cfg.chunk_overlap_seconds
                chunk_minutes = max(
                    1, min(cfg.gpt4o_chunk_duration_minutes, int(budget_seconds // 60))
                )
                parallelism = cfg.gpt4o_chunk_parallelism
                force_duration = True
            elif model == TranscriptionModel.WHISPER_LOCAL:
                chunk_minutes = cfg.whisper_local_chunk_duration_minutes
                parallelism = cfg.whisper_local_chunk_parallelism
                force_duration = True
            else:
                chunk_minutes = cfg.chunk_duration_minutes
                if gpt4o_on_whisper:
                    # The same 1400 s ceiling per request as GPT-4o Diarize, overlap included.
                    budget_seconds = (
                        _GPT4O_API_DURATION_LIMIT_SECONDS - 2 * cfg.chunk_overlap_seconds
                    )
                    chunk_minutes = max(1, min(chunk_minutes, int(budget_seconds // 60)))
                parallelism = cfg.transcription_workers
                # only True when duration forced it
                force_duration = file_size_mb <= cfg.max_single_file_mb

            # ── Stage 5–6: compute specs + parallel FFmpeg split ───────
            if progress_callback:
                progress_callback("splitting", 0, 1, "Splitting audio into chunks …")

            chunk_files, chunk_metadata = split_audio(
                audio_path,
                config=cfg,
                check_cancelled=check_cancelled,
                total_duration=total_duration,
                chunk_duration_minutes=chunk_minutes,
                force_by_duration=force_duration or needs_chunking,
            )

            if progress_callback:
                progress_callback("splitting", 1, 1, f"Created {len(chunk_files)} chunks")

            if check_cancelled:
                check_cancelled()

            # ── Stage 7: parallel transcription ────────────────────────
            try:
                if model == TranscriptionModel.GPT4O_DIARIZE:
                    combined = self._transcribe_chunks_gpt4o(
                        chunk_files,
                        chunk_metadata,
                        parallelism,
                        check_cancelled,
                        progress_callback,
                    )
                elif model == TranscriptionModel.WHISPER_LOCAL:
                    combined = self._transcribe_chunks_whisper_local(
                        chunk_files,
                        chunk_metadata,
                        parallelism,
                        check_cancelled,
                        progress_callback,
                    )
                else:
                    combined = self._transcribe_chunks_whisper(
                        chunk_files,
                        chunk_metadata,
                        parallelism,
                        check_cancelled,
                        progress_callback,
                    )
            finally:
                self._cleanup_chunks(chunk_files, audio_path)

            # ── Stage 8: format conversion ─────────────────────────────
            content = self._convert_format(combined, cfg.response_format)

            if progress_callback:
                progress_callback("complete", 1, 1, "Transcription complete")

            return TranscriptionResult(
                content=content,
                format=cfg.response_format,
                language=cfg.language or "auto",
                model_used=str(model),
                total_chunks=len(chunk_files),
                total_duration_seconds=total_duration,
            )

        finally:
            # Remove the extracted audio's temp dir, also when the extraction failed
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Single-pass transcription
    # ------------------------------------------------------------------

    def _measured_seconds(self, audio_path: Path, name: str) -> float:
        """The length of ``audio_path``, decoded when its header has none.

        Raises:
            InputLimitError: If neither ffprobe nor decoding can read it while
                ``max_media_seconds`` is set (a file that is not audio or video).
            ValueError: The same with ``max_media_seconds`` off.
        """
        try:
            return get_audio_duration(str(audio_path))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            if shutil.which("ffprobe") is None:
                reason = "ffprobe is not installed"
            elif isinstance(exc, subprocess.TimeoutExpired):
                reason = "reading its length timed out"
            else:
                reason = "ffprobe and ffmpeg cannot read it as audio or video"
            if self._limits.max_media_seconds is None:
                raise ValueError(
                    f"The length of {name} cannot be read ({reason}), so it was not transcribed."
                ) from exc
            raise InputLimitError(
                f"The length of {name} cannot be read ({reason}), so it cannot be checked "
                "against InputLimits.max_media_seconds.",
                limit="max_media_seconds",
                actual=float("inf"),
                maximum=self._limits.max_media_seconds,
            ) from exc

    def _transcribe_single(
        self,
        audio_path: Path,
        model: TranscriptionModel,
        check_cancelled: Callable[[], None] | None,
        progress_callback: Callable[[str, int, int, str], None] | None,
    ) -> TranscriptionResult:
        """Transcribe a single (small) file without chunking."""
        cfg = self._config
        if check_cancelled:
            check_cancelled()
        if progress_callback:
            progress_callback("transcribing", 0, 1, "Transcribing …")

        if model == TranscriptionModel.GPT4O_DIARIZE:
            content = self._call_gpt4o_single(audio_path)
        elif model == TranscriptionModel.WHISPER_LOCAL:
            content = self._call_whisper_local_single(audio_path)
        else:
            content = self._call_whisper_single(audio_path)

        if check_cancelled:
            check_cancelled()

        content = self._convert_format(content, cfg.response_format)

        if progress_callback:
            progress_callback("complete", 1, 1, "Transcription complete")

        duration = 0.0
        try:
            duration = get_audio_duration(str(audio_path))
        except Exception:
            pass

        return TranscriptionResult(
            content=content,
            format=cfg.response_format,
            language=cfg.language or "auto",
            model_used=str(model),
            total_chunks=1,
            total_duration_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Whisper API
    # ------------------------------------------------------------------

    def _whisper_client_config(self) -> dict:
        """The client config for the Whisper backend, built as the Transcriber builds it.

        The provider is resolved as in the constructor (``provider: "azure"`` works
        without the legacy ``use_azure`` flag). On Azure the audio goes to
        ``azure_audio_endpoint``, else ``azure_endpoint``, else ``base_url``, in the
        Transcriber's order, cut to the resource address (:func:`_azure_resource_endpoint`)
        and passed as ``azure_endpoint``, so the endpoint check sees that address. The
        SDK then requests ``/openai/deployments/<model>/audio/...``; a ``/openai/v1``
        ``base_url`` kept as it is would have given ``/openai/v1/deployments/...``,
        which Azure does not serve.
        """
        provider = self._provider or resolve_provider(
            config={"use_azure": False, **self._api_config}
        )
        config = {**self._api_config, "provider": provider, "use_azure": provider == "azure"}
        if provider == "azure":
            endpoint = (
                config.get("azure_audio_endpoint")
                or config.get("azure_endpoint")
                or config.get("base_url")
            )
            if endpoint:
                config["azure_endpoint"] = _azure_resource_endpoint(endpoint)
                config.pop("base_url", None)
            if not config.get("api_version"):
                config["api_version"] = "2024-12-01-preview"
        return config

    def _make_whisper_client(self):
        """Create a new OpenAI client for Whisper (thread-safe: one per thread)."""
        from gaik.software_components.config import create_openai_client

        return create_openai_client(self._whisper_client_config())

    def _get_whisper_deployment(self) -> str:
        # As Transcriber: a key left out, None or "" (a config built from an unset
        # variable) is Whisper. On Azure that is the conventional deployment name
        # "whisper"; on OpenAI the model id is "whisper-1" ("whisper" is a 404).
        configured = self._api_config.get("transcription_model")
        if configured:
            return configured
        return "whisper" if self._whisper_client_config()["provider"] == "azure" else "whisper-1"

    def _asks_for_json(self, deployment: str) -> bool:
        """Whether the Whisper backend asks ``deployment`` for ``json`` rather than SRT:
        ``TranscriptionConfig.whisper_request_format`` when set, else by the name
        (:func:`_named_like_gpt4o_transcribe`)."""
        chosen = self._config.whisper_request_format
        if chosen is not None:
            return chosen == "json"
        return _named_like_gpt4o_transcribe(deployment)

    def _whisper_request(self, deployment: str, file) -> dict:
        """The keyword arguments of one Whisper-backend transcription request.

        Whisper is asked for SRT, which the merge and every output format are built
        from. A GPT-4o model takes ``json`` or ``text`` only, so it is asked for
        ``json`` and its text is made into SRT afterwards.
        """
        cfg = self._config
        kwargs: dict = {
            "model": deployment,
            "file": file,
            "response_format": "json" if self._asks_for_json(deployment) else "srt",
        }
        if cfg.language and cfg.language != "auto":
            kwargs["language"] = cfg.language
        if cfg.prompt:
            kwargs["prompt"] = cfg.prompt
        return kwargs

    def _whisper_answer(self, response, deployment: str) -> str:
        """SRT for Whisper; the transcript's text for a model asked for ``json``."""
        if self._asks_for_json(deployment):
            return response.text or ""
        return str(response)

    def _call_whisper_single(self, audio_path: Path) -> str:
        """Transcribe a single file with Whisper; returns SRT."""
        from ._retry import with_retry

        cfg = self._config
        client = self._make_whisper_client()
        deployment = self._get_whisper_deployment()

        def _do():
            with open(audio_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    **self._whisper_request(deployment, f)
                )
            return self._whisper_answer(response, deployment)

        answer = with_retry(
            _do,
            max_retries=cfg.max_retries,
            base_delay=cfg.retry_base_delay_seconds,
            max_429_retries=cfg.max_429_retries,
        )
        if self._asks_for_json(deployment):
            return _text_as_srt(answer, self._seconds_or_zero(audio_path))
        return answer

    @staticmethod
    def _seconds_or_zero(audio_path: str | Path) -> float:
        try:
            return get_audio_duration(str(audio_path))
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0.0

    def _transcribe_chunks_whisper(
        self,
        chunk_files: list[str],
        chunk_metadata: list[dict] | None,
        parallelism: int,
        check_cancelled: Callable[[], None] | None,
        progress_callback: Callable[[str, int, int, str], None] | None,
    ) -> str:
        """Transcribe multiple chunks in parallel with Whisper, return combined SRT."""
        from ._retry import with_retry

        cfg = self._config
        total = len(chunk_files)
        completed = 0
        lock = threading.Lock()
        deployment = self._get_whisper_deployment()

        def _transcribe_one(idx_and_path: tuple[int, str]) -> tuple[int, str]:
            nonlocal completed
            idx, path = idx_and_path

            if check_cancelled:
                check_cancelled()

            # Thread-local client
            client = self._make_whisper_client()

            def _do():
                with open(path, "rb") as f:
                    response = client.audio.transcriptions.create(
                        **self._whisper_request(deployment, f)
                    )
                return self._whisper_answer(response, deployment)

            result = with_retry(
                _do,
                max_retries=cfg.max_retries,
                base_delay=cfg.retry_base_delay_seconds,
                max_429_retries=cfg.max_429_retries,
            )

            if check_cancelled:
                check_cancelled()

            with lock:
                completed += 1
                current = completed

            if progress_callback:
                msg = f"Transcribed chunk {current}/{total}"
                progress_callback("transcribing", current, total, msg)

            logger.info("Chunk %d/%d transcribed", idx + 1, total)
            return idx, result

        max_workers = min(parallelism, total)

        logger.info("Transcribing %d chunks (parallel=%d, model=whisper)", total, max_workers)

        results = _run_chunk_jobs(_transcribe_one, chunk_files, max_workers)
        ordered = [t for t in results if t is not None]

        if progress_callback:
            progress_callback("merging", 0, 1, "Merging transcriptions …")

        if self._asks_for_json(deployment):
            combined = _text_chunks_as_srt(
                ordered, chunk_metadata, self._seconds_or_zero(chunk_files[-1])
            )
        else:
            combined = combine_srt_chunks(ordered, chunk_metadata)

        if progress_callback:
            progress_callback("merging", 1, 1, "Merge complete")

        return combined

    # ------------------------------------------------------------------
    # GPT-4o Diarize API
    # ------------------------------------------------------------------

    def _call_gpt4o_single(self, audio_path: Path) -> str:
        """Transcribe a single file with GPT-4o Diarize, return SRT."""
        resp_json = self._call_gpt4o_api(str(audio_path))
        segments = self._extract_segments(resp_json)
        return self._segments_to_srt(segments)

    def _call_gpt4o_api(self, audio_file_path: str) -> dict:
        """Send audio to GPT-4o Diarize API with retry logic."""
        import httpx

        cfg = self._config
        api_cfg = self._api_config

        api_key = api_cfg.get("api_key", "")
        endpoint = api_cfg.get("azure_audio_endpoint") or api_cfg.get("azure_endpoint", "")
        api_version = api_cfg.get("api_version", "2025-03-01-preview")
        deployment = api_cfg.get("gpt4o_diarize_deployment", "gpt-4o-transcribe")

        if not api_key or not endpoint:
            raise ValueError("Azure credentials not configured for GPT-4o Diarize")

        # The deployment path goes after the resource address, so an endpoint given
        # with its /openai/v1 path does not get that path twice.
        url = (
            f"{_azure_resource_endpoint(endpoint)}/openai/deployments/{deployment}"
            f"/audio/transcriptions?api-version={api_version}"
        )

        total_max_attempts = cfg.max_retries + 1 + cfg.max_429_retries
        rate_limit_retries = 0
        response = None
        file_name = Path(audio_file_path).name

        for attempt in range(total_max_attempts):
            if not Path(audio_file_path).exists():
                raise FileNotFoundError(f"Audio file no longer exists: {audio_file_path}")

            with open(audio_file_path, "rb") as f:
                files = {"file": (file_name, f, "audio/mpeg")}
                data: dict = {
                    "model": deployment,
                    "response_format": "diarized_json",
                    "chunking_strategy": "auto",
                }
                if cfg.language and cfg.language != "auto":
                    data["language"] = cfg.language

                try:
                    response = httpx.post(
                        url,
                        headers={"api-key": api_key},
                        files=files,
                        data=data,
                        timeout=float(cfg.api_timeout_seconds),
                    )
                except httpx.TimeoutException:
                    if attempt < cfg.max_retries:
                        logger.warning("GPT-4o API timeout, retrying …")
                        time.sleep(cfg.retry_base_delay_seconds)
                        continue
                    raise RuntimeError("GPT-4o transcription timed out")

            if response.status_code == 200:
                break

            if response.status_code == 429 and rate_limit_retries < cfg.max_429_retries:
                retry_after = response.headers.get("retry-after")
                delay = (
                    float(retry_after)
                    if retry_after
                    else cfg.retry_base_delay_seconds * 1.5 * (2**rate_limit_retries)
                )
                rate_limit_retries += 1
                logger.warning(
                    "Rate limited (429), retry %d/%d in %.1fs",
                    rate_limit_retries,
                    cfg.max_429_retries,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code >= 500 and attempt < cfg.max_retries:
                logger.warning("Server error %d, retrying …", response.status_code)
                time.sleep(cfg.retry_base_delay_seconds)
                continue

            logger.error("GPT-4o API error %d: %s", response.status_code, response.text[:200])
            if response.status_code == 429:
                raise RuntimeError(f"Rate limited after {rate_limit_retries} retries")
            raise RuntimeError(f"GPT-4o transcription failed (HTTP {response.status_code})")

        return response.json()  # type: ignore[union-attr]

    @staticmethod
    def _extract_segments(resp_json: dict) -> list[dict]:
        return [
            {
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", ""),
            }
            for seg in resp_json.get("segments", [])
        ]

    @staticmethod
    def _segments_to_srt(segments: list[dict], include_speaker: bool = False) -> str:
        lines: list[str] = []
        for i, seg in enumerate(segments, 1):
            start = seconds_to_time(seg["start"])
            end = seconds_to_time(seg["end"])
            text = seg["text"].strip()
            if include_speaker and seg.get("speaker"):
                text = f"[{seg['speaker']}] {text}"
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _transcribe_chunks_gpt4o(
        self,
        chunk_files: list[str],
        chunk_metadata: list[dict] | None,
        parallelism: int,
        check_cancelled: Callable[[], None] | None,
        progress_callback: Callable[[str, int, int, str], None] | None,
    ) -> str:
        """Transcribe multiple chunks in parallel with GPT-4o, return combined SRT."""
        total = len(chunk_files)
        completed = 0
        lock = threading.Lock()

        def _transcribe_one(idx_and_path: tuple[int, str]) -> tuple[int, str]:
            nonlocal completed
            idx, path = idx_and_path

            if check_cancelled:
                check_cancelled()

            resp_json = self._call_gpt4o_api(path)
            segments = self._extract_segments(resp_json)
            srt = self._segments_to_srt(segments)

            with lock:
                completed += 1
                current = completed

            if progress_callback:
                msg = f"Transcribed chunk {current}/{total} (GPT-4o)"
                progress_callback("transcribing", current, total, msg)

            logger.info("Chunk %d/%d transcribed (GPT-4o)", idx + 1, total)
            return idx, srt

        max_workers = min(parallelism, total)

        logger.info("Transcribing %d chunks (parallel=%d, model=gpt-4o)", total, max_workers)

        results = _run_chunk_jobs(_transcribe_one, chunk_files, max_workers)
        ordered = [r for r in results if r is not None]

        if progress_callback:
            progress_callback("merging", 0, 1, "Merging transcriptions …")

        combined = combine_srt_chunks(ordered, chunk_metadata)

        if progress_callback:
            progress_callback("merging", 1, 1, "Merge complete")

        return combined

    # ------------------------------------------------------------------
    # Whisper Local (on-prem) API
    # ------------------------------------------------------------------

    def _call_whisper_local_api(self, audio_file_path: str) -> dict:
        """Send a single audio chunk to the on-prem Whisper server.

        Uses ``requests.post`` against ``api_base/transcribe`` with the same
        payload shape as the standalone ``transcriber.whisper_local.transcribe``
        helper, but with a configurable timeout so chunked callers can override
        the 30-minute default per request.
        """
        import requests

        api_cfg = self._api_config
        cfg = self._config

        api_base = api_cfg.get("api_base", "")
        key = api_cfg.get("key", "") or api_cfg.get("api_key", "")
        if not api_base:
            raise ValueError("Whisper Local api_base not configured")

        file_name = Path(audio_file_path).name
        with open(audio_file_path, "rb") as f:
            payload = {
                "language": cfg.language or "auto",
                "diarization": False,
                "include_words": True,
            }
            if cfg.prompt:
                payload["initial_prompt"] = cfg.prompt
            files = {"file": (file_name, f)}
            response = requests.post(
                f"{api_base.rstrip('/')}/transcribe",
                data=payload,
                files=files,
                headers={"key": key} if key else {},
                timeout=cfg.whisper_local_request_timeout_seconds,
            )
            response.raise_for_status()
        return response.json()

    @staticmethod
    def _whisper_local_segments_to_srt(segments: list[dict]) -> str:
        """Convert Whisper Local response segments to SRT content."""
        lines: list[str] = []
        for i, seg in enumerate(segments, 1):
            start = seconds_to_time(float(seg.get("start", 0.0)))
            end = seconds_to_time(float(seg.get("end", 0.0)))
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _call_whisper_local_single(self, audio_path: Path) -> str:
        """Transcribe a single (small) file with Whisper Local, return SRT."""
        result = self._call_whisper_local_api(str(audio_path))
        segments = result.get("segments", []) or []
        if segments:
            return self._whisper_local_segments_to_srt(segments)
        # No segments — fall back to single-block SRT spanning the whole audio
        text = (result.get("text") or "").strip()
        if not text:
            return ""
        try:
            duration = get_audio_duration(str(audio_path))
        except Exception:
            duration = 0.0
        return f"1\n{seconds_to_time(0.0)} --> {seconds_to_time(duration)}\n{text}\n"

    def _transcribe_chunks_whisper_local(
        self,
        chunk_files: list[str],
        chunk_metadata: list[dict] | None,
        parallelism: int,
        check_cancelled: Callable[[], None] | None,
        progress_callback: Callable[[str, int, int, str], None] | None,
    ) -> str:
        """Transcribe multiple chunks in parallel against the on-prem server."""
        total = len(chunk_files)
        completed = 0
        lock = threading.Lock()

        def _transcribe_one(idx_and_path: tuple[int, str]) -> tuple[int, str]:
            nonlocal completed
            idx, path = idx_and_path

            if check_cancelled:
                check_cancelled()

            result = self._call_whisper_local_api(path)
            segments = result.get("segments", []) or []
            srt = self._whisper_local_segments_to_srt(segments)

            if check_cancelled:
                check_cancelled()

            with lock:
                completed += 1
                current = completed

            if progress_callback:
                msg = f"Transcribed chunk {current}/{total} (whisper_local)"
                progress_callback("transcribing", current, total, msg)

            logger.info("Chunk %d/%d transcribed (whisper_local)", idx + 1, total)
            return idx, srt

        max_workers = min(parallelism, total)

        logger.info("Transcribing %d chunks (parallel=%d, model=whisper_local)", total, max_workers)

        results = _run_chunk_jobs(_transcribe_one, chunk_files, max_workers)
        ordered = [r for r in results if r is not None]

        if progress_callback:
            progress_callback("merging", 0, 1, "Merging transcriptions …")

        combined = combine_srt_chunks(ordered, chunk_metadata)

        if progress_callback:
            progress_callback("merging", 1, 1, "Merge complete")

        return combined

    # ------------------------------------------------------------------
    # Format conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_format(
        srt_content: str,
        fmt: Literal["text", "srt", "vtt", "json", "verbose_json"],
    ) -> str:
        if fmt == "srt":
            return srt_content
        if fmt == "text":
            return extract_text_from_srt(srt_content)
        if fmt == "vtt":
            # Only the timestamps change their separator; the text keeps its commas.
            return "WEBVTT\n\n" + _SRT_TIMESTAMP.sub(r"\1.\2", srt_content)
        # json / verbose_json — return SRT as-is (no structured data available)
        return srt_content

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _cleanup_chunks(chunk_files: list[str], source_path: Path) -> None:
        """Remove temporary chunk files and their parent directory."""
        if not chunk_files:
            return
        chunk_dir = Path(chunk_files[0]).parent
        # Don't delete the source directory
        if chunk_dir == source_path.parent:
            for f in chunk_files:
                Path(f).unlink(missing_ok=True)
        else:
            shutil.rmtree(chunk_dir, ignore_errors=True)
