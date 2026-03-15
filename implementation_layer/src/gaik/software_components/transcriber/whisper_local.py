import requests
import shutil
import subprocess
import time
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm", ".m4v"}


def is_video_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def extract_audio_from_video(video_path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required to extract audio from video files, but it was not found in PATH."
        )

    output_audio = video_path.with_name(f"{video_path.stem}_extracted.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_audio),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_msg = (result.stderr or "").strip()
        raise RuntimeError(f"Audio extraction failed for '{video_path.name}'. ffmpeg error: {stderr_msg}")

    return output_audio


def transcribe(
    audio_path,
    *,
    api_base: str,
    key: str,
    language: str = "auto",
    diarization: bool = False,
    speaker_count: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    initial_prompt: str | None = None,
):
    start_time = time.perf_counter()
    input_file = Path(audio_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Audio/Video file not found: {input_file}")

    upload_file = input_file
    temp_extracted_audio: Path | None = None
    if is_video_file(input_file):
        print(f"Detected video file: {input_file.name}")
        print("Extracting audio with ffmpeg...")
        upload_file = extract_audio_from_video(input_file)
        temp_extracted_audio = upload_file
        print(f"Audio extracted: {upload_file.name}")

    print(f"Sending: {upload_file.name} ...")

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
    segments = result.get("segments", [])

    if not diarization:
        plain_text = (result.get("text") or "").strip()
        if not plain_text and segments:
            plain_text = " ".join(seg.get("text", "").strip() for seg in segments if seg.get("text")).strip()
    elapsed_seconds = time.perf_counter() - start_time
    print(f"Time taken for transcription: {elapsed_seconds:.2f} seconds")

    if temp_extracted_audio is not None:
        temp_extracted_audio.unlink(missing_ok=True)

    return result

