"""Proof of Concept: Purchase Order ERP Record Extraction

Custom / hybrid pipeline (agent-wired).

This blueprint uses a custom combination of components, so the wizard generated
a per-step skeleton instead of a fixed module pipeline. Each automated step below
carries the component's reference call pattern and the artifact variable names from
the blueprint -- fill in one call per labelled block.

CONTRACT (required for the validation block to run):
  - Assign `extracted_fields`  (dict or list[dict]) -- the structured output, if any.
  - Assign `source_text`       (str)                -- the grounding text the output
                                                       is validated against (transcript,
                                                       parsed document, etc.).
  Leave them as None / "" if the pipeline has no extraction/validation step.

Usage:
    python run_poc.py
    python run_poc.py --synthetic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

# Component imports for this pipeline:
from gaik.software_components.vision_extractor import VisionExtractor
from gaik.software_components.validators.llm_judge import LLMJudge


# ---------------------------------------------------------------------------
# Helpers (carried over from the module templates -- do not re-derive)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def load_requirements() -> str:
    req_path = Path(__file__).parent / "prompts" / "extraction_requirements.md"
    return req_path.read_text(encoding="utf-8") if req_path.exists() else ""


def _find_input(sample_dir: Path, exts: tuple) -> Path:
    files = [f for f in sample_dir.iterdir() if f.suffix.lower() in exts]
    if not files:
        print(f"ERROR: No input file with extensions {exts} found in {sample_dir}", file=sys.stderr)
        sys.exit(1)
    return sorted(files)[0]


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
        from gaik.software_components.extractor.schema import ExtractionRequirements
        requirements = ExtractionRequirements(**data["requirements"])
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
    # Write the Pydantic model source (mirrors generate_schema.py output format).
    src = _inspect.getsource(schema)
    (schema_dir / "output_schema.py").write_text(src, encoding="utf-8")
    # Write the requirements payload.
    req_payload = {
        "model_name": schema.__name__,
        "requirements": requirements.model_dump() if hasattr(requirements, "model_dump") else vars(requirements),
    }
    (schema_dir / "output_schema_requirements.json").write_text(
        _json.dumps(req_payload, indent=2), encoding="utf-8"
    )
    # Save the hash so subsequent runs skip regeneration.
    (schema_dir / "output_schema.hash").write_text(_requirements_hash())


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Purchase Order ERP Record Extraction PoC")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic/generated input")
    args = parser.parse_args()

    config = load_config()
    use_azure = config.get("use_azure", True)
    models = config.get("models", {})
    language = config.get("language", "en")
    user_requirements = load_requirements()

    sample_dir = Path(__file__).parent / config.get("paths", {}).get("sample_input", "sample_input")
    output_dir = Path(__file__).parent / config.get("paths", {}).get("output", "output")
    schema_dir = Path(__file__).parent / "schemas"
    sample_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----- Load inputs (one per user-upload artifact) -----
    # Load user-upload artifact: source_pdf (type=pdf)
    source_pdf_path = _find_input(sample_dir, (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".txt", ".md"))
    print(f'source_pdf: {source_pdf_path}')


    # ----- Contract variables (assign these in the wiring below) -----
    extracted_fields = None   # dict | list[dict] -- the structured output (if any)
    source_text = ""          # str -- grounding text for hallucination validation (if any)

    # ===========================================================================
    # PIPELINE WIRING -- fill one call per labelled step block below.
    # Variable names come from the blueprint artifacts and already chain together.
    # ===========================================================================

    # ----- Step: upload_po  (user input) -----
    # produces: source_pdf  (loaded from sample_input/, see loaders above)

    # ----- Step: extract_po_fields  (VisionExtractor) -----
    # inputs: source_pdf  ->  outputs: extracted_po_json
    print(f"\nExtracting PO fields from: {source_pdf_path}")
    _additional_instructions = (
        "Preserve all alphanumeric identifiers — article codes, item numbers, vendor numbers, "
        "and product codes — exactly as written in the document, including leading zeros. "
        "Do not reformat, normalise, or truncate them. "
        "Delivery dates must be captured in DD/MM/YYYY format. "
        "The product_form field must be one of exactly: Flat, round, rectangular bar. "
        "Set product_form to null when the product form cannot be determined with confidence. "
        "Do not merge distinct line items. "
        "When a table row is continued on the next page, capture all continued rows as "
        "separate line items under the same logical entry. "
        "Do not invent or infer any value not explicitly present in the source document."
    )
    extractor = VisionExtractor(
        model_provider="openai",
        use_azure=use_azure,
        include_verification=True,
        merge_table=True,
        additional_instructions=_additional_instructions,
    )
    vr = extractor.extract(
        file_paths=[source_pdf_path],
        user_requirements=user_requirements,
    )
    extracted_po_json = vr.data
    extracted_fields = extracted_po_json
    # VisionExtractor processes page images directly — there is no intermediate text
    # transcript to use as source_text. We pass the JSON representation so LLMJudge
    # can perform internal consistency and completeness checks (not full text grounding).
    source_text = json.dumps(extracted_po_json, indent=2, ensure_ascii=False, default=str)
    print(f"Extraction complete. Documents processed: {vr.documents_processed}")

    # ----- Step: notify_reviewer  () -----
    # inputs: extracted_po_json, validation_report, source_pdf  ->  outputs: (none)
    # (no reference card for  -- read its README/example_script_path)

    # ----- Step: reviewer_review  (human review -- NOT executed in PoC) -----
    # In production a reviewer approves: approved_po_json

    # ----- Step: notify_employee  () -----
    # inputs: (none)  ->  outputs: (none)
    # (no reference card for  -- read its README/example_script_path)

    # ----- Step: employee_correct  (user input) -----
    # produces: (none)  (loaded from sample_input/, see loaders above)


    # ----- Save output -----
    if extracted_fields is not None:
        (output_dir / "result.json").write_text(
            json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"\nResult written to: {output_dir / 'result.json'}")
        print(json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str))
    else:
        print("\nNOTE: extracted_fields is still None -- finish wiring the pipeline above.")

    _pdf_source = extracted_fields if extracted_fields is not None else (source_text or "")


    # -- LLMJudge hallucination detection (from blueprint) --
    # Contract: by this point your wiring MUST have assigned:
    #   extracted_fields  (dict or list[dict])  -- the structured output
    #   source_text       (str)                 -- the grounding text to validate against
    if extracted_fields is None or not source_text:
        print("LLMJudge skipped: pipeline not fully wired "
              "(need both 'extracted_fields' and 'source_text').")
    else:
        print("\nRunning LLMJudge hallucination detection...")
        try:
            from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
            judge = _LLMJudge(model_provider="openai", use_azure=use_azure)
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
