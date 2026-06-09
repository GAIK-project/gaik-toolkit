"""Minimal example for running the Transcriber class on a single file with transcript error fixing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add GAIK package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.transcriber import Transcriber, get_openai_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe an audio/video file into text")
    parser.add_argument("audio_file", type=Path, help="Path to the input audio or video file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory where transcript files should be written",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Optional custom prompt/context passed to the transcription model",
    )
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Use public OpenAI instead of Azure (default is Azure)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = get_openai_config(use_azure=not args.openai)
    transcriber = Transcriber(
        api_config=config,
        output_dir=args.output_dir,
        enhanced_transcript=False,
        compress_audio=True
    )

    result = transcriber.transcribe(
        file_path=args.audio_file,
        custom_context=args.context,
    )

    saved_paths = result.save(args.output_dir)

    print("\nTranscription finished!")
    raw_path = saved_paths.get("raw")
    corrected_path = saved_paths.get("enhanced")
    if raw_path:
        print(f"Raw transcript saved to: {raw_path}")
    if corrected_path:
        print(f"Corrected transcript saved to: {corrected_path}")
    elif corrected_path is None:
        print("Corrected transcript not available (error fixing disabled).")


if __name__ == "__main__":
    main()
