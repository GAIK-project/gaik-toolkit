"""Reusable transcription package entry point."""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from openai import AzureOpenAI
from pydub import AudioSegment
from pydub.audio_segment import fix_wav_headers
from pydub.exceptions import CouldntDecodeError

from gaik.observability import measure_duration
from gaik.software_components.config import create_openai_client
from gaik.software_components.endpoints import check_endpoint
from gaik.software_components.enhance_transcript import (
    DEFAULT_MAX_CHANGE_RATIO,
    TranscriptEnhancer,
)
from gaik.software_components.input_limits import (
    InputLimits,
    check_not_media_list,
    media_input_args,
)
from gaik.software_components.llm.base import UsageCounter
from gaik.software_components.llm.factory import assert_openai_or_azure
from gaik.software_components.llm.providers import resolve_provider

from .srt_utils import format_timestamp
from .whisper_local import transcribe as whisper_local_transcribe

DEFAULT_PROMPT = (
    "Detect the language and extract transcript in the same language. "
    "The audio could be in any language, such as English, Finnish, Swedish, etc."
)
ALLOWED_TRANSCRIPTION_MODELS = {"whisper", "whisper-1", "gpt-4o-transcribe", "whisper_local"}

# OpenAI's transcription API refuses audio longer than 1400 s:
#   "audio duration 1433.728 seconds is longer than 1400 seconds which is the
#    maximum for this model"
# Both the single-pass guard and the chunker stay under this ceiling, so a file
# can never land in a gap where our own duration check passes but the API says
# no. Not applicable to `whisper_local`, which does not go through this path.
REMOTE_MAX_DURATION_SECONDS = 1400

# Default chunking threshold, with margin below the API ceiling.
DEFAULT_MAX_DURATION_SECONDS = 1200


# Decoding a long recording to WAV takes a while; this only stops one that hangs.
DECODE_TIMEOUT_SECONDS = 30 * 60


def _read_pcm_wav(path: Path) -> AudioSegment | None:
    """Read a PCM WAV with pydub's own Python reader; ``None`` for any other file.

    No ffmpeg runs, so a WAV's duration and chunks hold where ffmpeg is not
    installed, as they did when pydub read a ``.wav`` itself.
    """
    with path.open("rb") as handle:
        head = handle.read(12)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return None
        handle.seek(0)
        data = handle.read()
    try:
        return AudioSegment(data=data)
    except (CouldntDecodeError, struct.error, ValueError):
        return None  # not plain PCM; ffmpeg decodes it


def _decode_audio(path: str | Path) -> AudioSegment:
    """Decode the local file at ``path`` into a pydub segment.

    A PCM WAV is read in Python (:func:`_read_pcm_wav`). Anything else goes
    through ffmpeg, which runs here, not inside pydub, with the arguments every
    other media call uses
    (:func:`~gaik.software_components.input_limits.media_input_args`): the path
    is absolute, so a name such as ``http:...`` or ``concat:...`` is a file, and only
    the ``file`` protocol is allowed, so nothing the file's content names (a stream
    address, another file in a manifest) is opened over the network. pydub then reads
    the WAV ffmpeg wrote with its own Python code, without starting ffmpeg again.

    Raises:
        OSError: If ``path`` is not a file that can be opened, or ffmpeg is missing.
        subprocess.CalledProcessError: If ffmpeg cannot decode the file.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path.name}")
    wav_segment = _read_pcm_wav(path)
    if wav_segment is not None:
        return wav_segment
    decoded = subprocess.run(
        [
            AudioSegment.converter,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            *media_input_args(path),
            "-vn",
            "-f",
            "wav",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=DECODE_TIMEOUT_SECONDS,
    ).stdout
    wav = bytearray(decoded)
    del decoded  # one copy of the decoded audio at a time
    fix_wav_headers(wav)  # a WAV written to a pipe carries no final sizes
    return AudioSegment.from_file(io.BytesIO(bytes(wav)), format="wav")


def _audio_provider(api_config: dict) -> str:
    """Resolve the audio backend the way ``create_openai_client`` does.

    A bare legacy config (neither ``provider`` nor ``use_azure``) has always meant
    standard OpenAI, whatever ``LLM_PROVIDER`` says.
    """
    provider = resolve_provider(config={"use_azure": False, **api_config})
    assert_openai_or_azure({"provider": provider}, component="Transcriber")
    return provider


def _transcription_usage(response) -> dict[str, int]:
    """The usage of one transcription response, in chat-style token keys."""
    usage = response.usage
    if usage is None:
        return {}
    if usage.type == "tokens":
        return {
            "prompt_tokens": usage.input_tokens,
            "completion_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
        }
    if usage.type == "duration":
        return {"audio_seconds": math.ceil(usage.seconds)}
    raise ValueError(f"Unknown transcription usage type {usage.type!r}")


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
    keeps its own path. ParallelTranscriber has the same cut.
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


def _create_audio_client(api_config: dict):
    """Create an isolated SDK client, preserving the caller's HTTP transport.

    On Azure the audio goes to ``azure_audio_endpoint``, else ``azure_endpoint``, else
    ``base_url``, cut to the resource address and passed as ``azure_endpoint``, so the
    SDK requests ``/openai/deployments/<model>/audio/...`` (a ``/openai/v1``
    ``base_url`` kept as it is gives ``/openai/v1/deployments/...``, which Azure does
    not serve).
    """
    provider = _audio_provider(api_config)
    audio_config = {**api_config, "provider": provider, "use_azure": provider == "azure"}
    if provider == "azure":
        endpoint = (
            api_config.get("azure_audio_endpoint")
            or api_config.get("azure_endpoint")
            or api_config.get("base_url")
        )
        if endpoint:
            audio_config["azure_endpoint"] = _azure_resource_endpoint(endpoint)
            audio_config.pop("base_url", None)
        if not audio_config.get("api_version"):
            audio_config["api_version"] = "2024-12-01-preview"
    return create_openai_client(audio_config)


def _close_owned_audio_client(client, api_config: dict) -> None:
    # SDK close() also closes an injected transport. Its caller may reuse that
    # transport for enhancement or another attachment in the same request.
    if client is not None and api_config.get("http_client") is None:
        client.close()


@dataclass
class TranscriptionResult:
    """Container for raw and corrected transcripts.

    The trailing ``duration_s`` / ``audio_duration_s`` / ``model_used``
    fields are optional so existing call sites that build a
    ``TranscriptionResult`` by hand do not have to change. The transcriber
    populates them on every successful run.
    """

    raw_transcript: str
    enhanced_transcript: str | None
    job_id: str
    segments: list[dict] | None = None
    srt_content: str | None = None
    vtt_content: str | None = None
    duration_s: float | None = None  # transcriber wall-clock seconds
    audio_duration_s: float | None = None  # input audio length in seconds
    model_used: str | None = None  # resolved transcription model
    # Usage of the transcription requests (not of transcript enhancement): token counts,
    # or ``audio_seconds`` for duration-billed models; empty for local Whisper.
    usage: dict[str, int] = field(default_factory=dict)
    # Enhancement passes refused because they changed digits or too much of the text
    # (TranscriptEnhancer.refused_passes, as dicts); the raw transcript was kept for them.
    enhancement_refused_passes: list[dict] | None = None
    # Segments of a split recording that could not be transcribed (only with
    # allow_partial=True), one dict each: "segment" (1-based), "start_seconds" and
    # "end_seconds". Empty when every segment was transcribed.
    failed_segments: list[dict] = field(default_factory=list)

    def save(
        self,
        directory: str | Path,
        *,
        save_raw: bool = True,
        save_enhanced: bool = True,
        encoding: str = "utf-8",
    ) -> dict[str, Path | None]:
        """
        Persist transcripts to disk. Returns mapping of artifact type to path.
        """
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved: dict[str, Path | None] = {}

        if save_raw:
            raw_path = output_dir / f"{self.job_id}_raw_transcript.txt"
            raw_path.write_text(self.raw_transcript, encoding=encoding)
            saved["raw"] = raw_path

        if save_enhanced:
            if self.enhanced_transcript is None:
                saved["enhanced"] = None
            else:
                enhanced_path = output_dir / f"{self.job_id}_transcript.txt"
                enhanced_path.write_text(self.enhanced_transcript, encoding=encoding)
                saved["enhanced"] = enhanced_path

        return saved


class Transcriber:
    """High-level transcription workflow with optional transcript error fixing.

    A long recording is split into several paid transcription calls, so a file
    over ``limits`` (``max_media_seconds``, default 6 hours; ``max_media_bytes``,
    off by default) is refused with
    :class:`~gaik.software_components.input_limits.InputLimitError` before the
    first call. The duration is read with ffprobe (with a timeout) or, when
    ffprobe cannot read it, from the decoded audio. ``max_size_mb`` and
    ``max_duration_seconds`` only decide when a file is split into chunks.

    When a chunk of a split recording cannot be transcribed, ``transcribe``
    raises a :class:`RuntimeError` naming its time range, and the remaining
    chunks are not sent. With ``allow_partial=True`` the transcript comes back
    with a ``[Transcription failed for segment N]`` line under that chunk's
    timestamp instead, and :attr:`TranscriptionResult.failed_segments` lists the
    failed chunks; a run in which every chunk failed still raises.
    """

    def __init__(
        self,
        api_config: dict,
        output_dir: str | Path = "transcriber_workspace",
        *,
        compress_audio: bool = True,  # kept for backward compatibility; no longer used
        enhanced_transcript: bool = False,
        max_size_mb: int = 25,
        max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
        default_prompt: str | None = None,
        transcription_model: str | None = None,
        enhanced_transcript_instructions: str | None = None,
        enhancement_max_change_ratio: float | None = DEFAULT_MAX_CHANGE_RATIO,
        language: str = "auto",
        diarization: bool = False,
        speaker_count: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        initial_prompt: str | None = None,
        local_api_base: str | None = None,
        local_api_key: str | None = None,
        limits: InputLimits | None = None,
        allow_partial: bool = False,
    ) -> None:
        _audio_provider(api_config)
        # Checked here as TranscriptEnhancer checks it, so a wrong value fails before a
        # paid transcription rather than when the enhancer is built after it.
        if enhancement_max_change_ratio is not None and not 0 < enhancement_max_change_ratio <= 1:
            raise ValueError("enhancement_max_change_ratio must be between 0 and 1, or None")
        if transcription_model == "whisper_local" and local_api_base:
            check_endpoint(
                local_api_base,
                provider="whisper_local",
                allowed_hosts=api_config.get("allowed_endpoint_hosts"),
                what="local_api_base",
            )
        self.limits = limits or InputLimits()
        self.allow_partial = allow_partial
        self.api_config = api_config
        self.workspace_dir = Path(output_dir)
        self.compress_audio = compress_audio  # backward compat; not used in simplified flow
        self.enhanced_transcript_enabled = enhanced_transcript
        self.max_size_mb = max_size_mb
        self.max_duration_seconds = max_duration_seconds
        self.default_prompt = default_prompt
        self.transcription_model = transcription_model
        self.enhanced_transcript_instructions = enhanced_transcript_instructions
        self.enhancement_max_change_ratio = enhancement_max_change_ratio
        self.language = language
        self.diarization = diarization
        self.speaker_count = speaker_count
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.initial_prompt = initial_prompt
        self.local_api_base = local_api_base
        self.local_api_key = local_api_key
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def transcribe(
        self,
        file_path: str | Path,
        *,
        custom_context: str = "",
        use_case_name: str | None = None,
        compress_audio: bool | None = None,  # kept for backward compatibility; no longer used
    ) -> TranscriptionResult:
        """Transcribe an audio or video file and return transcript info."""

        input_path = Path(file_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        self.limits.check_media(input_path)

        job_id = self._generate_job_id(input_path)

        print("=" * 80)
        print(f"Transcribing job {job_id} ({input_path.suffix.lower() or 'no extension'})")
        if use_case_name:
            print(f"Use case: {use_case_name}")
        print("=" * 80)

        # IMPORTANT: do NOT mutate self.default_prompt across calls.
        prompt = self.default_prompt
        if custom_context:
            prompt = f"{prompt}\n{custom_context}" if prompt is not None else custom_context
        print(f"Transcription prompt: {len(prompt) if prompt is not None else 0} characters")

        effective_model = self._resolve_transcription_model()
        self._warn_ignored_local_options(effective_model)
        if effective_model != "whisper_local":
            _check_cloud_language(self.language)

        # Best-effort input audio duration. PyDub can decode both audio and
        # video containers; if it fails (corrupt file, unsupported codec)
        # we fall back to None rather than blocking transcription.
        audio_duration_s: float | None = None
        try:
            audio_duration_s = round(len(_decode_audio(input_path)) / 1000.0, 3)
        except Exception as exc:
            print(f"Could not read audio duration: {exc}")
        if audio_duration_s is not None:
            self.limits.check_media_seconds(audio_duration_s, input_path.name)

        segments: list[dict] | None = None
        srt_content: str | None = None
        vtt_content: str | None = None
        usage = UsageCounter()
        failed_segments: list[dict] = []

        with measure_duration() as elapsed:
            if effective_model == "whisper_local":
                raw_transcript, segments = self._transcribe_input_local(input_path)
                if segments:
                    from .srt_utils import segments_to_srt, segments_to_vtt

                    srt_content = segments_to_srt(segments)
                    vtt_content = segments_to_vtt(segments)
            else:
                # Simplified: do not extract/compress audio. Use original file if <= 25MB,
                # otherwise chunk via PyDub (which can decode both audio and video containers).
                raw_transcript = self._transcribe_input_remote(
                    input_path=input_path,
                    prompt=prompt,
                    transcription_model=effective_model,
                    usage=usage,
                    failed_segments=failed_segments,
                )

            enhanced_text: str | None = None
            refused_passes: list[dict] | None = None
            if self.enhanced_transcript_enabled:
                print("Fixing transcription errors with TranscriptEnhancer...")
                enhancer = TranscriptEnhancer(
                    api_config=self.api_config,
                    max_change_ratio=self.enhancement_max_change_ratio,
                )
                enhanced_result = enhancer.enhance_text(
                    raw_transcript,
                    additional_instructions=self.enhanced_transcript_instructions,
                )
                enhanced_text = enhanced_result.enhanced_text
                refused_passes = [r.model_dump() for r in enhanced_result.refused_passes]
            else:
                print("Transcript error fixing disabled; returning raw text only.")
        duration_s = round(elapsed(), 3)

        print("Transcription complete. Use TranscriptionResult.save(...) to persist output.")

        return TranscriptionResult(
            raw_transcript=raw_transcript,
            enhanced_transcript=enhanced_text,
            enhancement_refused_passes=refused_passes,
            job_id=job_id,
            segments=segments,
            srt_content=srt_content,
            vtt_content=vtt_content,
            duration_s=duration_s,
            audio_duration_s=audio_duration_s,
            model_used=effective_model,
            usage=usage.snapshot(),
            failed_segments=failed_segments,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_job_id(self, file_path: Path) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return hashlib.md5(f"{file_path.stem}_{timestamp}".encode()).hexdigest()[:10]

    def _resolve_transcription_model(self) -> str:
        # Follow the same provider as the audio client, so {"provider": "azure"}
        # without the legacy use_azure flag still gets an Azure deployment name.
        is_azure = _audio_provider(self.api_config) == "azure"
        if self.transcription_model is not None:
            if self.transcription_model not in ALLOWED_TRANSCRIPTION_MODELS:
                allowed = ", ".join(sorted(ALLOWED_TRANSCRIPTION_MODELS))
                raise ValueError(
                    f"Invalid transcription_model '{self.transcription_model}'. "
                    f"Allowed values: {allowed}"
                )

            # An explicit choice wins over the config, so asking for Whisper on a
            # config that names gpt-4o (or the other way round) is honoured.
            if self.transcription_model in ("whisper_local", "gpt-4o-transcribe"):
                return self.transcription_model

            if not is_azure:
                return "whisper-1"

            return self.api_config.get("transcription_model") or "whisper"

        configured = self.api_config.get("transcription_model")

        # On Azure the model is a deployment name, so whatever the config says
        # is authoritative and "whisper" is the conventional fallback. On
        # OpenAI the only valid Whisper model id is "whisper-1" — plain
        # "whisper" is a 404 there.
        if is_azure:
            return configured or "whisper"

        return "whisper-1" if configured in (None, "", "whisper") else configured

    def _warn_ignored_local_options(self, effective_model: str) -> None:
        if effective_model == "whisper_local":
            return

        has_local_overrides = any(
            [
                self.diarization is not False,
                self.speaker_count is not None,
                self.min_speakers is not None,
                self.max_speakers is not None,
                self.initial_prompt is not None,
                self.local_api_base is not None,
                self.local_api_key is not None,
            ]
        )
        if has_local_overrides:
            print(
                "Local transcription options are ignored unless "
                "transcription_model='whisper_local'."
            )

    def _transcribe_input_local(self, input_path: Path) -> tuple[str, list[dict] | None]:
        """Transcribe via local Whisper and return (text, segments)."""
        if not self.local_api_base:
            raise ValueError("local_api_base is required when transcription_model='whisper_local'.")
        if not self.local_api_key:
            raise ValueError("local_api_key is required when transcription_model='whisper_local'.")

        result = whisper_local_transcribe(
            audio_path=input_path,
            api_base=self.local_api_base,
            key=self.local_api_key,
            allowed_endpoint_hosts=self.api_config.get("allowed_endpoint_hosts"),
            language=self.language,
            diarization=self.diarization,
            speaker_count=self.speaker_count,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
            initial_prompt=self.initial_prompt,
        )

        segments = result.get("segments") or []
        text = (result.get("text") or "").strip()
        if not text and segments:
            text = " ".join(
                segment.get("text", "").strip() for segment in segments if segment.get("text")
            ).strip()

        return text, segments or None

    def _transcribe_input_remote(
        self,
        input_path: Path,
        prompt: str | None,
        transcription_model: str,
        usage: UsageCounter | None = None,
        failed_segments: list[dict] | None = None,
    ) -> str:
        """
        If input is within configured size and duration limits: single-pass
        transcription using the original file (audio OR video container
        supported by the API). Otherwise, chunk with PyDub and transcribe
        sequentially. Chunking is model-independent; every remote transcription
        model goes through the same size/duration guard.

        ``failed_segments``, if given, gets the chunks that failed (with
        ``allow_partial``) appended, as :func:`split_and_transcribe_with_context`.
        """
        if self._needs_chunking(input_path):
            print("Chunking input for transcription...")
            audio = _decode_audio(input_path)  # audio, and many video containers via ffmpeg
            self.limits.check_media_seconds(len(audio) / 1000, input_path.name)
            return split_and_transcribe_with_context(
                str(input_path),
                self.api_config,
                self.max_size_mb,
                self.max_duration_seconds,
                audio,
                base_prompt=prompt,
                transcription_model=transcription_model,
                usage=usage,
                language=self.language,
                allow_partial=self.allow_partial,
                failed_segments=failed_segments,
            )

        print("Transcribing in a single request (original file)...")
        return self._single_pass_transcription(input_path, prompt, transcription_model, usage)

    def _needs_chunking(self, file_path: Path) -> bool:
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > self.max_size_mb:
            return True

        try:
            duration_seconds = len(_decode_audio(file_path)) / 1000
        except Exception as exc:
            print(f"Could not read audio duration for chunking check: {exc}")
            return False

        # A caller-supplied value above the API ceiling would only produce a
        # request the API rejects, so cap it here rather than pass it through.
        return duration_seconds > min(self.max_duration_seconds, REMOTE_MAX_DURATION_SECONDS)

    def _single_pass_transcription(
        self,
        file_path: Path,
        prompt: str | None,
        transcription_model: str,
        usage: UsageCounter | None = None,
    ) -> str:
        """
        Single-pass transcription of the original file (audio OR video).
        """
        audio_client = _create_audio_client(self.api_config)
        try:
            with file_path.open("rb") as f:
                response = audio_client.audio.transcriptions.create(
                    **_transcription_request(transcription_model, f, prompt, self.language)
                )
            if usage is not None:
                usage.add(_transcription_usage(response))
            return response.text
        finally:
            _close_owned_audio_client(audio_client, self.api_config)

    def _build_azure_audio_client(self) -> AzureOpenAI:
        return _create_audio_client(self.api_config)


def _sends_language(language: str | None) -> bool:
    return language not in (None, "", "auto")


def _check_cloud_language(language: str | None) -> None:
    """Refuse, before any request, a language a cloud model cannot take."""
    if _sends_language(language) and not re.fullmatch(r"[a-z]{2}", str(language)):
        raise ValueError(
            f"language={language!r} is not a two-letter ISO-639-1 code (such as 'fi' or "
            "'en'). Cloud transcription models take such a code, or 'auto' to detect it."
        )


def _transcription_request(model: str, file, prompt: str | None, language: str | None) -> dict:
    """The keyword arguments of one ``audio.transcriptions.create`` call."""
    request: dict = {"model": model, "file": file}
    if prompt is not None:
        request["prompt"] = prompt
    if _sends_language(language):
        request["language"] = language
    return request


# How much of the previous chunk's transcript a chunk request carries.
_PREVIOUS_TRANSCRIPT_CHARS = 170


def _chunk_prompt(base_prompt: str | None, previous_transcript: str) -> str | None:
    """The prompt of a chunk after the first: the caller's context, then the end of
    the previous chunk's transcript.

    The transcript comes last because the provider reads the prompt as the text just
    before the audio (``whisper-1`` keeps only its final 224 tokens). ``None`` when
    there is neither, so the request carries no prompt.
    """
    tail = previous_transcript[-_PREVIOUS_TRANSCRIPT_CHARS:]
    return "\n".join(part for part in (base_prompt, tail) if part) or None


def split_and_transcribe_with_context(
    audio_path,
    api_config,
    max_size_mb=25,
    max_duration_seconds=DEFAULT_MAX_DURATION_SECONDS,
    audio=None,
    base_prompt: str | None = None,
    transcription_model: str | None = None,
    usage: UsageCounter | None = None,
    language: str | None = None,
    allow_partial: bool = False,
    failed_segments: list[dict] | None = None,
):
    """Split audio into chunks and transcribe with rolling context.

    ``usage``, if given, gets the usage of every chunk request added to it.
    ``language``, a two-letter ISO-639-1 code, goes with every chunk request;
    ``None`` or ``"auto"`` sends none, so the provider detects the language.

    A chunk that cannot be transcribed raises a :class:`RuntimeError` naming its
    time range, and the remaining chunks are not sent. With
    ``allow_partial=True`` the chunk is marked
    ``[Transcription failed for segment N]`` under its timestamp and the rest
    are transcribed; ``failed_segments``, if given, gets one dict per failed
    chunk appended (``segment``, 1-based, ``start_seconds``, ``end_seconds``).

    Raises:
        RuntimeError: If a chunk cannot be transcribed, or, with
            ``allow_partial=True``, if no chunk can be.
        ValueError: If ``audio_path`` is a playlist or file list rather than a
            recording (:func:`~gaik.software_components.input_limits.check_not_media_list`).
    """

    _audio_provider(api_config)
    check_not_media_list(audio_path)
    if transcription_model is None:
        transcription_model = api_config.get("transcription_model", "whisper")

    if audio is None:
        audio = _decode_audio(audio_path)

    duration_seconds = len(audio) / 1000
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    # Cap the per-chunk budget at the API ceiling: splitting on a larger value
    # would just hand the API chunks it refuses (e.g. 2850 s at a budget of
    # 1500 s yields two 1425 s chunks, both over the 1400 s limit).
    duration_budget = min(max_duration_seconds, REMOTE_MAX_DURATION_SECONDS)

    chunks_by_size = math.ceil(file_size_mb / (max_size_mb * 0.9))
    chunks_by_duration = math.ceil(duration_seconds / (duration_budget * 0.95))
    num_chunks = max(1, max(chunks_by_size, chunks_by_duration))

    print(f"Splitting into {num_chunks} chunks based on size and duration")

    chunk_length_ms = len(audio) // num_chunks
    temp_dir = tempfile.mkdtemp()

    transcripts = []
    context_text = ""
    failed: list[dict] = []
    error_types: list[str] = []

    audio_client = None
    try:
        audio_client = _create_audio_client(api_config)
        for i in range(num_chunks):
            start_ms = i * chunk_length_ms
            end_ms = min((i + 1) * chunk_length_ms, len(audio))
            chunk = audio[start_ms:end_ms]

            chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
            chunk.export(chunk_path, format="mp3")

            start_time = format_timestamp(start_ms / 1000)
            end_time = format_timestamp(end_ms / 1000)
            chunk_header = f"\n[Timestamp: {start_time} - {end_time}]\n"

            # The caller's context (names, terms) goes with every chunk, not just the
            # first; a later chunk also continues from the previous transcript.
            prompt = base_prompt if i == 0 else _chunk_prompt(base_prompt, context_text)

            try:
                with open(chunk_path, "rb") as chunk_file:
                    transcript_response = audio_client.audio.transcriptions.create(
                        **_transcription_request(transcription_model, chunk_file, prompt, language)
                    )

                    chunk_transcript = transcript_response.text
                    transcripts.append(chunk_header + chunk_transcript)
                    context_text = chunk_transcript
                    time.sleep(1)
            except Exception as exc:
                print(f"Error transcribing chunk {i + 1}: {type(exc).__name__}")
                if not allow_partial:
                    raise RuntimeError(
                        f"Segment {i + 1} of {num_chunks} ({start_time} - {end_time}) could "
                        f"not be transcribed ({type(exc).__name__}); pass allow_partial=True "
                        "to get the transcript with this segment marked as failed."
                    ) from None
                transcripts.append(f"{chunk_header}[Transcription failed for segment {i + 1}]")
                failed.append(
                    {
                        "segment": i + 1,
                        "start_seconds": start_ms / 1000,
                        "end_seconds": end_ms / 1000,
                    }
                )
                if type(exc).__name__ not in error_types:
                    error_types.append(type(exc).__name__)
                time.sleep(5)
            else:
                # Outside the try: a usage error must raise, not mark a good chunk as failed.
                if usage is not None:
                    usage.add(_transcription_usage(transcript_response))
            finally:
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass
    finally:
        _close_owned_audio_client(audio_client, api_config)
        shutil.rmtree(temp_dir, ignore_errors=True)

    if failed and len(failed) == num_chunks:
        # Markers alone are no transcript: fail as the single-pass path does.
        raise RuntimeError(
            f"None of the {num_chunks} segments could be transcribed "
            f"({', '.join(error_types)}), so there is no transcript."
        )
    if failed:
        numbers = ", ".join(str(segment["segment"]) for segment in failed)
        print(f"Segments {numbers} of {num_chunks} could not be transcribed; they are marked.")
    if failed_segments is not None:
        failed_segments.extend(failed)
    return "\n\n".join(transcripts)


def split_and_transcribe(
    audio_path,
    api_config,
    max_size_mb=25,
    max_duration_seconds=DEFAULT_MAX_DURATION_SECONDS,
    audio=None,
    allow_partial: bool = False,
):
    """Backward-compatible wrapper without explicit context parameter.

    Since gaik 0.12.0 a chunk that fails raises ``RuntimeError``;
    ``allow_partial=True`` keeps the earlier marked result.
    """
    return split_and_transcribe_with_context(
        audio_path,
        api_config,
        max_size_mb=max_size_mb,
        max_duration_seconds=max_duration_seconds,
        audio=audio,
        allow_partial=allow_partial,
    )
