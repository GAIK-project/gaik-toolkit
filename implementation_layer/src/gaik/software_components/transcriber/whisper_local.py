import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

import requests

from gaik.software_components.endpoints import check_endpoint
from gaik.software_components.input_limits import media_input_args

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".m4v"}

# Longest an ffmpeg audio extraction may run before it is stopped.
FFMPEG_TIMEOUT_SECONDS = 1800


def is_video_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def extract_audio_from_video(
    video_path: Path,
    output_dir: Path | None = None,
    *,
    timeout: float = FFMPEG_TIMEOUT_SECONDS,
) -> Path:
    """Extract a mono 16 kHz WAV from a video file and return its path.

    The WAV is written into ``output_dir`` when one is given, otherwise beside
    the video. The caller removes it. ffmpeg is stopped after ``timeout``
    seconds and a :class:`RuntimeError` is raised.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required to extract audio from video files, but it was not found in PATH."
        )

    output_name = f"{video_path.stem}_extracted.wav"
    output_audio = output_dir / output_name if output_dir else video_path.with_name(output_name)
    cmd = [
        "ffmpeg",
        "-y",
        *media_input_args(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_audio),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output_audio.unlink(missing_ok=True)
        raise RuntimeError(
            f"Audio extraction for '{video_path.name}' took longer than {timeout:.0f} s."
        ) from exc
    if result.returncode != 0:
        stderr_msg = (result.stderr or "").strip()
        raise RuntimeError(
            f"Audio extraction failed for '{video_path.name}'. ffmpeg error: {stderr_msg}"
        )

    return output_audio


def transcribe(
    audio_path,
    *,
    api_base: str,
    key: str,
    allowed_endpoint_hosts: str | Sequence[str] | None = None,
    language: str = "auto",
    diarization: bool = False,
    speaker_count: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    initial_prompt: str | None = None,
):
    # The audio and the key go to api_base: the LOCAL_TRANSCRIBER_API_BASE address,
    # this machine, or an allowed host (see gaik.software_components.endpoints).
    check_endpoint(
        api_base, provider="whisper_local", allowed_hosts=allowed_endpoint_hosts, what="api_base"
    )
    start_time = time.perf_counter()
    input_file = Path(audio_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Audio/Video file not found: {input_file}")

    upload_file = input_file
    # Extracted audio lives in a directory of its own, removed whether the
    # transcription succeeds, fails or is cancelled.
    temp_dir: str | None = None
    try:
        if is_video_file(input_file):
            print(f"Detected a video file ({input_file.suffix.lower()})")
            print("Extracting audio with ffmpeg...")
            temp_dir = tempfile.mkdtemp(prefix="gaik_whisper_local_")
            upload_file = extract_audio_from_video(input_file, Path(temp_dir))
            print("Audio extracted")

        print(f"Sending the audio ({upload_file.suffix.lower()}) ...")

        # Health check
        r = requests.get(f"{api_base}/health", timeout=30)
        r.raise_for_status()
        print(f"Server OK - {r.json()}")

        # Send transcription request
        with open(upload_file, "rb") as f:
            payload = {
                "language": language,
                "diarization": diarization,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
                "speaker_count": speaker_count,
                "initial_prompt": initial_prompt,
                "include_words": True,
            }
            files = {"file": (upload_file.name, f)}
            print("Transcribing... (this may take a while)")
            r = requests.post(
                f"{api_base}/transcribe",
                data=payload,
                files=files,
                headers={"key": key},
                timeout=60 * 30,
            )
            r.raise_for_status()

        result = r.json()
        elapsed_seconds = time.perf_counter() - start_time
        print(f"Time taken for transcription: {elapsed_seconds:.2f} seconds")

        return result
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
