"""
Example: extracts key structured fields from audios by dynamically building extraction models from user requiements
Software component: audio_to_structured_data
Workflow: input audio->transcribe->parse user requirement and build schema->extract key data
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.audio_to_structured_data import AudioToStructuredData  # noqa: E402


USER_REQUIREMENTS = """
    The task is to extract all required fields for a standard medical consultation summary
    from the transcript of a clinician’s dictated voice note after meeting with a patient.

    Output MUST follow the field structure below exactly.
    If the transcript does not mention a field, return an empty string ("").
    All extracted fields should be brief and factual, preferably not exceeding a short phrase.

    Extract the following fields exactly as they appear below:

    1. Patient Name
    2. Date of Birth (Format: dd.mm.yyyy)
    3. Consultation Date (Format: dd.mm.yyyy)
    4. Symptoms
    5. Symptom Duration
    6. Medical History
    7. Examinations Performed
    8. Clinical Findings
    9. Diagnosis
    10. Treatment Prescribed
    11. Follow-up Instructions
    12. Referrals
    13. Attachments
"""


def main() -> None:
    schema_dir = Path(__file__).parent / "schema"
    extract_options = {
        "save_json": False, #save extraction results
        "json_path": "extraction_results.json", #path of the extracted results
        "generate_schema": True,  # Set False to reuse an existing saved schema. If True, a new schema will be built and saved.
        "schema_name": "schema",  # Without .py; defaults to 'schema'
    }
    transcriber_ctor = {
        "output_dir": "./",
        "compress_audio": True, # (Optional) for compressing large audios (uses FFMPEG)
        "enhanced_transcript": False,
    }
    transcribe_options = {
        "custom_context": "",    # Optional extra prompt for transcription
        "use_case_name": "audio_to_structured_data",   # Optional label for logging
    }

    generate_schema = extract_options.pop("generate_schema", True) #whether a new schema is to be generated
    schema_name = extract_options.pop("schema_name", "schema") # Whether a schema name is given; if not, use default

    # Create the pipleine (transcription+schema generation+extraction)
    pipeline = AudioToStructuredData(use_azure=True)

    existing = None if generate_schema else pipeline.load_schema(schema_dir, schema_name)
    schema = requirements = None
    if existing:
        schema, requirements = existing

    # Run the pipeline
    result = pipeline.run(
        file_path=Path(r"sample.mp3"),
        user_requirements=USER_REQUIREMENTS,
        transcriber_ctor=transcriber_ctor,
        transcribe_options=transcribe_options,
        extractor_ctor={
            # Optional: override model or other DataExtractor ctor args;
            # "model": "gpt-5.2"
        },
        extract_options=extract_options,
        schema=schema,
        requirements=requirements,
    )

    # Save schema
    if result.schema and result.requirements and generate_schema:
        pipeline.save_schema(result.schema, result.requirements, schema_dir, schema_name)

    print("Transcription job id:", result.transcription.job_id)
    print("\nExtracted fields:\n")
    print(json.dumps(result.extracted_fields, indent=2, default=str))

    #The raw and/or enhanced transcripts are in result.transcription.raw_transcript and result.transcription.enhanced_transcript

if __name__ == "__main__":
    main()
