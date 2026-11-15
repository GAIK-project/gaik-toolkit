"""transcribe_audio: speech to text with the Transcriber, in a temporary working folder."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

from ._runtime import maybe_quiet, need
from .models import Transcript
from .settings import OperationSettings

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac")

# What the Transcriber writes between the parts of a recording it had to split.
_PART_HEADER = re.compile(r"\[Timestamp: \d+:\d+ - \d+:\d+\][ \t]*\n?")
_FAILED_PART = re.compile(r"\[Transcription failed for segment \d+\]")


def transcribe_audio(
    path: str | Path,
    *,
    language: str | None = None,
    context: str = "",
    settings: OperationSettings | None = None,
) -> Transcript:
    """Turn a recording into text with gaik's Transcriber (OpenAI or Azure OpenAI only).

    Args:
        path: A .wav, .mp3, .m4a, .mp4, .webm, .ogg or .flac file.
        language: The language of the recording, as a name or a code. The cloud models take
            no language setting, so it is told to the model in the prompt.
        context: Names and terms the recording is likely to hold; added to the prompt.

    A recording over 25 MB or 20 minutes is split, which needs ffmpeg on the PATH.

    Raises:
        FileNotFoundError: There is no such file.
        ValueError: Another file type, an empty file, or no speech in the recording.
        RuntimeError: Every part of the recording failed.
        ImportError: The transcriber's packages are not installed.
    """
    settings = settings or OperationSettings()
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError("file not found")
    if file.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError("unsupported audio type: use a wav, mp3, m4a, mp4, webm, ogg or flac file")
    if file.stat().st_size == 0:
        raise ValueError("the audio file is empty")

    language = (language or "").strip() or None
    prompt = context.strip()
    if language:
        prompt = f"{prompt}\nLanguage of the recording: {language}.".strip()

    with maybe_quiet(settings.quiet):
        config = settings.llm_config()
        try:
            from gaik.software_components.transcriber import Transcriber
        except ImportError as error:
            raise need("transcribe_audio", "pydub") from error
        # The Transcriber's default working folder is one in the current directory.
        work = tempfile.mkdtemp(prefix="gaik-transcribe-", dir=settings.work_dir)
        try:
            result = Transcriber(config, output_dir=work, language=language or "auto").transcribe(
                file, custom_context=prompt
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    raw = result.raw_transcript or ""
    failed = len(_FAILED_PART.findall(raw))
    text = _PART_HEADER.sub("", _FAILED_PART.sub("", raw))
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", text)).strip()
    if failed:
        # The Transcriber writes a line instead of raising when one part fails.
        logger.warning("Transcription lost %d part(s) of a recording", failed)
    if not text:
        if failed:
            raise RuntimeError("every part of the recording failed to transcribe")
        raise ValueError("no speech was found in the recording")
    return Transcript(
        text=text,
        duration_s=result.audio_duration_s,
        language=language,
        model=str(result.model_used or ""),
        failed_segments=failed,
    )
