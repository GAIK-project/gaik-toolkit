"""
Example: write a report from a report spec with the ReportWriter module.

Every stage saves plain files to the workspace output/<EXAMPLE>/, next to this script:
normalized/ (Markdown sources), knowledge/ (fact units per section) and report/ (the
section drafts, review_log.json, report.md and report.docx).

MODE:
    "full"         normalize, curate and synthesize.
    "resume"       synthesize only, from the knowledge/ files of an earlier "full" run.
                   Edit a file in output/<EXAMPLE>/knowledge/ first, e.g. delete a fact
                   unit, and the report changes accordingly.
    "single_call"  normalize, then the whole report in one call, into single_call/: the
                   baseline to compare report/ against.

Needs: pip install "gaik[report-writer]", the Pandoc binary for report.docx, and the
LLM credentials of get_llm_config() (Azure unless LLM_PROVIDER says otherwise).
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_modules.report_writer import (  # noqa: E402
    ReportSpec,
    ReportWriter,
    get_llm_config,
)

EXAMPLE = "house_condition_assessment"  # or "project_meeting"
MODE = "full"  # "full", "resume" or "single_call"

HERE = Path(__file__).parent
SPEC_FILE = HERE / EXAMPLE / "report_spec.json"
WORKSPACE = HERE / "output" / EXAMPLE


def main() -> None:
    spec = ReportSpec.load(SPEC_FILE)
    writer = ReportWriter(get_llm_config())
    print(f"Spec: {SPEC_FILE}\nWorkspace: {WORKSPACE}\nMode: {MODE}")

    if MODE == "full":
        report = writer.run(spec, WORKSPACE, progress_callback=print)
        folder = WORKSPACE / "report"
    elif MODE == "resume":
        report = writer.synthesize(spec, WORKSPACE, progress_callback=print)
        folder = WORKSPACE / "report"
    elif MODE == "single_call":
        report = writer.run(spec, WORKSPACE, mode="single_call", progress_callback=print)
        folder = WORKSPACE / "single_call"
    else:
        raise ValueError(f"Unknown MODE {MODE!r}; use 'full', 'resume' or 'single_call'")

    print(f"\nSections: {[s.title for s in report.sections]}")
    for entry in report.review_log:
        print(
            f"  review {entry.section_id}: {len(entry.applied)} edits applied, "
            f"{len(entry.unresolved)} unresolved"
        )
    print(f"Writer token usage: {report.usage}")
    print(f"Report: {folder / 'report.md'}\nDOCX:   {folder / 'report.docx'}")
    if MODE == "full":
        print(
            f"\nTo see the knowledge files at work, edit a file in {WORKSPACE / 'knowledge'}, "
            'set MODE = "resume" and run again.'
        )


if __name__ == "__main__":
    main()
