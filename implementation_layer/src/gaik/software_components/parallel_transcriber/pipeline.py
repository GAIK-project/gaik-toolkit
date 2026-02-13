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
import logging
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

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

# GPT-4o Transcribe has a 25-minute (1500 s) per-request limit
_MAX_GPT4O_DURATION_SECONDS = 1500


class ParallelTranscriber:
    """High-level orchestrator for parallel audio/video transcription.

    Args:
        api_config: Dict from :func:`get_openai_config` with keys like
            ``use_azure``, ``api_key``, ``azure_endpoint``, ``api_version``,
            ``transcription_model``, etc.
        config: Optional :class:`TranscriptionConfig`.  Defaults are used
            when omitted.

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
    ) -> None:
        self._api_config = dict(api_config)
        self._config = config or TranscriptionConfig()

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
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        cfg = self._config
        model = cfg.model
        audio_path: Path | None = None
        temp_audio: Path | None = None  # track extracted audio for cleanup

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
                temp_audio = extract_audio(file_path, audio_path, config=cfg)

                if progress_callback:
                    progress_callback("extracting", 1, 1, "Audio extracted")
            else:
                audio_path = file_path

            # ── Stage 2: file-size check → single-pass? ───────────────
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)

            # For GPT-4o, we also need to check duration against 25-min limit
            needs_chunking = file_size_mb > cfg.max_single_file_mb
            total_duration: float | None = None

            if model == TranscriptionModel.GPT4O_DIARIZE:
                total_duration = get_audio_duration(str(audio_path))
                if total_duration > _MAX_GPT4O_DURATION_SECONDS:
                    needs_chunking = True

            if not needs_chunking:
                # Single-pass transcription
                logger.info("File %.1f MB within limits, single-pass transcription", file_size_mb)
                result = self._transcribe_single(
                    audio_path, model, check_cancelled, progress_callback
                )
                return result

            # ── Stage 3: measure duration ──────────────────────────────
            if total_duration is None:
                total_duration = get_audio_duration(str(audio_path))
            logger.info("Total duration: %.1f min", total_duration / 60)

            if check_cancelled:
                check_cancelled()

            # ── Stage 4: choose model-specific chunk parameters ────────
            if model == TranscriptionModel.GPT4O_DIARIZE:
                chunk_minutes = cfg.gpt4o_chunk_duration_minutes
                parallelism = cfg.gpt4o_chunk_parallelism
                force_duration = True
            else:
                chunk_minutes = cfg.chunk_duration_minutes
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
            # Clean up extracted audio temp dir
            if temp_audio is not None:
                temp_dir = temp_audio.parent
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Single-pass transcription
    # ------------------------------------------------------------------

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

    def _make_whisper_client(self):
        """Create a new OpenAI client for Whisper (thread-safe: one per thread)."""
        from gaik.software_components.config import create_openai_client

        # For audio endpoints, Azure may need a different base URL
        config = dict(self._api_config)
        if config.get("use_azure") and config.get("azure_audio_endpoint"):
            config["azure_endpoint"] = config["azure_audio_endpoint"]
        return create_openai_client(config)

    def _get_whisper_deployment(self) -> str:
        return self._api_config.get("transcription_model", "whisper")

    def _call_whisper_single(self, audio_path: Path) -> str:
        """Transcribe a single file with Whisper."""
        from ._retry import with_retry

        cfg = self._config
        client = self._make_whisper_client()
        deployment = self._get_whisper_deployment()

        def _do():
            with open(audio_path, "rb") as f:
                kwargs: dict = {
                    "model": deployment,
                    "file": f,
                    "response_format": "srt",  # always get SRT, convert later
                }
                if cfg.language and cfg.language != "auto":
                    kwargs["language"] = cfg.language
                if cfg.prompt:
                    kwargs["prompt"] = cfg.prompt
                return str(client.audio.transcriptions.create(**kwargs))

        return with_retry(
            _do,
            max_retries=cfg.max_retries,
            base_delay=cfg.retry_base_delay_seconds,
            max_429_retries=cfg.max_429_retries,
        )

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
                    kwargs: dict = {
                        "model": deployment,
                        "file": f,
                        "response_format": "srt",
                    }
                    if cfg.language and cfg.language != "auto":
                        kwargs["language"] = cfg.language
                    if cfg.prompt:
                        kwargs["prompt"] = cfg.prompt
                    return str(client.audio.transcriptions.create(**kwargs))

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

        indexed = list(enumerate(chunk_files))
        results: list[str | None] = [None] * total
        max_workers = min(parallelism, total)

        logger.info("Transcribing %d chunks (parallel=%d, model=whisper)", total, max_workers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_transcribe_one, item): item[0] for item in indexed}
            for future in concurrent.futures.as_completed(future_map):
                out_idx, transcription = future.result()
                results[out_idx] = transcription

        ordered = [t for t in results if t is not None]

        if progress_callback:
            progress_callback("merging", 0, 1, "Merging transcriptions …")

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

        url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
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

        indexed = list(enumerate(chunk_files))
        results: list[str | None] = [None] * total
        max_workers = min(parallelism, total)

        logger.info("Transcribing %d chunks (parallel=%d, model=gpt-4o)", total, max_workers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_transcribe_one, item): item[0] for item in indexed}
            for future in concurrent.futures.as_completed(future_map):
                out_idx, srt_content = future.result()
                results[out_idx] = srt_content

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
            return "WEBVTT\n\n" + srt_content.replace(",", ".")
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
