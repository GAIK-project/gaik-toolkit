"""Reusable transcription package entry point."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openai
from openai import AzureOpenAI
from pydub import AudioSegment

DEFAULT_PROMPT = "Detect the language and extract transcript in the same language. The audio could be in any language, such as English, Finnish, Swedish, etc."


@dataclass
class TranscriptionResult:
    """Container for raw and enhanced transcripts."""

    raw_transcript: str
    enhanced_transcript: str | None
    job_id: str

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
        compress_audio: bool = True,
        enhanced_transcript: bool = True,
        max_size_mb: int = 25,
        max_duration_seconds: int = 1500,
        default_prompt: str = DEFAULT_PROMPT,
    ) -> None:
        self.api_config = api_config
        self.workspace_dir = Path(output_dir)
        self.compress_audio = compress_audio
        self.enhanced_transcript = enhanced_transcript
        self.max_size_mb = max_size_mb
        self.max_duration_seconds = max_duration_seconds
        self.default_prompt = default_prompt
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def transcribe(
        self,
        file_path: str | Path,
        *,
        custom_context: str = "",
        use_case_name: str | None = None,
        compress_audio: bool | None = None,
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

        cleanup_paths: list[Path] = []
        try:
            audio_path, temps = self._prepare_audio(
                input_path, job_id, compress_audio=compress_audio
            )
            cleanup_paths.extend(temps)

            if custom_context:
                self.default_prompt = self.default_prompt + "\n" + custom_context
            prompt = self.default_prompt
            print(f"Transcribing prompt: {prompt}")
            # prompt = custom_context or self.default_prompt
            raw_transcript = self._transcribe_audio(audio_path, prompt)

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
            )
        finally:
            self._cleanup_files(cleanup_paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_job_id(self, file_path: Path) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return hashlib.md5(f"{file_path.stem}_{timestamp}".encode()).hexdigest()[:10]

    def _prepare_audio(
        self,
        input_path: Path,
        job_id: str,
        *,
        compress_audio: bool | None = None,
    ) -> tuple[Path, list[Path]]:
        compress = self.compress_audio if compress_audio is None else compress_audio
        temp_paths: list[Path] = []

        if self._has_video_stream(input_path):
            print("Video detected. Extracting audio track...")
            extracted = self._extract_audio_from_video(input_path, job_id)
            if extracted:
                temp_paths.append(extracted)
                return extracted, temp_paths
            print("FFmpeg unavailable; using original file.")
            return input_path, temp_paths

        size_mb = input_path.stat().st_size / (1024 * 1024)
        if size_mb > self.max_size_mb and compress:
            print(
                f"Large audio detected ({size_mb:.1f}MB). Attempting compression to 32k bitrate..."
            )
            compressed = self._compress_audio(input_path, job_id)
            if compressed:
                temp_paths.append(compressed)
                return compressed, temp_paths
            print("Compression skipped (no FFmpeg). Using original audio.")

        if size_mb < self.max_size_mb and compress:
            print("File size is below chunk threshold. Skipping compression.")

        return input_path, temp_paths

    def _has_video_stream(self, file_path: Path) -> bool:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip() != ""
        except (subprocess.SubprocessError, FileNotFoundError):
            return file_path.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".flv"}

    def _compress_audio(self, file_path: Path, job_id: str) -> Path | None:
        ffmpeg_path = _find_ffmpeg()
        if not ffmpeg_path:
            return None

        compressed_path = self.workspace_dir / f"{job_id}_compressed_audio.ogg"
        try:
            subprocess.run(
                [
                    ffmpeg_path,
                    "-i",
                    str(file_path),
                    "-vn",
                    "-map_metadata",
                    "-1",
                    "-ac",
                    "1",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "32k",
                    "-application",
                    "voip",
                    str(compressed_path),
                    "-y",
                ],
                check=True,
                capture_output=True,
            )
            return compressed_path
        except subprocess.SubprocessError as exc:
            print(f"Compression failed: {exc}")
            return None

    def _extract_audio_from_video(self, file_path: Path, job_id: str) -> Path | None:
        ffmpeg_path = _find_ffmpeg()
        if not ffmpeg_path:
            return None

        extracted_path = self.workspace_dir / f"{job_id}_audio.mp3"
        try:
            subprocess.run(
                [
                    ffmpeg_path,
                    "-i",
                    str(file_path),
                    "-q:a",
                    "0",
                    "-map",
                    "a",
                    str(extracted_path),
                    "-y",
                ],
                check=True,
                capture_output=True,
            )
            return extracted_path
        except subprocess.SubprocessError as exc:
            print(f"Audio extraction failed: {exc}")
            return None

    def _cleanup_files(self, paths: list[Path]) -> None:
        for path in paths:
            if path and path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    print(f"Unable to remove temporary file {path}: {exc}")

    def _transcribe_audio(self, audio_path: Path, prompt: str) -> str:
        if self._needs_chunking(audio_path):
            print("Chunking audio for transcription...")
            audio = AudioSegment.from_file(audio_path)
            return split_and_transcribe_with_context(
                str(audio_path),
                self.api_config,
                self.max_size_mb,
                self.max_duration_seconds,
                audio,
                base_prompt=prompt,
            )

        print("Transcribing audio in a single request...")
        return self._single_pass_transcription(audio_path, prompt)

    def _needs_chunking(self, audio_path: Path) -> bool:
        size_mb = audio_path.stat().st_size / (1024 * 1024)
        return size_mb > self.max_size_mb

    def _single_pass_transcription(self, audio_path: Path, prompt: str) -> str:
        transcription_model = self.api_config.get("transcription_model", "whisper-1")
        use_azure = self.api_config.get("use_azure", False)
        api_key = self.api_config.get("api_key")

        with audio_path.open("rb") as audio_file:
            if use_azure:
                audio_client = self._build_azure_audio_client()
                response = audio_client.audio.transcriptions.create(
                    model=transcription_model,
                    file=audio_file,
                    prompt=prompt,
                )
            else:
                openai.api_key = api_key
                response = openai.audio.transcriptions.create(
                    model=transcription_model,
                    file=audio_file,
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


def post_process_transcript(raw_transcript, api_config):
    """Enhance transcript quality with GPT models."""

    model_name = api_config.get("model", "GPT model")
    print(f"Enhancing transcript quality with {model_name}...")
    prompt = f"""
    You are an expert transcript editor. Please improve the following raw transcript. The transcript could be in any language, e.g., English, Finnish, Swedish, etc.

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
        use_azure = api_config.get("use_azure", False)
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
                        "content": "You are an expert transcript editor who improves the quality, readability, and structure of transcribed conversations.",
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
                        "content": "You are an expert transcript editor who improves the quality, readability, and structure of transcribed conversations.",
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
):
    """Split audio into chunks and transcribe with rolling context."""

    use_azure = api_config.get("use_azure", False)
    api_key = api_config.get("api_key")
    transcription_model = api_config.get("transcription_model", "whisper-1")

    if audio is None:
        audio = AudioSegment.from_file(audio_path)

    duration_seconds = len(audio) / 1000
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    chunks_by_size = math.ceil(file_size_mb / (max_size_mb * 0.9))
    chunks_by_duration = math.ceil(duration_seconds / (max_duration_seconds * 0.95))
    num_chunks = max(1, max(chunks_by_size, chunks_by_duration))

    print(f"Splitting audio into {num_chunks} chunks based on size and duration")

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

            chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
            chunk_duration = len(chunk) / 1000
            print(f"Chunk {i + 1}/{num_chunks}: {chunk_size_mb:.2f}MB, {chunk_duration:.2f}s")

            start_time = format_timestamp(start_ms / 1000)
            end_time = format_timestamp(end_ms / 1000)
            chunk_header = f"\n[Timestamp: {start_time} - {end_time}]\n"

            if i == 0:
                prompt = base_prompt
            else:
                trimmed_context = context_text[-170:] if len(context_text) > 170 else context_text
                prompt = f"""The following is a continuation of a conversation. Here is the previous part of the transcript:

{trimmed_context}

Continue the transcription, maintaining speaker consistency and dialogue structure."""

            if use_azure:
                print("Using MS Azure endpoint for transcription")
            else:
                print("Using OpenAI direct endpoint for transcription")

            try:
                with open(chunk_path, "rb") as chunk_file:
                    if use_azure:
                        transcript_response = audio_client.audio.transcriptions.create(
                            model=transcription_model, file=chunk_file, prompt=prompt
                        )
                    else:
                        transcript_response = openai.audio.transcriptions.create(
                            model=transcription_model, file=chunk_file, prompt=prompt
                        )

                    chunk_transcript = transcript_response.text
                    transcripts.append(chunk_header + chunk_transcript)
                    context_text = chunk_transcript
                    time.sleep(1)
            except Exception as exc:
                print(f"Error transcribing chunk {i + 1}: {exc}")
                transcripts.append(f"[Transcription failed for segment {i + 1}]")
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


def _find_ffmpeg() -> str | None:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    possible_paths = [
        "ffmpeg",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        (
            "ffmpeg-2025-03-10-git-87e5da9067-essentials_build\\"
            "ffmpeg-2025-03-10-git-87e5da9067-essentials_build\\bin\\ffmpeg.exe"
        ),
    ]

    for path in possible_paths:
        try:
            subprocess.run([path, "-version"], capture_output=True, check=True)
            return path
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    return None
