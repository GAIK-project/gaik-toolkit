"""Source Normalizer Example

Converts the multi-source report generator's sample inputs to Markdown texts and saves
them to a folder. The offline example parses documents locally; the full example also
transcribes the recording and describes the sketch, which calls the API.

Usage:
    python source_normalizer_example.py          # offline only
    python source_normalizer_example.py --full   # also the recording and the image
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.llm import get_llm_config  # noqa: E402
from gaik.software_components.source_normalizer import (  # noqa: E402
    NormalizedSources,
    SourceNormalizer,
)

SAMPLES = (
    Path(__file__).parent.parent.parent
    / "software_modules"
    / "multi_source_report_generator"
    / "sample_inputs"
)
OUTPUT_DIR = Path(__file__).parent / "output"

DOCUMENTS = {
    "primary": [SAMPLES / "notes.txt"],
    "secondary": [SAMPLES / "deployment-freeze-policy.pdf", SAMPLES / "project-budget.xlsx"],
}


def offline_example() -> None:
    """Normalize the documents locally and reload the saved folder."""
    sources = SourceNormalizer().normalize(DOCUMENTS, progress_callback=print)
    paths = sources.save(OUTPUT_DIR / "offline")
    print(f"Saved: {sorted(p.name for p in paths.values())}")

    for source in NormalizedSources.load(OUTPUT_DIR / "offline").sources:
        print(f"\n--- {source.id} ({source.source_class}, {source.tool}) ---")
        print(source.text[:400])


def full_example() -> None:
    """Also transcribe the recording and describe the sketch (calls the API)."""
    config = get_llm_config()
    normalizer = SourceNormalizer(config)
    sources = normalizer.normalize(
        {
            "primary": [*DOCUMENTS["primary"], SAMPLES / "meeting_recording.mp3"],
            "secondary": [*DOCUMENTS["secondary"], SAMPLES / "sketch.png"],
        },
        progress_callback=print,
    )
    sources.save(OUTPUT_DIR / "full")
    print(sources.get("meeting_recording.mp3").text[:400])


if __name__ == "__main__":
    offline_example()
    if "--full" in sys.argv:
        full_example()
