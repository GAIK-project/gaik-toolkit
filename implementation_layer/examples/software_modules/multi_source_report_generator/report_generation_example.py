"""
Example: generate a user-defined Markdown report from multiple source files.

Workflow: input_paths (mixed file types) -> normalize each file to markdown
evidence -> write each user-defined section with an LLM -> assembled report.md

Place any mix of supported files in ``sample_inputs/`` (PDF, Word, Excel/CSV,
text, Markdown, audio/video, images). Markdown/text/CSV work with the base
install; other types need their respective GAIK extras.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_modules.multi_source_report_generator import (  # noqa: E402
    MultiSourceReportGenerator,
    load_report_config,
    save_report_config,
)

# V2 agentic workflow toggle. The single switch below controls everything:
#   True  -> each section is drafted independently and then mandatorily
#            fact-checked/repaired by a diff-editor reviewer, with live CLI
#            progress. Requires: pip install "gaik[multi-source-report-generator-agentic]"
#   False -> the report is written in a single LLM call (the default).
USE_AGENTIC = True

# Config file toggle.
#   True  -> load all run() options from report_config.json (if it exists) instead of
#            the hardcoded variables below. Any option in the JSON overrides the
#            defaults. The config is still re-saved after every run so it stays current.
#   False -> use the hardcoded variables below. The config is saved/updated on every run
#            so you can inspect it, share it, or flip USE_CONFIG_FILE=True next time.
USE_CONFIG_FILE = False
CONFIG_FILE = Path(__file__).parent / "report_config.json"

# Sample report toggle. When True, sample_report.md is used as a format/style
# reference (layout, list style, length). The writer and reviewer both enforce
# that format. Content always comes from the evidence only.
# When False (or the file is absent), the report uses a generic professional format.
USE_SAMPLE_REPORT = True

# # The report structure is entirely user-defined: a title plus a list of
# # sections, each with instructions describing what the section should contain.
REPORT_TITLE = "Q2 Product Planning Meeting Report"

# Optional high-level description of the report's purpose. Passed to the writer,
# reviewer, curator, and polish pass as shared context. Set to None to omit.
REPORT_DESCRIPTION = (
    "A structured report of the Q2 product planning meeting held on September 10, 2024, "
    "documenting decisions, priorities, action items, and open questions."
)

# Each section may optionally declare:
#   "id"          - stable identifier (auto-derived from the title if omitted)
#   "depends_on"  - list of section ids that must be written BEFORE this one; in
#                   agentic mode their finalized content is passed in as context
#                   (e.g. a summary/conclusions section depending on earlier ones).
# With no depends_on, all sections are written in parallel (the default).
SECTIONS = [
    {
        "title": "Executive Summary",
        "instructions": (
            "Summarize the purpose and outcome of the Q2 product planning meeting. "
            "Cover the main themes discussed, the overall direction the team aligned on, "
            "and any high-level capacity or resource considerations mentioned."
        ),
    },
    {
        "title": "Decisions Made",
        "instructions": (
            "List and briefly explain the key decisions reached during the meeting. "
            "For each decision, state what was agreed and the main reason or constraint behind it."
        ),
    },
    {
        "title": "Action Items",
        "instructions": (
            "List all action items from the meeting in a table with columns: "
            "Action Item, Owner, Due Date, and Priority. "
            "Use only items explicitly stated in the evidence."
        ),
    },
    {
        "title": "Open Questions",
        "instructions": (
            "List the unresolved questions or topics that require follow-up after the meeting. "
            "Present them as a bulleted list."
        ),
    },
    {
        "id": "next_steps",
        "title": "Next Steps",
        "instructions": (
            "Summarize the immediate next steps and follow-up actions the team should take. "
            "Include any scheduled follow-up meetings or deadlines mentioned."
        ),
        "depends_on": ["decisions_made", "action_items", "open_questions"],
    },
]


def main() -> None:
    sample_dir = Path(__file__).parent / "sample_inputs"
    output_dir = Path(__file__).parent / "output"
    transcripts_dir = output_dir / "transcripts"

    # Sample report — used as a format/style reference only when USE_SAMPLE_REPORT=True
    # and the file exists. Set USE_SAMPLE_REPORT=False to use a generic format instead.
    sample_report = Path(__file__).parent / "sample_report.md"
    sample_report_path = (
        (sample_report if sample_report.exists() else None) if USE_SAMPLE_REPORT else None
    )

    if not sample_dir.exists() or not any(sample_dir.iterdir()):
        print(
            f"Put some source files in {sample_dir} first (e.g. a .md, .txt, .pdf, .mp3, or .jpg)."
        )
        return

    # ── Run options ───────────────────────────────────────────────────────────
    # Build the run() kwargs from either the config file or the hardcoded vars.
    if USE_CONFIG_FILE and CONFIG_FILE.exists():
        print(f"Config: loading existing config → {CONFIG_FILE}")
        run_kwargs = load_report_config(CONFIG_FILE)
    else:
        if USE_CONFIG_FILE:
            print(
                f"Config: USE_CONFIG_FILE=True but {CONFIG_FILE.name} not found — using hardcoded defaults."
            )
        else:
            print("Config: using hardcoded variables (USE_CONFIG_FILE=False).")
        run_kwargs = {
            "input_paths": [sample_dir],
            "report_title": REPORT_TITLE,
            "report_description": REPORT_DESCRIPTION,
            "additional_instructions": None,  # e.g. "Do not use bullet points. Write in prose only."
            "sections": SECTIONS,
            "report_language": "English",
            "sample_report_path": sample_report_path,
            "output_dir": output_dir,
            # Optional DOCX export. Requires:
            #   pip install "gaik[multi-source-report-generator-docx]"
            #   + Pandoc system binary: https://pandoc.org/installing.html
            "output_docx": True,
            "parser_choice": "auto",
            "image_options": {"mode": "parse"},
            "transcriber_options": {
                "ctor": {
                    "output_dir": str(transcripts_dir),
                },
            },
            "writer_options": {"model": "gpt-5.4"},
            "agentic": USE_AGENTIC,
            "curate_evidence": True,
            "polish": True,
            "strict_review": True,
        }

    # Always save/update the config so it stays current with any code changes.
    config_existed = CONFIG_FILE.exists()
    save_report_config(CONFIG_FILE, **run_kwargs)
    print(f"Config: {'updated' if config_existed else 'created'} → {CONFIG_FILE}")

    generator = MultiSourceReportGenerator(use_azure=True)
    print(f"Writing report... ({'agentic V2' if run_kwargs.get('agentic') else 'single-call'})")

    # verbose is a runtime display preference — not stored in the config.
    result = generator.run(**run_kwargs, verbose=run_kwargs.get("agentic", False))

    print(f"Format template: {sample_report_path or '(none)'}")
    print(f"Evidence sources used: {len(result.evidence_items)}")
    for item in result.evidence_items:
        print(f"  - {item.metadata['filename']} ({item.source_type})")

    # Save transcribed text for each audio/video source.
    audio_types = {"audio", "video"}
    audio_items = [it for it in result.evidence_items if it.source_type in audio_types]
    if audio_items:
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        for item in audio_items:
            stem = Path(item.source_path).stem
            txt_path = transcripts_dir / f"{stem}_transcript.txt"
            txt_path.write_text(item.content_markdown, encoding="utf-8")
            print(f"  Transcript saved: {txt_path}")

    print(f"Sections written: {[s.title for s in result.sections]}")
    # In agentic mode, sections may carry non-fatal warnings (e.g. a reviewer edit
    # that could not be applied, or no matching sample section).
    for section in result.sections:
        for warning in section.revision_warnings:
            print(f"  [warning] {section.title}: {warning}")
    print(f"Report written to: {result.markdown_path}")
    if result.docx_path:
        print(f"DOCX written to:  {result.docx_path}")
    if result.usage:
        print(f"Token usage: {result.usage}")


if __name__ == "__main__":
    main()
