"""Minimal example for running the Transcriber class on a single file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add GAIK package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.transcriber import Transcriber, get_openai_config


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
        enhanced_transcript=True,
    )

    result = transcriber.transcribe(
        file_path=args.audio_file,
        custom_context=args.context,
    )

    saved_paths = result.save(args.output_dir)

    print("\nTranscription finished!")
    raw_path = saved_paths.get("raw")
    enhanced_path = saved_paths.get("enhanced")
    if raw_path:
        print(f"Raw transcript saved to: {raw_path}")
    if enhanced_path:
        print(f"Enhanced transcript saved to: {enhanced_path}")
    elif enhanced_path is None:
        print("Enhanced transcript not available (enhancement disabled).")


if __name__ == "__main__":
    main()


