"""Live test of the ReportWriter module: a tiny two-section report from two text files.

Runs the default CURACT pipeline (normalize, curate, synthesize) that the demo app uses.
The text sources need no model call to normalize, and one review attempt per section
keeps the run at about six small calls: one curator, one writer and one reviewer call
per section, the two sections in parallel.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from gaik.software_modules.report_writer import (
    KnowledgeBase,
    ReportSpec,
    ReportWriter,
    RunSettings,
    SectionSpec,
    get_llm_config,
)

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

# One fact per section, each in its own source, so a citation can only be right one way.
SOURCES = {
    "roof_inspection.txt": (
        "Roof inspection notes, Koivukuja 5.\n"
        "The roof is covered with bitumen felt that was laid in 2009.\n"
        "No leaks were found in the attic.\n"
    ),
    "plumbing_notes.txt": (
        "Plumbing notes, Koivukuja 5.\nThe water pipes are copper and were replaced in 2015.\n"
    ),
}


def test_report_writer_two_sections_cite_their_sources(tmp_path: Path):
    for name, text in SOURCES.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    spec = ReportSpec(
        title="Condition assessment, Koivukuja 5",
        sections=[
            SectionSpec(id="roof", title="Roof", instructions="The roof covering and its age."),
            SectionSpec(
                id="plumbing", title="Plumbing", instructions="The water pipes and their age."
            ),
        ],
        sources={
            "primary": [tmp_path / "roof_inspection.txt"],
            "secondary": [tmp_path / "plumbing_notes.txt"],
        },
        settings=RunSettings(review_attempts=1, docx=False),
    )
    workspace = tmp_path / "workspace"

    report = ReportWriter(get_llm_config("azure")).run(spec, workspace)
    print(report.markdown)

    # Both sections, in spec order, each with a body.
    assert [s.id for s in report.sections] == ["roof", "plumbing"]
    assert [s.title for s in report.sections] == ["Roof", "Plumbing"]
    assert all(s.text.strip() for s in report.sections)
    assert (workspace / "report" / "report.md").read_text(encoding="utf-8") == report.markdown

    # The curator found each section's fact in that section's source.
    knowledge = KnowledgeBase.load(workspace / "knowledge")
    for section_id, file in (("roof", "roof_inspection.txt"), ("plumbing", "plumbing_notes.txt")):
        assert any(u.source.file == file for u in knowledge.get(section_id).units), section_id

    # Each section states its fact and cites its source by file name.
    roof, plumbing = (s.text.lower() for s in report.sections)
    assert "2009" in roof and "roof_inspection" in roof, roof
    assert "2015" in plumbing and "plumbing_notes" in plumbing, plumbing
    assert report.usage.get("prompt_tokens", 0) > 0
