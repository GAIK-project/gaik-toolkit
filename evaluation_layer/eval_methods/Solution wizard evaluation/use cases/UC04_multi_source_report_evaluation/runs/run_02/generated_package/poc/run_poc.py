"""Proof of Concept: Quarterly Supplier Performance Report Generator

Accepts a PoC input bundle JSON and synthesises the four source files into
a structured, evidence-grounded Markdown report with an evidence index.

Usage:
    python run_poc.py --input <path-to-poc_input_bundle.json>

Bundle format (all paths resolved relative to the bundle file):
    {
      "source_files":  ["<relative-path>", ...],
      "report_spec":   "<relative-path-to-report_spec.json>",
      "sample_report": "<relative-path-to-report_template.md>"
    }

Outputs (written to output/ relative to this script):
    output/report.md            -- draft Markdown report (pending manager approval)
    output/evidence_index.json  -- evidence index listing all source files processed
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

from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _deduplicate_headings(text: str) -> str:
    """Remove duplicate consecutive Markdown headings produced by agentic mode
    when sample_report_path contributes a skeleton heading and the section
    writer also opens with its own heading.

    Collapses patterns like:
        ## Executive Summary\\n\\n## Executive Summary
    to a single heading.  Repeated until stable.
    """
    import re
    pattern = re.compile(r'^(#{1,6} [^\n]+)\n[ \t]*\n\1\n', re.MULTILINE)
    prev: str | None = None
    while prev != text:
        prev = text
        text = pattern.sub(r'\1\n', text)
    return text


def load_bundle(bundle_path: Path) -> dict:
    """Load the PoC input bundle JSON."""
    try:
        return json.loads(bundle_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: Bundle file not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Bundle JSON is invalid: {exc}", file=sys.stderr)
        sys.exit(1)


def resolve_bundle_paths(
    bundle: dict, bundle_dir: Path
) -> tuple[list[Path], Path, Path | None]:
    """Resolve all paths in the bundle relative to the bundle file's directory.

    Returns (source_paths, report_spec_path, sample_report_path_or_None).
    """
    source_files = bundle.get("source_files", [])
    if not source_files:
        print("ERROR: bundle 'source_files' is empty or missing.", file=sys.stderr)
        sys.exit(1)

    source_paths: list[Path] = []
    for sf in source_files:
        p = (bundle_dir / sf).resolve()
        if not p.exists():
            print(f"ERROR: Source file not found: {p}", file=sys.stderr)
            sys.exit(1)
        source_paths.append(p)

    report_spec_rel = bundle.get("report_spec")
    if not report_spec_rel:
        print("ERROR: bundle missing 'report_spec' key.", file=sys.stderr)
        sys.exit(1)
    report_spec_path = (bundle_dir / report_spec_rel).resolve()
    if not report_spec_path.exists():
        print(f"ERROR: report_spec not found: {report_spec_path}", file=sys.stderr)
        sys.exit(1)

    sample_report_path: Path | None = None
    sample_rel = bundle.get("sample_report")
    if sample_rel:
        p = (bundle_dir / sample_rel).resolve()
        if p.exists():
            sample_report_path = p

    return source_paths, report_spec_path, sample_report_path


def load_report_spec(spec_path: Path) -> dict:
    """Load the report spec JSON (sections, title, description, language)."""
    try:
        return json.loads(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: report_spec not found: {spec_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: report_spec JSON is invalid: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quarterly Supplier Performance Report Generator PoC"
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="BUNDLE_JSON",
        help="Path to poc_input_bundle.json",
    )
    cli_args = parser.parse_args()

    bundle_path = Path(cli_args.input).resolve()
    if not bundle_path.exists():
        print(f"ERROR: Bundle file not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    # -- Config --
    config = load_config()
    use_azure: bool = config.get("use_azure", True)
    models: dict = config.get("models", {})
    extraction_model: str = models.get("extraction", "gpt-5.4")
    temperature: float = float(models.get("temperature", 1.0))
    reasoning_effort: str = models.get("reasoning_effort", "medium")

    output_dir = Path(__file__).parent / config.get("paths", {}).get("output", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # -- Resolve bundle --
    bundle_dir = bundle_path.parent
    bundle = load_bundle(bundle_path)
    source_paths, report_spec_path, sample_report_path = resolve_bundle_paths(
        bundle, bundle_dir
    )

    # -- Load report spec --
    spec = load_report_spec(report_spec_path)
    report_title: str = spec.get("report_title", "Q2 2026 Supplier Performance Report")
    report_description: str = spec.get("report_description", "")
    report_language: str = spec.get("report_language", "English")
    sections: list[dict] = spec.get("sections", [])

    if not sections:
        print("ERROR: report_spec contains no sections.", file=sys.stderr)
        sys.exit(1)

    # -- Status --
    print("[INFO] === Quarterly Supplier Performance Report Generator PoC ===")
    print(f"[INFO] Bundle      : {bundle_path}")
    print(f"[INFO] Sources     : {len(source_paths)} file(s)")
    for sp in source_paths:
        print(f"[INFO]   {sp.name}")
    print(f"[INFO] Spec        : {report_spec_path.name}")
    print(f"[INFO] Template    : {sample_report_path.name if sample_report_path else '(none)'}")
    print(f"[INFO] Sections    : {len(sections)}")
    print(f"[INFO] Report title: {report_title}")
    print(f"[INFO] Model       : {extraction_model}  temp={temperature}  reasoning={reasoning_effort}")
    print(f"[INFO] Output dir  : {output_dir}")
    print("[INFO] Starting agentic report generation ...")

    # -- Build writer / reviewer LLM options --
    writer_opts: dict = {
        "model": extraction_model,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
    }

    # ----- Step: generate_report  (MultiSourceReportGenerator) -----
    generator = MultiSourceReportGenerator(use_azure=use_azure)
    result = generator.run(
        input_paths=[str(p) for p in source_paths],
        sections=sections,
        report_title=report_title,
        report_description=report_description,
        report_language=report_language,
        sample_report_path=str(sample_report_path) if sample_report_path else None,
        output_dir=str(output_dir),
        output_docx=False,
        agentic=True,
        curate_evidence=False,
        polish=False,
        strict_review=True,
        include_source_references=True,
        include_evidence_index=True,
        verbose=True,
        writer_options=writer_opts,
        review_options=writer_opts,
    )

    # ----- Step: notify_reviewer  (console notification) -----
    report_path = output_dir / "report.md"
    evidence_path = output_dir / "evidence_index.json"

    # If the module did not write evidence_index.json, write it from result.evidence_items.
    if not evidence_path.exists() and hasattr(result, "evidence_items") and result.evidence_items:
        evidence_data = []
        for item in result.evidence_items:
            if hasattr(item, "model_dump"):
                evidence_data.append(item.model_dump())
            elif hasattr(item, "__dict__"):
                evidence_data.append(vars(item))
            else:
                evidence_data.append(str(item))
        evidence_path.write_text(
            json.dumps(evidence_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ----- Post-process: remove duplicate consecutive headings -----
    if report_path.exists() and report_path.stat().st_size > 0:
        raw = report_path.read_text(encoding="utf-8")
        cleaned = _deduplicate_headings(raw)
        if cleaned != raw:
            report_path.write_text(cleaned, encoding="utf-8")
            print("[INFO] Deduplicated repeated section headings in report.md")

    # ----- Output validation -----
    errors: list[str] = []

    if not report_path.exists():
        errors.append(f"output/report.md was not created: {report_path}")
    elif report_path.stat().st_size == 0:
        errors.append(f"output/report.md is empty: {report_path}")

    if not evidence_path.exists():
        errors.append(f"output/evidence_index.json was not created: {evidence_path}")
    else:
        try:
            json.loads(evidence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"output/evidence_index.json is not valid JSON: {exc}")

    if errors:
        print("\n[FAIL] Output validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    # ----- Success summary -----
    written_sections = (
        [s.title for s in result.sections]
        if hasattr(result, "sections") and result.sections
        else []
    )
    print(f"\n[OK] Report written         : {report_path}")
    print(f"[OK] Evidence index written : {evidence_path}")
    if written_sections:
        print(f"[OK] Sections written       : {', '.join(written_sections)}")

    print()
    print("[DRAFT] *** This report is a DRAFT pending procurement manager review. ***")
    print("[DRAFT] Do not release or distribute until a procurement manager has approved it.")
    print("[DRAFT] To review: open output/report.md and consult output/evidence_index.json.")


if __name__ == "__main__":
    main()
