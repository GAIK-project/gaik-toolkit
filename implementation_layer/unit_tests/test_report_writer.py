"""Offline tests of the ReportWriter module.

The stage components and the LLM client are replaced in the ``report_writer`` module
namespace with fakes that record their constructor arguments and calls. Pandoc is faked
by copying the Markdown, except in the one test that needs the real binary.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import gaik.software_modules.report_writer.report_writer as rw
import pypandoc
import pytest
from gaik.software_components.knowledge_curator.models import SectionKnowledge
from gaik.software_components.llm import ChatResponse
from gaik.software_components.llm.base import UsageCounter
from gaik.software_components.report_synthesizer.models import ReportSection
from gaik.software_components.source_normalizer.models import NormalizedSource
from gaik.software_modules.report_writer import (
    KnowledgeBase,
    ModelSettings,
    NormalizedSources,
    Report,
    ReportSpec,
    ReportWriter,
    RunSettings,
    SectionSpec,
    StepOptions,
)

CONFIG = {"provider": "openai", "model": "base-model"}
SAMPLE_TEXT = "# Sample\n\nSample from sample.docx."
SINGLE_CALL_ANSWER = (
    "# Condition assessment\n\n## Roof\n\nThe roof is old.\n\n### Attic\n\nDry.\n\n"
    "## Summary\n\nFine overall.\n"
)


def make_spec(tmp_path: Path, *, sample_report: bool = True) -> ReportSpec:
    return ReportSpec(
        title="Condition assessment",
        language="Finnish",
        sections=[
            SectionSpec(
                id="roof", title="Roof", instructions="Describe the roof.", required_items=["age"]
            ),
            SectionSpec(id="summary", title="Summary", depends_on=["roof"]),
        ],
        instructions="Site notes outrank documents.",
        sources={
            "primary": [tmp_path / "inputs" / "notes.txt"],
            "secondary": [tmp_path / "inputs" / "old_report.pdf"],
        },
        sample_report=tmp_path / "sample.docx" if sample_report else None,
        models=ModelSettings(
            vision="vision-m",
            transcription="stt-m",
            curator="cur-m",
            writer="wr-m",
            reviewer="rev-m",
        ),
    )


def fake_pandoc(source, to, outputfile):
    shutil.copyfile(source, outputfile)


@pytest.fixture
def rec(monkeypatch):
    """Replace the components, the LLM client and Pandoc with recording fakes."""
    rec = SimpleNamespace(calls=[], answer=SINGLE_CALL_ANSWER)
    rec.names = lambda: [name for name, _ in rec.calls]
    rec.args = lambda name: next(args for n, args in rec.calls if n == name)

    def log(name, **kwargs):
        rec.calls.append((name, kwargs))

    class FakeNormalizer:
        def __init__(self, config, **kwargs):
            log("SourceNormalizer", config=config, **kwargs)
            self.usage = UsageCounter()

        def normalize(self, sources, *, progress_callback=None):
            log("normalize", sources=sources)
            self.usage.add({"prompt_tokens": 3})
            items = [(c, Path(p)) for c, paths in sources.items() for p in paths]
            return NormalizedSources(
                sources=[
                    NormalizedSource(
                        id=f"{i:02d}_{p.stem}",
                        file=p.name,
                        source_class=c,
                        source_type="text",
                        tool="fake",
                        text=f"Text of {p.name}.",
                    )
                    for i, (c, p) in enumerate(items, start=1)
                ]
            )

        def to_markdown(self, path):
            log("to_markdown", path=path)
            self.usage.add({"prompt_tokens": 2})
            return SAMPLE_TEXT

    class FakeCurator:
        def __init__(self, config, model=None, **kwargs):
            log("KnowledgeCurator", config=config, model=model, **kwargs)

        def curate(self, sources, sections, *, instructions="", progress_callback=None):
            log("curate", sources=sources, sections=sections, instructions=instructions)
            return KnowledgeBase(
                sections=[
                    SectionKnowledge(
                        section_id=s.id, units=[], missing=s.required_items, conflicts=[]
                    )
                    for s in sections
                    if not s.derived
                ]
            )

    class FakeSynthesizer:
        def __init__(self, config, model=None, **kwargs):
            log("ReportSynthesizer", config=config, model=model, **kwargs)

        def synthesize(self, knowledge, sections, **kwargs):
            log("synthesize", knowledge=knowledge, sections=sections, **kwargs)
            return Report(
                title=kwargs["title"],
                sections=[
                    ReportSection(id=s.id, title=s.title, text=f"Body of {s.id}.") for s in sections
                ],
                review_log=[],
                usage={"total_tokens": 7},
            )

    class FakeClient:
        def __init__(self, config):
            log("create_llm_client", config=config)

        def chat(self, messages, **kwargs):
            log("chat", messages=messages, **kwargs)
            return ChatResponse(
                text=rec.answer, model="fake", provider="fake", usage={"total_tokens": 5}
            )

    monkeypatch.setattr(rw, "SourceNormalizer", FakeNormalizer)
    monkeypatch.setattr(rw, "KnowledgeCurator", FakeCurator)
    monkeypatch.setattr(rw, "ReportSynthesizer", FakeSynthesizer)
    monkeypatch.setattr(rw, "create_llm_client", FakeClient)
    monkeypatch.setattr(pypandoc, "convert_file", fake_pandoc)
    return rec


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


def test_spec_round_trip(tmp_path):
    spec = make_spec(tmp_path)
    path = spec.save(tmp_path / "report_spec.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sources"] == {
        "primary": ["inputs/notes.txt"],
        "secondary": ["inputs/old_report.pdf"],
    }
    assert data["sample_report"] == "sample.docx"

    loaded = ReportSpec.load(path)
    root = tmp_path.resolve()
    assert loaded.sources == {
        "primary": [root / "inputs" / "notes.txt"],
        "secondary": [root / "inputs" / "old_report.pdf"],
    }
    assert loaded.sample_report == root / "sample.docx"
    assert loaded.sections == spec.sections
    assert loaded.models == spec.models

    data["models"]["api_key"] = "secret"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="api_key"):
        ReportSpec.load(path)


def test_spec_without_sources_raises(tmp_path):
    data = make_spec(tmp_path).model_dump()
    data["sources"] = {"primary": []}
    with pytest.raises(ValueError, match="no sources"):
        ReportSpec.model_validate(data)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def test_normalize(tmp_path, rec):
    spec = make_spec(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "normalized").mkdir(parents=True)
    (workspace / "normalized" / "stale.md").write_text("old", encoding="utf-8")

    sources = ReportWriter(CONFIG).normalize(spec, workspace)

    assert rec.args("SourceNormalizer") == {
        "config": CONFIG,
        "vision_model": "vision-m",
        "transcription_model": "stt-m",
        "language": "auto",
    }
    assert sources.usage == {"prompt_tokens": 5}  # the sources and the sample report
    assert rec.args("normalize")["sources"] == spec.sources
    assert rec.args("to_markdown")["path"] == spec.sample_report
    assert sorted(p.name for p in (workspace / "normalized").iterdir()) == [
        "01_notes.md",
        "02_old_report.md",
        "sources.json",
    ]
    assert NormalizedSources.load(workspace / "normalized") == sources.model_copy(
        update={"usage": {}}
    )
    assert (workspace / "sample_report.md").read_text(encoding="utf-8") == SAMPLE_TEXT

    ReportWriter(CONFIG).normalize(make_spec(tmp_path, sample_report=False), workspace)
    assert not (workspace / "sample_report.md").exists()


def test_curate(tmp_path, rec):
    spec = make_spec(tmp_path)
    workspace = tmp_path / "workspace"
    writer = ReportWriter(CONFIG)
    writer.normalize(spec, workspace)
    (workspace / "knowledge").mkdir()
    (workspace / "knowledge" / "removed_section.json").write_text("{}", encoding="utf-8")

    knowledge = writer.curate(spec, workspace)

    assert rec.args("KnowledgeCurator") == {
        "config": CONFIG,
        "model": "cur-m",
        "max_workers": 4,
        "chat_options": {},
    }
    args = rec.args("curate")
    assert args["sources"] == NormalizedSources.load(workspace / "normalized")
    assert args["sections"] == spec.sections
    assert args["instructions"] == "Site notes outrank documents."
    assert [p.name for p in (workspace / "knowledge").iterdir()] == ["roof.json"]
    assert KnowledgeBase.load(workspace / "knowledge") == knowledge


def test_synthesize(tmp_path, rec):
    spec = make_spec(tmp_path)
    spec.settings = RunSettings(
        strict_review=True,
        review_attempts=2,
        writer=StepOptions(reasoning_effort="high"),
        reviewer=StepOptions(temperature=0.2),
    )
    workspace = tmp_path / "workspace"
    writer = ReportWriter(CONFIG)
    writer.normalize(spec, workspace)
    writer.curate(spec, workspace)

    report = writer.synthesize(spec, workspace, progress_callback=print)

    assert rec.args("ReportSynthesizer") == {
        "config": CONFIG,
        "model": "wr-m",
        "reviewer_model": "rev-m",
        "strict_review": True,
        "review_attempts": 2,
        "writer_options": {"reasoning_effort": "high"},
        "reviewer_options": {"temperature": 0.2},
    }
    assert rec.args("synthesize") == {
        "knowledge": KnowledgeBase.load(workspace / "knowledge"),
        "sections": spec.sections,
        "title": "Condition assessment",
        "language": "Finnish",
        "instructions": "Site notes outrank documents.",
        "sample_report": SAMPLE_TEXT,
        "progress_callback": print,
    }
    assert report.usage == {"total_tokens": 7}
    assert (workspace / "report" / "report.md").read_text(encoding="utf-8") == report.markdown
    assert (workspace / "report" / "report.docx").is_file()
    assert Report.load(workspace / "report").sections == report.sections


def test_synthesize_resumes_from_edited_knowledge(tmp_path, rec):
    spec = make_spec(tmp_path)
    workspace = tmp_path / "workspace"
    ReportWriter(CONFIG).normalize(spec, workspace)
    ReportWriter(CONFIG).curate(spec, workspace)
    path = workspace / "knowledge" / "roof.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["missing"] = ["edited by hand"]
    path.write_text(json.dumps(data), encoding="utf-8")
    rec.calls.clear()

    ReportWriter(CONFIG).synthesize(spec, workspace)

    assert rec.names() == ["ReportSynthesizer", "synthesize"]
    assert rec.args("synthesize")["knowledge"].get("roof").missing == ["edited by hand"]


def test_synthesize_needs_the_normalized_sample_report(tmp_path, rec):
    spec = make_spec(tmp_path)
    workspace = tmp_path / "workspace"
    writer = ReportWriter(CONFIG)
    writer.normalize(spec, workspace)
    writer.curate(spec, workspace)
    (workspace / "sample_report.md").unlink()

    with pytest.raises(FileNotFoundError, match="sample_report.md"):
        writer.synthesize(spec, workspace)


def test_missing_stage_input_raises(tmp_path, rec):
    spec = make_spec(tmp_path)
    with pytest.raises(FileNotFoundError, match="sources.json"):
        ReportWriter(CONFIG).curate(spec, tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="knowledge"):
        ReportWriter(CONFIG).synthesize(spec, tmp_path / "empty")


def _save_and_edit_report(workspace: Path) -> None:
    Report(
        title="Condition assessment",
        sections=[ReportSection(id="roof", title="Roof", text="Old text.")],
        review_log=[],
    ).save(workspace / "report")
    section = workspace / "report" / "sections" / "01_roof.md"
    section.write_text(section.read_text(encoding="utf-8").replace("Old", "Edited"), "utf-8")


def test_rebuild(tmp_path, rec):
    workspace = tmp_path / "workspace"
    _save_and_edit_report(workspace)

    report = ReportWriter(CONFIG).rebuild(make_spec(tmp_path), workspace)

    assert report.sections[0].text == "Edited text."
    assert "Edited text." in (workspace / "report" / "report.md").read_text(encoding="utf-8")
    assert "Edited text." in (workspace / "report" / "report.docx").read_text(encoding="utf-8")
    assert rec.calls == []


def test_rebuild_without_docx_removes_the_old_docx(tmp_path, rec):
    workspace = tmp_path / "workspace"
    _save_and_edit_report(workspace)
    spec = make_spec(tmp_path)
    spec.settings.docx = False

    ReportWriter(CONFIG).rebuild(spec, workspace)

    assert "Edited text." in (workspace / "report" / "report.md").read_text(encoding="utf-8")
    assert not (workspace / "report" / "report.docx").exists()


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="needs the Pandoc binary")
def test_rebuild_writes_docx_with_pandoc(tmp_path):
    workspace = tmp_path / "workspace"
    _save_and_edit_report(workspace)

    ReportWriter(CONFIG).rebuild(make_spec(tmp_path), workspace)

    docx_text = pypandoc.convert_file(str(workspace / "report" / "report.docx"), "plain")
    assert "Edited text." in docx_text
    assert "Old text." not in docx_text


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def test_run_curact(tmp_path, rec):
    report = ReportWriter(CONFIG).run(make_spec(tmp_path), tmp_path / "workspace")

    assert rec.names() == [
        "SourceNormalizer",
        "normalize",
        "to_markdown",
        "KnowledgeCurator",
        "curate",
        "ReportSynthesizer",
        "synthesize",
    ]
    assert Report.load(tmp_path / "workspace" / "report").sections == report.sections


def test_run_single_call(tmp_path, rec):
    spec = make_spec(tmp_path)
    spec.settings.writer = StepOptions(reasoning_effort="low")
    workspace = tmp_path / "workspace"

    report = ReportWriter(CONFIG).run(spec, workspace, mode="single_call")

    assert rec.names() == [
        "SourceNormalizer",
        "normalize",
        "to_markdown",
        "create_llm_client",
        "chat",
    ]
    assert rec.args("create_llm_client")["config"] == {**CONFIG, "model": "wr-m"}
    assert rec.args("chat")["reasoning_effort"] == "low"
    user = rec.args("chat")["messages"][1]["content"]
    for part in (
        '<source file="notes.txt" class="primary">\nText of notes.txt.\n</source>',
        '<source file="old_report.pdf" class="secondary">\nText of old_report.pdf.\n</source>',
        SAMPLE_TEXT,
        "1. Heading: Roof\n   Content to cover: Describe the roof.\n   Required items:\n   - age",
        "Site notes outrank documents.",
        "Write the report in: Finnish",
    ):
        assert part in user
    assert [(s.id, s.title, s.text) for s in report.sections] == [
        ("roof", "Roof", "The roof is old.\n\n### Attic\n\nDry."),
        ("summary", "Summary", "Fine overall."),
    ]
    assert report.title == "Condition assessment"
    assert report.review_log == []
    assert report.usage == {"total_tokens": 5}
    saved = Report.load(workspace / "single_call")
    assert saved.sections == report.sections
    assert (workspace / "single_call" / "review_log.json").read_text(encoding="utf-8") == "[]"


@pytest.mark.parametrize(
    "answer",
    [
        "# Condition assessment\n\n## Roof\n\nA.\n",
        "# Condition assessment\n\n## Roof\n\nA.\n\n## Summary\n\nB.\n\n## Extra\n\nC.\n",
        "# Condition assessment\n\n## Summary\n\nB.\n\n## Roof\n\nA.\n",
        "# Condition assessment\n\n## Roof\n\nA.\n\n## Roof\n\nA.\n\n## Summary\n\nB.\n",
        "# Another title\n\n## Roof\n\nA.\n\n## Summary\n\nB.\n",
        "# Condition assessment\n\nIntro.\n\n## Roof\n\nA.\n\n## Summary\n\nB.\n",
        "# Condition assessment\n\n## Roof\n\n## Summary\n\nB.\n",
    ],
    ids=["missing", "extra", "reordered", "duplicated", "title", "intro", "empty"],
)
def test_run_single_call_rejects_a_malformed_answer(tmp_path, rec, answer):
    rec.answer = answer
    with pytest.raises(ValueError, match="single-call answer"):
        ReportWriter(CONFIG).run(make_spec(tmp_path), tmp_path / "workspace", mode="single_call")
    assert not (tmp_path / "workspace" / "single_call").exists()


def test_run_single_call_lists_expected_and_found_headings(tmp_path, rec):
    rec.answer = "# Condition assessment\n\n## Summary\n\nB.\n\n## Roof\n\nA.\n"
    with pytest.raises(
        ValueError, match=r"Expected \['Roof', 'Summary'\], found \['Summary', 'Roof'\]"
    ):
        ReportWriter(CONFIG).run(make_spec(tmp_path), tmp_path / "workspace", mode="single_call")


def test_run_unknown_mode_raises(tmp_path, rec):
    with pytest.raises(ValueError, match="Unknown mode 'fast'"):
        ReportWriter(CONFIG).run(make_spec(tmp_path), tmp_path / "workspace", mode="fast")
    assert rec.calls == []
