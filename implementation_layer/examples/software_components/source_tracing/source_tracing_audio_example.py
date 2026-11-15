"""Source Tracing example: AudioToStructuredData, with evidence checked against the transcript.

The module transcribes the audio and extracts from the enhanced transcript when there is one,
otherwise from the raw one. ``transcript_used`` returns exactly the text it extracted from, so
the quotes are checked against the right one. A quote cannot be tied to a time in the
recording in this version: its position is in the transcript text.

This example uses the sample recording of the AudioToStructuredData module and a small
schema of its own, because that recording is not a purchase order.

    python source_tracing_audio_example.py

Needs: pip install "gaik[audio-to-structured-data,source-tracing]" and credentials (.env).
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

HERE = Path(__file__).parent
load_dotenv(HERE.parents[2] / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(HERE.parents[2] / "src"))

from gaik.software_components.extractor import ExtractionRequirements, FieldSpec  # noqa: E402
from gaik.software_components.source_tracing import SourceTracing, transcript_used  # noqa: E402
from gaik.software_modules.audio_to_structured_data import AudioToStructuredData  # noqa: E402
from po_schema import print_report  # noqa: E402

AUDIO = HERE.parent.parent / "software_modules" / "audio_to_structured_data" / "sample.mp3"

TASK = "Extract a short summary of what is said and the names of the people mentioned."


class Recording(BaseModel):
    summary: str | None = Field(None, description="A short summary of what is said")
    people: str | None = Field(None, description="Names of the people mentioned, comma separated")


REQUIREMENTS = ExtractionRequirements(
    use_case_name="recording",
    fields=[
        FieldSpec(field_name="summary", field_type="str", description="A short summary"),
        FieldSpec(field_name="people", field_type="str", description="Names of the people"),
    ],
)


def main() -> None:
    tracing = SourceTracing()
    task = tracing.augment(Recording, TASK, source="text")

    pipeline = AudioToStructuredData(use_azure=True)
    result = pipeline.run(
        file_path=AUDIO,
        user_requirements=task.prompt,
        schema=task.model,
        requirements=REQUIREMENTS,
    )

    data, report = tracing.check_text(result.extracted_fields, transcript_used(result))

    print("Extracted data (evidence removed):")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    print_report(report)


if __name__ == "__main__":
    main()
