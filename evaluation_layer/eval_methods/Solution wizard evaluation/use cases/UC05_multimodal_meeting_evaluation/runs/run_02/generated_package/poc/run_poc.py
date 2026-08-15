"""Proof of Concept: AI-Supported Meeting Record Generation

Custom / hybrid pipeline: Transcriber (whisper_local) + PyMuPDFParser -> Extractor -> LLMJudge.

Reads a fixed input bundle manifest (JSON) that references three files describing one
project meeting -- the meeting audio recording, the agenda PDF, and the participant
list JSON -- and produces a single structured MeetingRecord JSON, with every decision,
action item, unresolved issue, and conflict backed by a pipe-delimited citation
(`file_name|start_timestamp|end_timestamp` for audio, `file_name|page_number` for the
agenda). review_status is always written as "pending_review" -- the actual
approve/reject decision happens outside this PoC (human_review step in the blueprint).

Usage:
    python run_poc.py --input <bundle_path>

Where <bundle_path> is a JSON manifest shaped like:
    {
      "meeting_id": "...",
      "inputs": {
        "meeting_audio": "input/meeting.wav",
        "agenda_pdf": "input/agenda.pdf",
        "participant_list": "input/participants.json"
      },
      "output": {"directory": "output", "filename": "meeting_record.json"}
    }
Paths in "inputs" are resolved relative to the bundle file's own directory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def load_requirements() -> str:
    req_path = Path(__file__).parent / "prompts" / "extraction_requirements.md"
    return req_path.read_text(encoding="utf-8") if req_path.exists() else ""


def _load_output_schema(schema_dir: Path):
    """Load the wizard-approved schema from schemas/output_schema.*.

    All schema files are named output_schema.* regardless of the blueprint class name.
    Returns (schema_class, requirements_obj).
    """
    import importlib.util

    schema_path = schema_dir / "output_schema.py"
    req_path = schema_dir / "output_schema_requirements.json"
    if not (schema_path.exists() and req_path.exists()):
        raise FileNotFoundError(
            f"Approved schema not found in {schema_dir}. Run generate_schema.py first."
        )

    data = json.loads(req_path.read_text(encoding="utf-8"))
    from gaik.software_components.extractor.schema import CompositeExtractionRequirements

    requirements = CompositeExtractionRequirements(**data["requirements"])

    spec = importlib.util.spec_from_file_location(data["model_name"], schema_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema_class = getattr(module, data["model_name"])
    return schema_class, requirements


def _format_timestamp(value) -> str:
    """Normalize a segment start/end value to HH:MM:SS.

    Local whisper servers commonly return start/end as float seconds; some already
    return a formatted string. Handle both.
    """
    if isinstance(value, str):
        # Already looks like HH:MM:SS (or HH:MM:SS.mmm) -- trim to whole seconds.
        parts = value.split(":")
        if len(parts) == 3:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(float(parts[2])):02d}"
        value = float(value)
    total = int(round(float(value)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _segments_to_labelled_text(segments: list[dict], file_name: str) -> str:
    """Render transcript segments as `[start - end] text` lines, prefixed with the
    exact audio file name so the extractor can produce correctly-formatted citations
    (`file_name|start_timestamp|end_timestamp`)."""
    lines = [f"AUDIO FILE: {file_name}", ""]
    for seg in segments or []:
        start = seg.get("start_timestamp", seg.get("start"))
        end = seg.get("end_timestamp", seg.get("end"))
        text = (seg.get("text") or "").strip()
        if start is None or end is None or not text:
            continue
        lines.append(f"[{_format_timestamp(start)} - {_format_timestamp(end)}] {text}")
    return "\n".join(lines)


def _load_participants(path: Path) -> tuple[str, list[dict]]:
    """Read the participant list JSON directly (no parsing component needed).

    Returns (text-for-prompt, ground-truth participant list) so the final output's
    `participants` field can be filled deterministically from the authoritative
    source instead of relying on the LLM to reproduce names/roles verbatim.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    participants = data.get("participants", [])
    lines = [f"PARTICIPANT LIST FILE: {path.name}", ""]
    for p in participants:
        extra = f" -- {p['meeting_responsibility']}" if p.get("meeting_responsibility") else ""
        lines.append(f"- {p.get('name')} ({p.get('role')}){extra}")
    ground_truth = [{"name": p.get("name"), "role": p.get("role")} for p in participants]
    return "\n".join(lines), ground_truth


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Supported Meeting Record Generation PoC")
    parser.add_argument(
        "--input", required=True, help="Path to the input bundle manifest JSON"
    )
    args = parser.parse_args()

    config = load_config()
    use_azure = config.get("use_azure", True)
    language = config.get("language", "en")
    models_cfg = config.get("models", {})
    temperature = models_cfg.get("temperature", 0.0)
    user_requirements = load_requirements()

    bundle_path = Path(args.input).resolve()
    if not bundle_path.exists():
        print(f"ERROR: input bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_dir = bundle_path.parent
    inputs = bundle.get("inputs", {})

    def _resolve(key: str) -> Path:
        if key not in inputs:
            print(f"ERROR: bundle is missing inputs.{key}", file=sys.stderr)
            sys.exit(1)
        return (bundle_dir / inputs[key]).resolve()

    meeting_audio_path = _resolve("meeting_audio")
    agenda_pdf_path = _resolve("agenda_pdf")
    participant_list_path = _resolve("participant_list")
    print(f"meeting_audio: {meeting_audio_path}")
    print(f"agenda_pdf: {agenda_pdf_path}")
    print(f"participant_list: {participant_list_path}")

    output_cfg = bundle.get("output", {})
    output_dir = Path(__file__).parent / output_cfg.get("directory", "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = output_cfg.get("filename", "meeting_record.json")
    schema_dir = Path(__file__).parent / "schemas"

    # =======================================================================
    # Step: transcribe_meeting (Transcriber, whisper_local -- timestamps required
    # for audio citations; hosted models return plain text only)
    # =======================================================================
    print("\n[1/3] Transcribing meeting recording (whisper_local)...")
    local_api_base = os.environ.get("LOCAL_TRANSCRIBER_API_BASE")
    local_api_key = os.environ.get("LOCAL_TRANSCRIBER_API_KEY")
    if not local_api_base:
        print(
            "ERROR: LOCAL_TRANSCRIBER_API_BASE is not set. whisper_local transcription "
            "requires a self-hosted Whisper endpoint (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)

    from gaik.software_components.transcriber import Transcriber

    transcriber = Transcriber(
        api_config={},
        transcription_model="whisper_local",
        language=language,
        diarization=False,
        local_api_base=local_api_base,
        local_api_key=local_api_key,
    )
    tr = transcriber.transcribe(str(meeting_audio_path))
    segments = tr.segments or []
    if segments:
        transcript_text = _segments_to_labelled_text(segments, meeting_audio_path.name)
    else:
        print(
            "WARNING: transcriber returned no segments -- audio citations will be "
            "degraded (no per-statement timestamps available).",
            file=sys.stderr,
        )
        transcript_text = (
            f"AUDIO FILE: {meeting_audio_path.name}\n\n"
            f"{tr.enhanced_transcript or tr.raw_transcript}"
        )
    print(f"    {len(segments)} segments, {len(transcript_text)} chars")

    # =======================================================================
    # Step: parse_agenda (PyMuPDFParser, use_markdown=False -- the only free/local
    # way to get file_name|page_number citations from a text-layer PDF)
    # =======================================================================
    print("\n[2/3] Parsing agenda PDF (page-level citations)...")
    from gaik.software_components.parsers import PyMuPDFParser

    pdf_parser = PyMuPDFParser()
    pdf_result = pdf_parser.parse_document(str(agenda_pdf_path), use_markdown=False)
    parsed_agenda_text = (
        f"AGENDA FILE: {agenda_pdf_path.name}\n\n{pdf_result['text_content']}"
    )
    print(f"    {pdf_result.get('word_count')} words, {pdf_result.get('content_length')} chars")

    # ----- Load participant list directly (structured data, no parsing needed) -----
    participant_text, participants_ground_truth = _load_participants(participant_list_path)

    # =======================================================================
    # Step: extract_meeting_record (Extractor / DataExtractor)
    # =======================================================================
    print("\n[3/3] Extracting structured meeting record...")
    from gaik.software_components.extractor import DataExtractor, get_openai_config

    extractor_config = get_openai_config(use_azure=use_azure)
    extractor = DataExtractor(
        config=extractor_config,
        model=models_cfg.get("extraction"),
        temperature=temperature,
    )
    schema_class, requirements = _load_output_schema(schema_dir)

    source_text = f"{transcript_text}\n\n{parsed_agenda_text}\n\n{participant_text}"

    results = extractor.extract(
        extraction_model=schema_class,
        requirements=requirements,
        user_requirements=user_requirements,
        documents=[source_text],
    )
    extracted_fields = results[0] if results else {}

    # ----- Deterministic corrections: prefer authoritative source data over LLM
    # transcription for fields we already know exactly, rather than trusting the
    # model to reproduce them verbatim. -----
    if bundle.get("meeting_id"):
        extracted_fields["meeting_id"] = bundle["meeting_id"]
    if participants_ground_truth:
        extracted_fields["participants"] = participants_ground_truth
    extracted_fields["review_status"] = "pending_review"

    # ----- Save output -----
    output_path = output_dir / output_filename
    output_path.write_text(
        json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\nResult written to: {output_path}")
    print(json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str))

    # =======================================================================
    # Step: validate_meeting_record (LLMJudge hallucination pre-screen)
    # =======================================================================
    print("\nRunning LLMJudge hallucination detection...")
    try:
        from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge

        judge = LLMJudge(model_provider="azure" if use_azure else "openai", use_azure=use_azure)
        report = judge.detect_hallucinations(source_text=source_text, extracted=extracted_fields)
        if report.flags:
            print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
            for flag in report.flags:
                print(f"  field={flag.field}  value={flag.value}  reason={flag.reason}")
        else:
            print("Hallucination check passed -- all fields are grounded in the source.")
        validation_result = {
            "hallucination_flags": [
                {
                    "field": f.field,
                    "value": f.value,
                    "severity": str(f.severity),
                    "reason": f.reason,
                }
                for f in report.flags
            ],
            "passed": len(report.flags) == 0,
        }
        (output_dir / "validation.json").write_text(
            json.dumps(validation_result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except ImportError:
        print("LLMJudge skipped: gaik[llm-judge] not installed.")
    except Exception as exc:
        print(f"LLMJudge warning: {exc}")

    # ----- Step: human_review (human review -- NOT executed in this PoC) -----
    # In production, the project manager approves/rejects meeting_record_json to
    # produce approved_meeting_record. This PoC stops at review_status=pending_review.


if __name__ == "__main__":
    main()
