"""Example for local transcription model usage with Transcriber.

Edit the configuration values below and run the script directly.
This example keeps transcript error fixing disabled.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add GAIK package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.transcriber import Transcriber, get_openai_config

# ------------------------------------------------------------------
# Configure these values before running
# ------------------------------------------------------------------
AUDIO_FILE = Path("Sample.m4a")

def main() -> None:
    # API config is still required for optional transcript error fixing.
    config = get_openai_config(use_azure=True)

    transcriber = Transcriber(
        api_config=config,  # OpenAI/Azure config
        output_dir=".",  
        enhanced_transcript=True,  # Two-pass transcript correction
        transcription_model="whisper_local",  # Force local transcription backend
        local_api_base="http://YOUR_ADDRESS:8080",  # Local whisper base URL
        local_api_key="YOUR_KEY",  # API key sent to local whisper service
        language="fi",  # Language code. "auto" for detection. "fi" for Finnish.
        diarization=False,  # Enable/disable speaker diarization
        speaker_count=None,  # Exact speaker count if known
        min_speakers=None,  # Minimum speakers for diarization range
        max_speakers=None,  # Maximum speakers for diarization range
        initial_prompt=None,  # Optional prompt hint for the local transcriber
        enhanced_transcript_instructions=""
    )

    result = transcriber.transcribe(file_path=AUDIO_FILE)

    print("\nTranscription finished!")
    print("\n--- Raw Transcript ---\n")
    print(result.raw_transcript)

    if result.enhanced_transcript is not None:
        print("\n--- Corrected Transcript ---\n")
        print(result.enhanced_transcript)
    else:
        print("\nCorrected transcript not available (error fixing disabled).")


if __name__ == "__main__":
    main()


