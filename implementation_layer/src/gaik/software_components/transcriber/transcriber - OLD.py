"""Reusable transcription package entry point."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openai
from openai import AzureOpenAI
from pydub import AudioSegment

from .whisper_local import transcribe as whisper_local_transcribe

DEFAULT_PROMPT = (
    "Detect the language and extract transcript in the same language. "
    "The audio could be in any language, such as English, Finnish, Swedish, etc."
)
ALLOWED_TRANSCRIPTION_MODELS = {"whisper", "gpt-4o-transcribe", "whisper_local"}


@dataclass
class TranscriptionResult:
    """Container for raw and enhanced transcripts."""

    raw_transcript: str
    enhanced_transcript: str | None
    job_id: str
    segments: list[dict] | None = None
    srt_content: str | None = None
    vtt_content: str | None = None

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
    """High-level transcription workflow with optional enhancement."""

    def __init__(
        self,
        api_config: dict,
        output_dir: str | Path = "transcriber_workspace",
        *,
        compress_audio: bool = True,  # kept for backward compatibility; no longer used
        enhanced_transcript: bool = False,
        max_size_mb: int = 25,
        max_duration_seconds: int = 1500,
        default_prompt: str = DEFAULT_PROMPT,
        transcription_model: str | None = None,
        language: str = "auto",
        diarization: bool = False,
        speaker_count: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        initial_prompt: str | None = None,
        local_api_base: str | None = None,
        local_api_key: str | None = None,
    ) -> None:
        self.api_config = api_config
        self.workspace_dir = Path(output_dir)
        self.compress_audio = compress_audio  # backward compat; not used in simplified flow
        self.enhanced_transcript = enhanced_transcript
        self.max_size_mb = max_size_mb
        self.max_duration_seconds = max_duration_seconds
        self.default_prompt = default_prompt
        self.transcription_model = transcription_model
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

        job_id = self._generate_job_id(input_path)

        print("=" * 80)
        print(f"Transcribing file: {input_path}")
        if use_case_name:
            print(f"Use case: {use_case_name}")
        print("=" * 80)

        # IMPORTANT: do NOT mutate self.default_prompt across calls.
        prompt = self.default_prompt + (("\n" + custom_context) if custom_context else "")
        print(f"Transcribing prompt: {prompt}")

        effective_model = self._resolve_transcription_model()
        self._warn_ignored_local_options(effective_model)

        segments: list[dict] | None = None
        srt_content: str | None = None
        vtt_content: str | None = None

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
            )

        enhanced_text: str | None = None
        if self.enhanced_transcript:
            print("Enhancing transcript for improved readability...")
            enhanced_text = post_process_transcript(raw_transcript, self.api_config)
        else:
            print("Transcript enhancement disabled; returning raw text only.")

        print("Transcription complete. Use TranscriptionResult.save(...) to persist output.")

        return TranscriptionResult(
            raw_transcript=raw_transcript,
            enhanced_transcript=enhanced_text,
            job_id=job_id,
            segments=segments,
            srt_content=srt_content,
            vtt_content=vtt_content,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_job_id(self, file_path: Path) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return hashlib.md5(f"{file_path.stem}_{timestamp}".encode()).hexdigest()[:10]

    def _resolve_transcription_model(self) -> str:
        if self.transcription_model is None:
            # Use config value (e.g. "whisper" from AZURE_TRANSCRIPTION_MODEL),
            # falling back to "whisper" which works as both Azure deployment name
            # and OpenAI model name.
            return self.api_config.get("transcription_model", "whisper")

        if self.transcription_model not in ALLOWED_TRANSCRIPTION_MODELS:
            allowed = ", ".join(sorted(ALLOWED_TRANSCRIPTION_MODELS))
            raise ValueError(
                f"Invalid transcription_model '{self.transcription_model}'. "
                f"Allowed values: {allowed}"
            )

        if self.transcription_model == "whisper_local":
            return "whisper_local"

        if self.transcription_model == "gpt-4o-transcribe":
            return "gpt-4o-transcribe"

        # explicit transcription_model == "whisper" -> use config or "whisper"
        return self.api_config.get("transcription_model", "whisper")

    def _warn_ignored_local_options(self, effective_model: str) -> None:
        if effective_model == "whisper_local":
            return

        has_local_overrides = any(
            [
                self.language != "auto",
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
        self, input_path: Path, prompt: str, transcription_model: str
    ) -> str:
        """
        If input <= max_size_mb: single-pass transcription using the original file
        (audio OR video container supported by the API).
        Else: chunk with PyDub and transcribe sequentially.
        """
        if self._needs_chunking(input_path):
            print("Chunking input for transcription...")
            audio = AudioSegment.from_file(
                input_path
            )  # works for audio, and many video containers via ffmpeg
            return split_and_transcribe_with_context(
                str(input_path),
                self.api_config,
                self.max_size_mb,
                self.max_duration_seconds,
                audio,
                base_prompt=prompt,
                transcription_model=transcription_model,
            )

        print("Transcribing in a single request (original file)...")
        return self._single_pass_transcription(input_path, prompt, transcription_model)

    def _needs_chunking(self, file_path: Path) -> bool:
        size_mb = file_path.stat().st_size / (1024 * 1024)
        return size_mb > self.max_size_mb

    def _single_pass_transcription(
        self, file_path: Path, prompt: str, transcription_model: str
    ) -> str:
        """
        Single-pass transcription of the original file (audio OR video).
        """
        use_azure = bool(self.api_config.get("use_azure", False))
        api_key = self.api_config.get("api_key")

        with file_path.open("rb") as f:
            if use_azure:
                audio_client = self._build_azure_audio_client()
                response = audio_client.audio.transcriptions.create(
                    model=transcription_model,
                    file=f,
                    prompt=prompt,
                )
            else:
                openai.api_key = api_key
                response = openai.audio.transcriptions.create(
                    model=transcription_model,
                    file=f,
                    prompt=prompt,
                )
        return response.text

    def _build_azure_audio_client(self) -> AzureOpenAI:
        api_key = self.api_config.get("api_key")
        api_version = self.api_config.get("api_version", "2024-12-01-preview")
        audio_endpoint = self.api_config.get(
            "azure_audio_endpoint",
            self.api_config.get("azure_endpoint", "").replace(
                "chat/completions?", "audio/transcriptions?"
            ),
        )

        return AzureOpenAI(
            api_key=api_key,
            azure_endpoint=audio_endpoint.split("/openai/")[0],
            api_version=api_version,
        )


def post_process_transcript(raw_transcript: str, api_config: dict) -> str:
    """Enhance transcript quality with GPT models."""

    model_name = api_config.get("model", "GPT model")
    print(f"Enhancing transcript quality with {model_name}...")
    prompt = f"""
    You are an expert transcript editor. Please improve the following \
raw transcript. The transcript could be in any language, e.g., \
English, Finnish, Swedish, etc.

    Your task is to:
    1. Fix any transcription errors, inconsistencies, and unclear speech
    2. Create proper dialogue structure
    3. Format the text with appropriate paragraphs and line breaks for readability
    4. Ensure the conversation flows naturally between segments and timestamp blocks
    5. Retain all factual information without altering meaning or context
    6. Do not add any content that wasn't in the original transcript

    **QUALITY ENHANCEMENT:**
    - Remove filler words (um, uh, you know) for clarity while preserving natural speech patterns
    - Fix grammatical errors, spelling mistakes, and incomplete sentences
    - Use consistent terms/words for a concept.
    - Ensure proper capitalization and punctuation
    - Group related statements by the same speaker into coherent paragraphs
    - Add line breaks between different speakers for visual clarity

    Return ONLY the enhanced transcript. Do not include any explanatory text or commentary.

    RAW TRANSCRIPT:
    {raw_transcript}
    """

    try:
        use_azure = bool(api_config.get("use_azure", False))
        if use_azure:
            client = AzureOpenAI(
                api_key=api_config.get("api_key"),
                azure_endpoint=api_config.get("azure_endpoint", ""),
                api_version=api_config.get("api_version", "2024-12-01-preview"),
            )
            chat_model = api_config.get("model", "gpt-4.1")
            response = client.chat.completions.create(
                model=chat_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert transcript editor who improves the quality, "
                            "readability, and structure of transcribed conversations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
        else:
            openai.api_key = api_config.get("api_key")
            chat_model = api_config.get("model", "gpt-4.1-2025-04-14")
            response = openai.chat.completions.create(
                model=chat_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert transcript editor who improves the quality, "
                            "readability, and structure of transcribed conversations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )

        return response.choices[0].message.content
    except Exception as e:
        print(f"Error enhancing transcript: {e}")
        print("Falling back to raw transcript...")
        return raw_transcript


def split_and_transcribe_with_context(
    audio_path,
    api_config,
    max_size_mb=25,
    max_duration_seconds=1500,
    audio=None,
    base_prompt: str = DEFAULT_PROMPT,
    transcription_model: str | None = None,
):
    """Split audio into chunks and transcribe with rolling context."""

    use_azure = bool(api_config.get("use_azure", False))
    api_key = api_config.get("api_key")
    if transcription_model is None:
        transcription_model = api_config.get("transcription_model", "whisper")

    if audio is None:
        audio = AudioSegment.from_file(audio_path)

    duration_seconds = len(audio) / 1000
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    chunks_by_size = math.ceil(file_size_mb / (max_size_mb * 0.9))
    chunks_by_duration = math.ceil(duration_seconds / (max_duration_seconds * 0.95))
    num_chunks = max(1, max(chunks_by_size, chunks_by_duration))

    print(f"Splitting into {num_chunks} chunks based on size and duration")

    chunk_length_ms = len(audio) // num_chunks
    temp_dir = tempfile.mkdtemp()

    transcripts = []
    context_text = ""

    if use_azure:
        audio_endpoint_url = api_config.get(
            "azure_audio_endpoint",
            api_config.get("azure_endpoint", "").replace(
                "chat/completions?", "audio/transcriptions?"
            ),
        )
        audio_client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=audio_endpoint_url.split("/openai/")[0],
            api_version=api_config.get("api_version", "2024-12-01-preview"),
        )
    else:
        openai.api_key = api_key
        audio_client = None

    try:
        for i in range(num_chunks):
            start_ms = i * chunk_length_ms
            end_ms = min((i + 1) * chunk_length_ms, len(audio))
            chunk = audio[start_ms:end_ms]

            chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
            chunk.export(chunk_path, format="mp3")

            start_time = format_timestamp(start_ms / 1000)
            end_time = format_timestamp(end_ms / 1000)
            chunk_header = f"\n[Timestamp: {start_time} - {end_time}]\n"

            if i == 0:
                prompt = base_prompt
            else:
                trimmed_context = context_text[-170:] if len(context_text) > 170 else context_text
                prompt = f"""The following is a continuation of a \
conversation. Here is the previous part of the transcript:

{trimmed_context}

Continue the transcription, maintaining speaker consistency and dialogue structure."""

            try:
                with open(chunk_path, "rb") as chunk_file:
                    if use_azure:
                        transcript_response = audio_client.audio.transcriptions.create(
                            model=transcription_model,
                            file=chunk_file,
                            prompt=prompt,
                        )
                    else:
                        transcript_response = openai.audio.transcriptions.create(
                            model=transcription_model,
                            file=chunk_file,
                            prompt=prompt,
                        )

                    chunk_transcript = transcript_response.text
                    transcripts.append(chunk_header + chunk_transcript)
                    context_text = chunk_transcript
                    time.sleep(1)
            except Exception as exc:
                print(f"Error transcribing chunk {i + 1}: {exc}")
                transcripts.append(f"{chunk_header}[Transcription failed for segment {i + 1}]")
                time.sleep(5)
            finally:
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return "\n\n".join(transcripts)


def split_and_transcribe(
    audio_path,
    api_config,
    max_size_mb=25,
    max_duration_seconds=1500,
    audio=None,
):
    """Backward-compatible wrapper without explicit context parameter."""
    return split_and_transcribe_with_context(
        audio_path,
        api_config,
        max_size_mb=max_size_mb,
        max_duration_seconds=max_duration_seconds,
        audio=audio,
    )


def format_timestamp(seconds):
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"
