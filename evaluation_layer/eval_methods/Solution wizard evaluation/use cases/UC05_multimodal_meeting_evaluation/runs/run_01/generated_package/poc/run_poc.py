"""Proof of Concept: AI-Assisted Meeting Record Generator

Custom / hybrid pipeline: meeting audio + agenda PDF + participant list (JSON)
-> structured, evidence-cited MeetingRecord JSON.

Reads a frozen runtime bundle manifest (e.g. fixtures/poc_input_bundle.json) of the form:

    {
      "inputs": {
        "meeting_audio": "input/<name>.wav",
        "agenda_pdf": "input/<name>.pdf",
        "participant_list": "input/<name>.json"
      },
      "output": {"directory": "output", "filename": "meeting_record.json", "format": "json"}
    }

All paths inside the manifest are resolved relative to the manifest's own directory.

CONTRACT (required for the validation block to run):
  - Assign `extracted_fields`  (dict or list[dict]) -- the structured output, if any.
  - Assign `source_text`       (str)                -- the grounding text the output
                                                       is validated against (transcript,
                                                       parsed document, etc.).

Usage:
    python run_poc.py --input <path-to-bundle-manifest.json>
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from gaik.software_components.parsers import PyMuPDFParser


# ---------------------------------------------------------------------------
# Helpers (carried over from the module templates -- do not re-derive)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def load_requirements() -> str:
    req_path = Path(__file__).parent / "prompts" / "extraction_requirements.md"
    return req_path.read_text(encoding="utf-8") if req_path.exists() else ""


def _requirements_hash() -> str:
    import hashlib
    req_path = Path(__file__).parent / "prompts" / "extraction_requirements.md"
    if not req_path.exists():
        return ""
    return hashlib.sha256(req_path.read_bytes()).hexdigest()


def _load_output_schema(schema_dir: Path):
    """Load the wizard-approved schema from schemas/output_schema.*.

    The wizard pre-generates these files via generate_schema.py; the PoC should
    reuse them on the first run and only call SchemaGenerator when they are absent
    or the requirements prompt has changed.

    Returns (schema_class, requirements_obj) on success, (None, None) otherwise.
    All schema files are named output_schema.* regardless of the blueprint class name.
    """
    import importlib.util, json as _json
    schema_path = schema_dir / "output_schema.py"
    req_path    = schema_dir / "output_schema_requirements.json"
    hash_path   = schema_dir / "output_schema.hash"

    if not (schema_path.exists() and req_path.exists()):
        print("No saved schema found -- will generate from extraction_requirements.md.")
        return None, None

    # If requirements prompt has changed, force regeneration.
    if hash_path.exists():
        current_hash = _requirements_hash()
        if current_hash and hash_path.read_text().strip() != current_hash:
            print("extraction_requirements.md changed -- schema will be regenerated.")
            return None, None

    try:
        data = _json.loads(req_path.read_text(encoding="utf-8"))
        from gaik.software_components.extractor.schema import (
            ExtractionRequirements,
            CompositeExtractionRequirements,
        )
        raw_requirements = data["requirements"]
        # This schema uses a parent-with-nested-list structure -> Composite payload.
        if "structure_type" in raw_requirements:
            requirements = CompositeExtractionRequirements(**raw_requirements)
        else:
            requirements = ExtractionRequirements(**raw_requirements)
        spec = importlib.util.spec_from_file_location(data["model_name"], schema_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema_class = getattr(module, data["model_name"])
        print("Using approved schema (requirements unchanged).")
        return schema_class, requirements
    except Exception as exc:
        print(f"WARNING: could not load saved schema ({exc}) -- will regenerate.")
        return None, None


def _save_output_schema(schema_gen, schema, requirements, schema_dir: Path) -> None:
    """Persist a freshly generated schema to schemas/output_schema.* and update the hash."""
    import json as _json, inspect as _inspect
    schema_dir.mkdir(parents=True, exist_ok=True)
    src = _inspect.getsource(schema)
    (schema_dir / "output_schema.py").write_text(src, encoding="utf-8")
    req_payload = {
        "model_name": schema.__name__,
        "requirements": requirements.model_dump() if hasattr(requirements, "model_dump") else vars(requirements),
    }
    (schema_dir / "output_schema_requirements.json").write_text(
        _json.dumps(req_payload, indent=2), encoding="utf-8"
    )
    (schema_dir / "output_schema.hash").write_text(_requirements_hash())


def _fmt_ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS, matching the citation_formats convention."""
    total = int(round(seconds or 0.0))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_audio_transcript_text(file_name: str, segments: list[dict], fallback_text: str) -> str:
    """Render transcript segments with per-segment timestamps and the source file
    name, so the extractor can build file_name|start_timestamp|end_timestamp citations."""
    lines = [f"AUDIO SOURCE FILE: {file_name}", ""]
    if segments:
        for seg in segments:
            start = _fmt_ts(seg.get("start"))
            end = _fmt_ts(seg.get("end"))
            text = (seg.get("text") or "").strip()
            if text:
                lines.append(f"[{start} - {end}] {text}")
    else:
        lines.append(fallback_text or "")
    return "\n".join(lines)


def _build_agenda_text(file_name: str, text_content: str) -> str:
    """Prefix the parsed agenda (with its '=== PAGE N ===' markers from
    use_markdown=False) with the source file name, so the extractor can build
    file_name|page_number citations."""
    return f"AGENDA SOURCE FILE: {file_name}\n\n{text_content}"


def _build_participant_list_text(file_name: str, data) -> str:
    return f"PARTICIPANT LIST FILE: {file_name}\n\n{json.dumps(data, indent=2, ensure_ascii=False)}"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Assisted Meeting Record Generator PoC")
    parser.add_argument(
        "--input", required=True,
        help="Path to the meeting bundle manifest (e.g. fixtures/poc_input_bundle.json)",
    )
    args = parser.parse_args()

    config = load_config()
    use_azure = config.get("use_azure", True)
    language = config.get("language", "en")
    user_requirements = load_requirements()

    # ----- Resolve the bundle manifest and its three input files -----
    bundle_path = Path(args.input).expanduser().resolve()
    if not bundle_path.exists():
        print(f"ERROR: bundle manifest not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_root = bundle_path.parent
    bundle_inputs = bundle.get("inputs", {})

    try:
        meeting_audio_path = (bundle_root / bundle_inputs["meeting_audio"]).resolve()
        agenda_document_path = (bundle_root / bundle_inputs["agenda_pdf"]).resolve()
        participant_list_path = (bundle_root / bundle_inputs["participant_list"]).resolve()
    except KeyError as exc:
        print(f"ERROR: bundle manifest is missing input key: {exc}", file=sys.stderr)
        sys.exit(1)

    for path_, label in (
        (meeting_audio_path, "meeting_audio"),
        (agenda_document_path, "agenda_pdf"),
        (participant_list_path, "participant_list"),
    ):
        if not path_.exists():
            print(f"ERROR: {label} file not found: {path_}", file=sys.stderr)
            sys.exit(1)

    print(f"meeting_audio:    {meeting_audio_path}")
    print(f"agenda_document:  {agenda_document_path}")
    print(f"participant_list: {participant_list_path}")

    output_spec = bundle.get("output", {})
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_spec.get("filename", "meeting_record.json")

    schema_dir = Path(__file__).parent / "schemas"

    # ----- Contract variables (assigned below) -----
    extracted_fields = None   # dict | list[dict] -- the structured output (if any)
    source_text = ""          # str -- grounding text for hallucination validation (if any)

    # ===========================================================================
    # PIPELINE WIRING
    # ===========================================================================

    # ----- Step: provide_meeting_bundle (user input) -----
    # produces: meeting_audio, agenda_document, participant_list (resolved above from --input manifest)

    # ----- Step: transcribe_audio (Transcriber, whisper_local, diarization=False) -----
    # inputs: meeting_audio -> outputs: audio_transcript
    from gaik.software_components.transcriber import Transcriber, get_openai_config as get_transcriber_config

    local_api_base = os.environ.get("LOCAL_TRANSCRIBER_API_BASE")
    local_api_key = os.environ.get("LOCAL_TRANSCRIBER_API_KEY")
    if not local_api_base or not local_api_key:
        print(
            "ERROR: LOCAL_TRANSCRIBER_API_BASE and LOCAL_TRANSCRIBER_API_KEY must be set "
            "(in .env) to reach the self-hosted Whisper endpoint.",
            file=sys.stderr,
        )
        sys.exit(1)

    transcriber = Transcriber(
        api_config=get_transcriber_config(use_azure=use_azure),
        transcription_model="whisper_local",
        language=language,
        diarization=False,
        local_api_base=local_api_base,
        local_api_key=local_api_key,
    )
    tr = transcriber.transcribe(str(meeting_audio_path))
    segments = tr.segments or []
    audio_transcript = _build_audio_transcript_text(
        meeting_audio_path.name, segments, tr.enhanced_transcript or tr.raw_transcript
    )

    # ----- Step: parse_agenda (PyMuPDFParser, use_markdown=False for page citations) -----
    # inputs: agenda_document -> outputs: parsed_agenda
    pdf_parser = PyMuPDFParser()
    parsed_res = pdf_parser.parse_document(str(agenda_document_path), use_markdown=False)
    parsed_agenda = _build_agenda_text(agenda_document_path.name, parsed_res["text_content"])

    # ----- Load participant_list (user-upload artifact; passed as extraction context) -----
    participant_list_data = json.loads(participant_list_path.read_text(encoding="utf-8"))
    participant_list_text = _build_participant_list_text(participant_list_path.name, participant_list_data)

    # ----- Step: extract_meeting_record (Extractor) -----
    # inputs: audio_transcript, parsed_agenda, participant_list -> outputs: meeting_record_json
    from gaik.software_components.extractor import SchemaGenerator, DataExtractor, get_openai_config

    extraction_config = get_openai_config(use_azure=use_azure)
    schema_gen = SchemaGenerator(config=extraction_config)
    extractor = DataExtractor(config=extraction_config)

    schema, requirements = _load_output_schema(schema_dir)
    if schema is None:
        schema = schema_gen.generate_schema(user_requirements=user_requirements)
        requirements = schema_gen.item_requirements
        schema_dir.mkdir(parents=True, exist_ok=True)
        _save_output_schema(schema_gen, schema, requirements, schema_dir)

    source_text = f"{audio_transcript}\n\n{parsed_agenda}\n\n{participant_list_text}"

    extraction_results = extractor.extract(
        extraction_model=schema,
        requirements=requirements,
        user_requirements=user_requirements,
        documents=[source_text],
    )
    meeting_record_json = extraction_results[0] if extraction_results else None
    extracted_fields = meeting_record_json

    # ----- Step: human_review (human review -- NOT executed in PoC) -----
    # In production a reviewer approves: approved_meeting_record

    # ----- Save output -----
    if extracted_fields is not None:
        output_path.write_text(
            json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"\nResult written to: {output_path}")
        print(json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str))
    else:
        print("ERROR: extraction produced no result.", file=sys.stderr)
        sys.exit(1)

    # -- LLMJudge hallucination detection (from blueprint: human_review=yes) --
    # Contract: by this point the wiring above has assigned:
    #   extracted_fields  (dict or list[dict])  -- the structured output
    #   source_text       (str)                 -- the grounding text to validate against
    if extracted_fields is None or not source_text:
        print("LLMJudge skipped: pipeline not fully wired "
              "(need both 'extracted_fields' and 'source_text').")
    else:
        print("\nRunning LLMJudge hallucination detection...")
        try:
            from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
            judge = _LLMJudge(model_provider="azure", use_azure=use_azure)
            extracted_for_judge = extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(source_text=source_text, extracted=extracted_for_judge)
            if report.flags:
                print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
                for flag in report.flags:
                    print(f"  field={flag.field}  value={flag.value}  reason={flag.reason}")
            else:
                print("Hallucination check passed -- all fields are grounded in the source.")
            validation_result = {
                "hallucination_flags": [
                    {"field": f.field, "value": f.value, "severity": str(f.severity), "reason": f.reason}
                    for f in report.flags
                ],
                "passed": len(report.flags) == 0,
            }
            (output_dir / "validation.json").write_text(
                json.dumps(validation_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except ImportError:
            print("LLMJudge skipped: gaik[llm-judge] not installed.")
        except Exception as _judge_exc:
            print(f"LLMJudge warning: {_judge_exc}")


if __name__ == "__main__":
    main()
