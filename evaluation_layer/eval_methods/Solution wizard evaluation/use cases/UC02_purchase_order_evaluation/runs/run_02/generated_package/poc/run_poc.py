"""Proof of Concept: Purchase Order ERP Record Extraction

Pipeline: VisionExtractor -> LLMJudge -> (human review in production)

Usage:
    python run_poc.py
    python run_poc.py --input path/to/purchase_order.pdf
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


# ---------------------------------------------------------------------------
# Helpers
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

    Returns (schema_class, requirements_obj) on success, (None, None) otherwise.
    """
    import importlib.util
    import json as _json

    schema_path = schema_dir / "output_schema.py"
    req_path    = schema_dir / "output_schema_requirements.json"
    hash_path   = schema_dir / "output_schema.hash"

    if not (schema_path.exists() and req_path.exists()):
        print("No saved schema found -- VisionExtractor will generate from extraction_requirements.md.")
        return None, None

    # If requirements prompt has changed, force regeneration.
    if hash_path.exists():
        current_hash = _requirements_hash()
        if current_hash and hash_path.read_text().strip() != current_hash:
            print("extraction_requirements.md changed -- schema will be regenerated.")
            return None, None

    try:
        data = _json.loads(req_path.read_text(encoding="utf-8"))
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements
        requirements = CompositeExtractionRequirements(**data["requirements"])
        spec = importlib.util.spec_from_file_location(data["model_name"], schema_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema_class = getattr(module, data["model_name"])
        print("Using wizard-approved schema (requirements unchanged).")
        return schema_class, requirements
    except Exception as exc:
        print(f"WARNING: could not load saved schema ({exc}) -- VisionExtractor will generate schema.")
        return None, None


def _extract_pdf_text(pdf_path: Path) -> str:
    """Attempt to extract the text layer from a PDF for LLMJudge grounding.

    Returns an empty string for scanned PDFs or when PyMuPDF is unavailable.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if not text.strip():
            print("NOTE: No text layer found (scanned PDF); LLMJudge will assess "
                  "consistency of extracted fields internally.")
        return text
    except ImportError:
        print("NOTE: PyMuPDF not installed; PDF text extraction unavailable "
              "(install with: pip install pymupdf).")
        return ""
    except Exception as exc:
        print(f"NOTE: Could not extract PDF text ({exc}).")
        return ""


def _compare_with_fixture(result: dict, fixtures_dir: Path) -> None:
    """Semantic comparison with fixtures/expected_erp_record.json (PoC goal)."""
    fixture_path = fixtures_dir / "expected_erp_record.json"
    if not fixture_path.exists():
        print(f"\nNo fixture found at {fixture_path} -- skipping comparison.")
        print("To enable: place your expected_erp_record.json in the fixtures/ directory.")
        return

    expected = json.loads(fixture_path.read_text(encoding="utf-8"))
    print("\n--- Semantic comparison with fixtures/expected_erp_record.json ---")

    def _compare_value(key, exp, got):
        exp_s = str(exp).strip() if exp is not None else "null"
        got_s = str(got).strip() if got is not None else "null"
        match = exp_s == got_s
        status = "OK " if match else "DIFF"
        print(f"  [{status}] {key}: expected={exp_s!r}  got={got_s!r}")
        return match

    all_ok = True
    # Header fields
    for field in ("purchase_order_number", "delivery_date", "delivery_address", "vendor_number"):
        ok = _compare_value(field, expected.get(field), result.get(field))
        all_ok = all_ok and ok

    # Line items
    exp_items = expected.get("line_items", [])
    got_items = result.get("line_items", [])
    print(f"  line_items count: expected={len(exp_items)}  got={len(got_items)}")
    all_ok = all_ok and len(exp_items) == len(got_items)
    for i, (exp_item, got_item) in enumerate(zip(exp_items, got_items)):
        for field in exp_item:
            ok = _compare_value(f"line_items[{i}].{field}", exp_item.get(field), got_item.get(field))
            all_ok = all_ok and ok

    print("  Overall:", "PASS" if all_ok else "DIFFERENCES FOUND -- review output above")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Purchase Order ERP Record Extraction PoC")
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Path to a specific purchase order PDF (default: first PDF in sample_input/)"
    )
    args = parser.parse_args()

    config = load_config()
    use_azure = config.get("use_azure", True)
    user_requirements = load_requirements()

    poc_dir = Path(__file__).parent
    sample_dir = poc_dir / config.get("paths", {}).get("sample_input", "sample_input")
    output_dir = poc_dir / config.get("paths", {}).get("output", "output")
    schema_dir = poc_dir / "schemas"
    fixtures_dir = poc_dir.parent / "fixtures"

    sample_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----- Step: upload_po -- locate the input PDF -----
    if args.input:
        source_pdf_path = args.input.resolve()
        if not source_pdf_path.exists():
            print(f"ERROR: Input file not found: {source_pdf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        source_pdf_path = _find_input(sample_dir, (".pdf",))
    print(f"Input: {source_pdf_path}")

    # Contract variables
    extracted_fields = None
    source_text = ""

    # ----- Step: extract_po_fields (VisionExtractor) -----
    from gaik.software_components.vision_extractor import VisionExtractor

    schema_class, requirements = _load_output_schema(schema_dir)

    extractor = VisionExtractor(
        model_provider="openai",
        use_azure=use_azure,
        include_verification=True,
        merge_table=True,
        additional_instructions=(
            "Preserve all leading zeros in item numbers, article codes, and vendor numbers "
            "exactly as printed. Article codes are case-sensitive — do not normalize case or "
            "punctuation. Normalize all dates to DD/MM/YYYY format. "
            "product_form must be exactly one of: Flat, round, rectangular bar. "
            "For absent optional fields output null, never an empty string. "
            "Merge line-item rows split across page breaks into a single entry."
        ),
    )

    print("Extracting PO fields with VisionExtractor...")
    vr = extractor.extract(
        file_paths=[source_pdf_path],
        user_requirements=user_requirements,
        extraction_model=schema_class if schema_class else None,
        requirements=requirements if requirements else None,
    )
    erp_record_json = vr.data
    extracted_fields = erp_record_json
    print(f"Extraction complete: {vr.documents_processed} document(s) processed.")
    if vr.usage:
        print(f"Usage: {vr.usage.total_tokens} tokens  |  Cost: ${vr.usage.cost_usd:.6f}")

    # Source text for LLMJudge grounding (text layer of PDF if available)
    source_text = _extract_pdf_text(source_pdf_path)

    # ----- Save extracted output -----
    if extracted_fields is not None:
        result_path = output_dir / "result.json"
        result_path.write_text(
            json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"\nResult written to: {result_path}")
        print(json.dumps(extracted_fields, indent=2, ensure_ascii=False, default=str))
    else:
        print("\nERROR: extracted_fields is None -- extraction failed.", file=sys.stderr)
        sys.exit(1)

    # ----- Step: validate_extraction (LLMJudge) -----
    # Pre-screens the extracted record for hallucinations before human review.
    if extracted_fields is not None and source_text:
        print("\nRunning LLMJudge hallucination detection...")
        try:
            from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
            judge = _LLMJudge(model_provider="azure", use_azure=use_azure)
            extracted_for_judge = extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(
                source_text=source_text,
                extracted=extracted_for_judge,
            )
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
                json.dumps(validation_result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Validation report written to: {output_dir / 'validation.json'}")
        except ImportError:
            print("LLMJudge skipped: gaik[llm-judge] not installed.")
        except Exception as exc:
            print(f"LLMJudge warning: {exc}")
    else:
        print("\nLLMJudge skipped: no text layer available for grounding "
              "(scanned PDF or PyMuPDF not installed).")

    # ----- Step: notify_reviewer (CLI output) -----
    # In production: deliver result.json to reviewer via the ERP workflow system.
    # In PoC: the saved result.json and console output serve as the review artefact.
    print("\n--- Record ready for reviewer verification ---")
    print("Approved JSON may be transferred to ERP. Unreviewed records must NOT be transferred.")

    # ----- Step: reviewer_approves (human review -- not executed in PoC) -----
    # A procurement or order-processing reviewer verifies the record before transfer.
    # This step is performed manually outside the PoC pipeline.

    # ----- Semantic comparison with fixture (PoC goal) -----
    if isinstance(extracted_fields, dict):
        _compare_with_fixture(extracted_fields, fixtures_dir)

    print("\nPoC complete.")


if __name__ == "__main__":
    main()
