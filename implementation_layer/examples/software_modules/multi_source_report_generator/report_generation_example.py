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
)

# The report structure is entirely user-defined: a title plus a list of
# sections, each with instructions describing what the section should contain.
REPORT_TITLE = "AI Consultancy Report"

SECTIONS = [
    {
        "title": "AI Maturity Level",
        "instructions": "Briefly describe the company's current business operations and services offered. \n- Describe their current AI maturity and classify as Low**, Moderate**, or High** (marked with double star). Base this on their development stage, data availability, technical expertise, workflow integration, and AI roadmap. If this information is explicitly present in the context, use it verbatim.",
    },
    {
        "title": "Current Solution Development Stage",
        "instructions": "Explain if they are in ideation, prototyping, implementation phase, or already has an AI product with customer base.\n- Describe the current state of development, and company's AI readiness with what exists and what needs development.\n - Describe what they are currently looking for, and their aims and objectives for AI implementation.",
    },
    {
        "title": "Recommendations",
        "instructions": "Provide a blend of comprehensive discussions, reflections, suggestions, observations, and actionable points.\n- The tone should not be purely commanding or advisory but rather a mix of thoughtful analysis and practical guidance\n- Include relevant technical and business perspectives\n- Use a conversational yet professional tone\n- Make recommendations specific, insightful, and tailored to the company's unique situation\n- Make sure the recommendations are comprehensive and cover everything AI experts recommended in the transcript and the meeting notes. \n- Make sure that no opinion, suggestion, or recommendation present in the overall context is left out.",
    },
]


def main() -> None:
    sample_dir = Path(__file__).parent / "sample_inputs"
    output_dir = Path(__file__).parent / "output"
    transcripts_dir = output_dir / "transcripts"

    # Optional example report. The writer strictly follows its FORMAT and STYLE
    # (.txt/.md/.pdf/.docx) — all content still comes only from the evidence.
    # Set to None to generate without a template.
    sample_report = Path(__file__).parent / "sample_report.md"
    sample_report_path = sample_report if sample_report.exists() else None

    if not sample_dir.exists() or not any(sample_dir.iterdir()):
        print(
            f"Put some source files in {sample_dir} first (e.g. a .md, .txt, .pdf, .mp3, or .jpg)."
        )
        return

    generator = MultiSourceReportGenerator(use_azure=True)

    print("Writing report...")
    result = generator.run(
        # A folder is expanded recursively; only supported file types are used.
        input_paths=[sample_dir],
        report_title=REPORT_TITLE,
        sections=SECTIONS,
        report_language="English",
        # The report follows this example's structure/style (content from evidence only).
        sample_report_path=sample_report_path,
        output_dir=output_dir,
        # PDF parser strategy: auto (pymupdf) | pymupdf | vision | multimodal | docling
        parser_choice="auto",
        # For images: {"mode": "parse"} (default, general parsing to markdown) or
        # {"mode": "structured", "user_requirements": "..."} for structured extraction.
        image_options={"mode": "parse"},
        # Transcriber options:
        #   compress_audio=True  — compress audio before sending (reduces upload size)
        #   output_dir           — Transcriber saves raw transcript files here
        #                          (TranscriptionResult.save() writes {job_id}_raw_transcript.txt)
        transcriber_options={
            "ctor": {
                "compress_audio": True,
                "output_dir": str(transcripts_dir),
            },
        },
        writer_options={"model": "gpt-5.4"},
    )

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
    print(f"Report written to: {result.markdown_path}")
    if result.usage:
        print(f"Token usage: {result.usage}")


if __name__ == "__main__":
    main()
