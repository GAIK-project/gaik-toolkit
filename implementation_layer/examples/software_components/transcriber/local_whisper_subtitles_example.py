"""Example: Transcribe audio/video and generate SRT/VTT subtitles.

Demonstrates:
1. Transcribe with local Whisper (returns segments with timestamps)
2. Generate SRT and WebVTT subtitle files
3. Chunk segments for semantic search embedding

Prerequisites:
    pip install gaik[all-cpu]

    # Set environment variables
    LOCAL_WHISPER_BASE=http://your-whisper-server:8080
    LOCAL_WHISPER_KEY=your-api-key
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.transcriber.srt_utils import (
    chunk_segments,
    segments_to_srt,
    segments_to_vtt,
)
from gaik.software_components.transcriber.whisper_local import transcribe

# ------------------------------------------------------------------
# Configure these values before running
# ------------------------------------------------------------------
AUDIO_FILE = Path("sample.mp3")
LOCAL_API_BASE = "http://your-whisper-server:8080"
LOCAL_API_KEY = "your-api-key"
LANGUAGE = "auto"  # "auto", "fi", "en", "sv", etc.


def main() -> None:
    # 1. Transcribe with local Whisper
    print("Transcribing...")
    result = transcribe(
        audio_path=AUDIO_FILE,
        api_base=LOCAL_API_BASE,
        key=LOCAL_API_KEY,
        language=LANGUAGE,
    )

    segments = result.get("segments", [])
    text = (result.get("text") or "").strip()
    print(f"Got {len(segments)} segments, {len(text)} chars\n")

    # 2. Generate SRT subtitles
    srt_content = segments_to_srt(segments)
    srt_path = Path("output.srt")
    srt_path.write_text(srt_content, encoding="utf-8")
    print(f"SRT saved to {srt_path}")
    print("First 500 chars of SRT:")
    print(srt_content[:500])
    print()

    # 3. Generate WebVTT subtitles
    vtt_content = segments_to_vtt(segments)
    vtt_path = Path("output.vtt")
    vtt_path.write_text(vtt_content, encoding="utf-8")
    print(f"VTT saved to {vtt_path}\n")

    # 4. Chunk segments for semantic search (30-60s groups)
    chunks = chunk_segments(segments, target_seconds=45)
    print(f"Chunked {len(segments)} segments into {len(chunks)} search chunks:")
    for i, chunk in enumerate(chunks[:5]):
        start = chunk.get("start", 0)
        end = chunk.get("end", 0)
        text_preview = chunk.get("text", "")[:80]
        print(f"  [{i + 1}] {start:.1f}s - {end:.1f}s: {text_preview}...")

    if len(chunks) > 5:
        print(f"  ... and {len(chunks) - 5} more chunks")


if __name__ == "__main__":
    main()
