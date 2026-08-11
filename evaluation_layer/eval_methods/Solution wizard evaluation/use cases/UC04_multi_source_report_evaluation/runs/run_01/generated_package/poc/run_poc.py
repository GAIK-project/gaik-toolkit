"""Proof of Concept: Q2 2026 Supplier Performance Report -- Multi-Source Synthesis

Reads a poc_input_bundle.json, resolves all source paths relative to the bundle
directory, calls MultiSourceReportGenerator in agentic mode with strict review,
and writes:
  output/report.md           -- Markdown draft (exact title, six required sections)
  output/evidence_index.json -- Source audit trail (parseable JSON)

The report is a DRAFT for procurement manager review.
It is NOT approved for release until the manager signs off.

Usage:
    python run_poc.py --input <path-to-poc_input_bundle.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator  # noqa: E402


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

def fix_duplicate_headings(text: str) -> str:
    """Remove a Markdown heading that is immediately repeated after blank lines.

    The report template (sample_report_path) already contains section headings.
    When the module also writes a heading at the start of each section, the result
    is two consecutive identical headings separated by blank lines.  This function
    removes the first occurrence so only one heading appears per section.

    Example fixed:
        ## Executive Summary          <- first (blank, from template)
                                      <- blank line
        ## Executive Summary          <- second (with content)
        Q2 supplier performance...
    Becomes:
        ## Executive Summary
        Q2 supplier performance...
    """
    lines = text.splitlines(keepends=True)
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            heading = line.rstrip("\n").rstrip()
            # Scan forward past any blank lines
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            # If the next non-blank line is the same heading, skip current line
            # (and the blank lines between them) to keep only the second occurrence
            if j < len(lines) and lines[j].rstrip("\n").rstrip() == heading:
                i = j  # jump to the second (content-bearing) occurrence
                continue
        result.append(line)
        i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

def load_bundle(bundle_path: Path) -> dict:
    """Load and return the input bundle JSON."""
    return json.loads(bundle_path.read_text(encoding="utf-8"))


def resolve_bundle_paths(bundle: dict, bundle_dir: Path) -> tuple[list[Path], Path, Path | None]:
    """Resolve all relative paths in the bundle against the bundle directory.

    Returns:
        source_paths      -- list of resolved Path objects for the four source files
        report_spec_path  -- resolved Path for report_spec.json
        sample_report     -- resolved Path for report_template.md, or None if missing
    """
    source_paths = [
        (bundle_dir / sf).resolve()
        for sf in bundle.get("source_files", [])
    ]
    report_spec_path = (bundle_dir / bundle["report_spec"]).resolve()
    sample_raw = bundle.get("sample_report")
    sample_report = (bundle_dir / sample_raw).resolve() if sample_raw else None
    return source_paths, report_spec_path, sample_report


# Gate-3 instruction refinements applied on top of whatever report_spec.json contains.
# Blueprint v1.1: actions section must restrict [source_file] citations to the Action
# column only to prevent citation text from leaking into Completion Condition cells.
_SECTION_OVERRIDES: dict[str, dict] = {
    "actions": {
        "instructions": (
            "Create a table with Action, Owner, Due Date, and Completion Condition. "
            "Include only actions explicitly stated in the evidence. "
            "Place source citations [filename] in the Action column only; "
            "do not add citations in the Owner, Due Date, or Completion Condition columns. "
            "If an action does not appear explicitly in a source document's action log or "
            "in meeting-note decisions, omit it entirely — do not include inferred or "
            "routine monitoring actions."
        )
    }
}


def load_sections(report_spec_path: Path) -> list[dict]:
    """Load section specifications from report_spec.json and apply blueprint overrides."""
    spec = json.loads(report_spec_path.read_text(encoding="utf-8"))
    sections = spec.get("sections", [])
    for section in sections:
        sid = section.get("id")
        if sid in _SECTION_OVERRIDES:
            section.update(_SECTION_OVERRIDES[sid])
    return sections


# ---------------------------------------------------------------------------
# Status helpers (Windows-safe ASCII -- no unicode arrows or box characters)
# ---------------------------------------------------------------------------

def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Q2 2026 Supplier Performance Report -- Multi-Source Synthesis PoC"
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="BUNDLE",
        help="Path to poc_input_bundle.json",
    )
    args = parser.parse_args()

    # ----- Step: upload_sources -- load bundle and resolve paths -----
    bundle_path = Path(args.input).resolve()
    if not bundle_path.exists():
        err(f"Bundle file not found: {bundle_path}")
        sys.exit(1)

    bundle_dir = bundle_path.parent
    info(f"Bundle: {bundle_path.name}  (base dir: {bundle_dir})")

    bundle = load_bundle(bundle_path)
    source_paths, report_spec_path, sample_report_path = resolve_bundle_paths(bundle, bundle_dir)

    # Verify sources
    missing = [p for p in source_paths if not p.exists()]
    if missing:
        for p in missing:
            err(f"Source file not found: {p}")
        sys.exit(1)

    for p in source_paths:
        ok(f"Source: {p.name}")

    if not report_spec_path.exists():
        err(f"report_spec not found: {report_spec_path}")
        sys.exit(1)
    ok(f"Report spec: {report_spec_path.name}")

    if sample_report_path and sample_report_path.exists():
        ok(f"Sample report: {sample_report_path.name}")
    else:
        warn("Sample report not found -- proceeding without style template")
        sample_report_path = None

    sections = load_sections(report_spec_path)
    info(f"Loaded {len(sections)} sections from report spec")
    for s in sections:
        deps = s.get("depends_on", [])
        suffix = f"  (after: {', '.join(deps)})" if deps else ""
        info(f"  Section: {s['title']}{suffix}")

    # Output directory
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ----- Step: synthesise_report -- MultiSourceReportGenerator -----
    info("Initialising MultiSourceReportGenerator (Azure OpenAI) ...")
    generator = MultiSourceReportGenerator(use_azure=True)

    writer_opts = {
        "model": "gpt-5.4",
        "temperature": 1.0,
        "reasoning_effort": "medium",
    }
    review_opts = {
        "model": "gpt-5.4",
        "temperature": 1.0,
        "reasoning_effort": "medium",
    }

    info("Starting agentic report synthesis (strict_review=True) ...")
    info("Sections will be written in dependency order.")
    info("Per-section progress will appear below:")
    print("-" * 60)

    result = generator.run(
        input_paths=[str(p) for p in source_paths],
        sections=sections,
        report_title="Q2 2026 Supplier Performance Report",
        report_description=(
            "Internal management report for procurement leadership covering "
            "Q2 supplier delivery, quality, spend, risks, and agreed actions."
        ),
        report_language="English",
        sample_report_path=str(sample_report_path) if sample_report_path else None,
        output_dir=str(output_dir),
        output_docx=False,
        agentic=True,
        strict_review=True,
        curate_evidence=False,
        polish=False,
        include_source_references=True,
        include_evidence_index=True,
        verbose=True,
        writer_options=writer_opts,
        review_options=review_opts,
    )

    print("-" * 60)

    # Contract variables (report synthesis -- no structured extraction)
    extracted_fields = None  # No extraction step in this pipeline
    source_text = ""         # No LLMJudge validation step

    # ----- Verify and save outputs -----
    report_path = output_dir / "report.md"
    evidence_path = output_dir / "evidence_index.json"

    # report.md -- written by the module; fall back to result.markdown if needed.
    # Post-process to remove duplicate consecutive section headings caused by the
    # sample_report_path template already containing heading lines.
    if report_path.exists() and report_path.stat().st_size > 0:
        raw = report_path.read_text(encoding="utf-8")
        cleaned = fix_duplicate_headings(raw)
        if cleaned != raw:
            report_path.write_text(cleaned, encoding="utf-8")
            info("Removed duplicate section headings from report.")
        ok(f"Report written: output/report.md ({report_path.stat().st_size} bytes)")
    elif result.markdown:
        cleaned = fix_duplicate_headings(result.markdown)
        report_path.write_text(cleaned, encoding="utf-8")
        ok(f"Report written (fallback): output/report.md ({len(cleaned)} chars)")
    else:
        err("Report is empty -- check pipeline output above.")
        sys.exit(1)

    # evidence_index.json -- written by the module when include_evidence_index=True
    if evidence_path.exists():
        try:
            json.loads(evidence_path.read_text(encoding="utf-8"))
            ok(f"Evidence index written: output/evidence_index.json")
        except json.JSONDecodeError:
            err(f"Evidence index is not valid JSON: {evidence_path}")
            sys.exit(1)
    else:
        # Fallback: build from result.evidence_items
        if hasattr(result, "evidence_items") and result.evidence_items:
            evidence_data = [
                (ei.model_dump() if hasattr(ei, "model_dump") else vars(ei))
                for ei in result.evidence_items
            ]
            evidence_path.write_text(
                json.dumps({"evidence_items": evidence_data}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            ok("Evidence index written (fallback): output/evidence_index.json")
        else:
            warn("No evidence items returned -- writing empty index.")
            evidence_path.write_text(
                json.dumps({"evidence_items": []}, indent=2),
                encoding="utf-8",
            )

    # ----- Step: notify_manager -- handoff message -----
    print("")
    print("=" * 60)
    print("[DONE] PoC pipeline complete.")
    print(f"       Report:         {report_path}")
    print(f"       Evidence index: {evidence_path}")
    print("")
    print("[NOTE] This is a DRAFT for procurement manager review.")
    print("       The report is NOT approved for release until the")
    print("       manager reviews and signs off.")
    print("=" * 60)


if __name__ == "__main__":
    main()
