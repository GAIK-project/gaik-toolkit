"""Offline tests for ReportSynthesizer: the writer client and the reviewer are fakes."""

from __future__ import annotations

import re
import time
from types import SimpleNamespace

import gaik.software_components.report_synthesizer.report_synthesizer as rs
import pytest
from gaik.software_components.draft_reviewer.models import Edit, ReviewResult
from gaik.software_components.knowledge_curator.models import (
    Conflict,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
)
from gaik.software_components.llm.base import ChatResponse, UsageCounter
from gaik.software_components.report_synthesizer import Report, ReportSynthesizer

CONFIG = {"provider": "openai", "api_key": "x", "model": "base-model"}
INSTRUCTIONS = "Cite observations as [field observation, date]. REPORT_RULES"
SAMPLE = "# Sample\n\n## Roof\n\nSAMPLE_MARKER The roof of another house was fine."

SECTIONS = [
    SectionSpec(
        id="summary",
        title="Summary",
        instructions="Five sentences.",
        depends_on=["structures", "services", "recommendations"],
    ),
    SectionSpec(
        id="structures",
        title="Structures",
        instructions="Short paragraphs.",
        required_items=["roof covering", "attic"],
    ),
    SectionSpec(
        id="services",
        title="Services",
        required_items=["ventilation", "latest sewer camera inspection"],
    ),
    SectionSpec(
        id="recommendations",
        title="Recommendations",
        instructions="One line per action.",
        depends_on=["structures", "services"],
    ),
]


def _unit(uid: str, summary: str, file: str, locator: str | None) -> FactUnit:
    return FactUnit(
        id=uid,
        topic="topic",
        time_qualifier="1998",
        summary=summary,
        quote=summary,
        source=SourceRef(file=file, locator=locator),
        source_class="secondary",
        confidence="high",
    )


STRUCTURES = SectionKnowledge(
    section_id="structures",
    units=[_unit("structures-01", "STRUCTURES_FACT bitumen felt roof.", "report.pdf", "page 2")],
    missing=["attic"],
    conflicts=[],
)
SERVICES = SectionKnowledge(
    section_id="services",
    units=[
        _unit("services-01", "SERVICES_FACT ventilation from 1998.", "report.pdf", "page 3"),
        _unit("services-02", "Ventilation renewed in 2015.", "notes.txt", None),
    ],
    missing=["latest sewer camera inspection"],
    conflicts=[
        Conflict(
            topic="ventilation age",
            description="1998 or 2015.",
            status="unresolved",
            unit_ids=["services-01", "services-02"],
        )
    ],
)
KNOWLEDGE = KnowledgeBase(sections=[STRUCTURES, SERVICES])
FIX = Edit(search="DRAFT", replace="REVIEWED", reason="fix")


class _FakeClient:
    """Answers "## <id>\\n\\nDRAFT <id>" unless scripted; records prompts and events."""

    def __init__(self, answers: dict, delays: dict, events: list):
        self.answers, self.delays, self.events = answers, delays, events
        self.prompts: dict[str, str] = {}
        self.kwargs: list[dict] = []
        self.usage = UsageCounter()

    def chat(self, messages, **kwargs):
        assert messages[0]["content"] == rs.WRITER_SYSTEM_PROMPT
        prompt = messages[1]["content"]
        sid = re.search(r'<section_to_write id="([^"]+)">', prompt).group(1)
        self.prompts[sid] = prompt
        self.kwargs.append(kwargs)
        self.events.append(("write", sid))
        time.sleep(self.delays.get(sid, 0))
        usage = {"prompt_tokens": 10, "completion_tokens": 2}
        self.usage.add(usage)
        return ChatResponse(
            text=self.answers.get(sid, f"## {sid}\n\nDRAFT {sid}"),
            model="fake",
            provider="fake",
            usage=usage,
        )


class _FakeReviewer:
    """Replaces DRAFT with REVIEWED; records its calls and returns scripted unresolved edits."""

    def __init__(self, events: list):
        self.events = events
        self.calls: dict[str, dict] = {}
        self.unresolved: dict[str, list[Edit]] = {}
        self.client = SimpleNamespace(usage=UsageCounter())

    def review(self, draft, *, reference, instructions=""):
        self.client.usage.add({"prompt_tokens": 1})
        sid = re.search(r"DRAFT (\S+)", draft).group(1)
        self.calls[sid] = {"reference": reference, "instructions": instructions}
        self.events.append(("reviewed", sid))
        return ReviewResult(
            text=draft.replace("DRAFT", "REVIEWED"),
            applied=[FIX],
            unresolved=self.unresolved.get(sid, []),
        )


class _Fakes:
    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.answers: dict[str, str] = {}
        self.delays: dict[str, float] = {}
        self.client = _FakeClient(self.answers, self.delays, self.events)
        self.reviewer = _FakeReviewer(self.events)
        self.writer_configs: list[dict] = []
        self.reviewer_args: list[tuple] = []


@pytest.fixture
def fakes(monkeypatch) -> _Fakes:
    fakes = _Fakes()

    def create_llm_client(config):
        fakes.writer_configs.append(config)
        return fakes.client

    def draft_reviewer(config, model=None, **kwargs):
        fakes.reviewer_args.append((config, model, kwargs))
        return fakes.reviewer

    monkeypatch.setattr(rs, "create_llm_client", create_llm_client)
    monkeypatch.setattr(rs, "DraftReviewer", draft_reviewer)
    return fakes


def _synthesize(knowledge=KNOWLEDGE, sections=SECTIONS, *, strict_review=False, **kwargs):
    return ReportSynthesizer(CONFIG, strict_review=strict_review).synthesize(
        knowledge, sections, title="Condition assessment", instructions=INSTRUCTIONS, **kwargs
    )


def test_technical_prompt_has_only_its_own_knowledge(fakes):
    _synthesize()
    prompt = fakes.client.prompts["structures"]
    assert STRUCTURES.model_dump_json(indent=2) in prompt
    assert "SERVICES_FACT" not in prompt
    assert "roof covering" in prompt and "Short paragraphs." in prompt
    assert "REPORT_RULES" in prompt and "Condition assessment" in prompt
    assert "Write the section in: English" in prompt
    assert SERVICES.model_dump_json(indent=2) in fakes.client.prompts["services"]
    assert "STRUCTURES_FACT" not in fakes.client.prompts["services"]


def test_derived_prompt_has_reviewed_prerequisites_and_no_knowledge(fakes):
    _synthesize()
    prompt = fakes.client.prompts["recommendations"]
    assert '<section id="structures" title="Structures">\nREVIEWED structures\n</section>' in prompt
    assert '<section id="services" title="Services">\nREVIEWED services\n</section>' in prompt
    assert "DRAFT" not in prompt and "<knowledge>" not in prompt
    assert "STRUCTURES_FACT" not in prompt and "SERVICES_FACT" not in prompt
    summary = fakes.client.prompts["summary"]
    assert "REVIEWED recommendations" in summary and "REVIEWED services" in summary
    assert "<knowledge>" not in summary


def test_derived_sections_are_written_after_their_prerequisites(fakes):
    fakes.delays["services"] = 0.2
    _synthesize()
    events = fakes.events
    for derived, prerequisites in [
        ("recommendations", ["structures", "services"]),
        ("summary", ["structures", "services", "recommendations"]),
    ]:
        start = events.index(("write", derived))
        assert all(events.index(("reviewed", p)) < start for p in prerequisites)
    assert events[-1] == ("reviewed", "summary")


def test_long_dependency_chain(fakes):
    chain = [SectionSpec(id="s0", title="S0")] + [
        SectionSpec(id=f"s{i}", title=f"S{i}", depends_on=[f"s{i - 1}"]) for i in range(1, 30)
    ]
    knowledge = KnowledgeBase(sections=[STRUCTURES.model_copy(update={"section_id": "s0"})])
    report = _synthesize(knowledge=knowledge, sections=chain)
    assert [s.id for s in report.sections] == [s.id for s in chain]
    assert "REVIEWED s28" in fakes.client.prompts["s29"]


def test_sample_report_goes_to_writers_only(fakes):
    _synthesize(sample_report=SAMPLE)
    assert all(SAMPLE in prompt for prompt in fakes.client.prompts.values())
    assert len(fakes.client.prompts) == len(SECTIONS)
    for call in fakes.reviewer.calls.values():
        assert "SAMPLE_MARKER" not in call["reference"]
        assert "SAMPLE_MARKER" not in call["instructions"]


def test_no_sample_report_means_no_format_reference(fakes):
    _synthesize()
    assert all("<format_reference>" not in p for p in fakes.client.prompts.values())


def test_reviewer_reference_and_checks(fakes):
    _synthesize()
    calls = fakes.reviewer.calls
    assert calls["structures"]["reference"] == STRUCTURES.model_dump_json(indent=2)
    assert calls["services"]["reference"] == SERVICES.model_dump_json(indent=2)
    reference = calls["recommendations"]["reference"]
    assert reference in fakes.client.prompts["recommendations"]
    assert "REVIEWED structures" in reference and "REVIEWED services" in reference
    assert "<knowledge>" not in reference and "SERVICES_FACT" not in reference
    for sid, call in calls.items():
        checks = call["instructions"]
        assert "REPORT_RULES" in checks and "(missing: <item>)" in checks
        assert "Do not rewrite the style" in checks
        assert ('"missing" list' in checks) == (sid in ("structures", "services"))
    assert "One line per action." in calls["recommendations"]["instructions"]
    assert "latest sewer camera inspection" in calls["services"]["instructions"]


def test_models_default_to_config_and_can_be_overridden(fakes):
    ReportSynthesizer(CONFIG).synthesize(KNOWLEDGE, SECTIONS, title="T")
    ReportSynthesizer(CONFIG, "writer-model", reviewer_model="reviewer-model").synthesize(
        KNOWLEDGE, SECTIONS, title="T"
    )
    assert [c["model"] for c in fakes.writer_configs] == ["base-model", "writer-model"]
    defaults = {"max_attempts": 5, "chat_options": {}}
    assert fakes.reviewer_args == [(CONFIG, None, defaults), (CONFIG, "reviewer-model", defaults)]


def test_options_reach_the_writer_and_the_reviewer(fakes):
    ReportSynthesizer(
        CONFIG,
        review_attempts=2,
        writer_options={"reasoning_effort": "low"},
        reviewer_options={"temperature": 0.1},
    ).synthesize(KNOWLEDGE, SECTIONS, title="T")
    assert fakes.client.kwargs == [{"reasoning_effort": "low"}] * len(SECTIONS)
    assert fakes.reviewer_args == [
        (CONFIG, None, {"max_attempts": 2, "chat_options": {"temperature": 0.1}})
    ]


def test_usage_heading_order_and_review_log(fakes):
    report = _synthesize()
    # 4 writer calls of 10 + 2 tokens, 4 reviews of 1 prompt token
    assert report.usage == {"prompt_tokens": 44, "completion_tokens": 8}
    assert [s.id for s in report.sections] == [s.id for s in SECTIONS]
    assert [s.title for s in report.sections] == [s.title for s in SECTIONS]
    assert [s.text for s in report.sections] == [f"REVIEWED {s.id}" for s in SECTIONS]
    assert [e.section_id for e in report.review_log] == [s.id for s in SECTIONS]
    assert all(e.applied == [FIX] and e.unresolved == [] for e in report.review_log)
    assert report.title == "Condition assessment"


def test_strict_review_raises_on_unresolved_edits(fakes):
    fakes.reviewer.unresolved["services"] = [Edit(search="nowhere", replace="x", reason="r")]
    with pytest.raises(RuntimeError, match="'services'"):
        _synthesize(strict_review=True)
    assert ("write", "summary") not in fakes.events


def test_unresolved_edits_are_logged_without_strict_review(fakes):
    unresolved = [Edit(search="nowhere", replace="x", reason="r")]
    fakes.reviewer.unresolved["services"] = unresolved
    report = _synthesize()
    entry = next(e for e in report.review_log if e.section_id == "services")
    assert entry.unresolved == unresolved and entry.applied == [FIX]


def _knowledge(*section_ids: str) -> KnowledgeBase:
    return KnowledgeBase(
        sections=[STRUCTURES.model_copy(update={"section_id": i}) for i in section_ids]
    )


@pytest.mark.parametrize(
    ("knowledge", "sections", "title", "match"),
    [
        (_knowledge("structures"), SECTIONS, "T", r"No knowledge .*\['services'\]"),
        (_knowledge("structures", "services", "summary"), SECTIONS, "T", r"\['summary'\]"),
        (_knowledge("structures", "services", "other"), SECTIONS, "T", r"\['other'\]"),
        (_knowledge("structures", "services", "services"), SECTIONS, "T", r"\['services'\]"),
        (
            _knowledge("a"),
            [
                SectionSpec(id="a", title="A"),
                SectionSpec(id="b", title="B", depends_on=["a", "c"]),
                SectionSpec(id="c", title="C", depends_on=["b"]),
            ],
            "T",
            r"Cyclic .*'b'.*'c'|Cyclic .*'c'.*'b'",
        ),
        (
            _knowledge("a"),
            [SectionSpec(id="a", title="A"), SectionSpec(id="a", title="A2")],
            "T",
            r"Duplicate section ids: \['a'\]",
        ),
        (
            _knowledge("a"),
            [SectionSpec(id="a", title="A"), SectionSpec(id="b", title="B", depends_on=["x"])],
            "T",
            r"'b' depends on unknown sections: \['x'\]",
        ),
        (KNOWLEDGE, SECTIONS, "  ", "title is empty"),
        (KnowledgeBase(sections=[]), [], "T", "sections is empty"),
    ],
)
def test_validation_errors_before_any_llm_call(fakes, knowledge, sections, title, match):
    with pytest.raises(ValueError, match=match):
        ReportSynthesizer(CONFIG).synthesize(knowledge, sections, title=title)
    assert fakes.writer_configs == [] and fakes.events == []


def test_blank_sample_report_raises(fakes):
    with pytest.raises(ValueError, match="sample_report is empty"):
        _synthesize(sample_report=" \n")
    assert fakes.events == []


@pytest.mark.parametrize("answer", ["", "  \n ", "## Services\n"])
def test_empty_writer_answer_raises(fakes, answer):
    fakes.answers["services"] = answer
    with pytest.raises(RuntimeError, match="'services'"):
        _synthesize()


def test_progress_messages_and_callback_exception_propagates(fakes):
    messages: list[str] = []
    _synthesize(progress_callback=messages.append)
    assert "Writing Structures" in messages and "Reviewing Structures" in messages
    assert "Finished Summary: 1 edits applied, 0 unresolved" in messages
    assert messages[-1] == "Finished Summary: 1 edits applied, 0 unresolved"

    class CancelledError(Exception):
        pass

    def cancel(message: str) -> None:
        if message == "Reviewing Services":
            raise CancelledError

    with pytest.raises(CancelledError):
        _synthesize(progress_callback=cancel)


def test_save_load_round_trip_with_edited_section(fakes, tmp_path):
    report = _synthesize()
    (tmp_path / "report.docx").write_bytes(b"stale")
    paths = report.save(tmp_path, docx=False)
    assert not (tmp_path / "report.docx").exists()
    assert "docx" not in paths
    assert Report.load(tmp_path) == report.model_copy(update={"usage": {}})
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == report.markdown
    assert report.markdown.startswith("# Condition assessment\n\n## Summary\n\nREVIEWED summary")

    section_file = tmp_path / "sections" / "02_structures.md"
    assert section_file == paths["section:structures"]
    section_file.write_text("## Structures\n\nEdited by the inspector.\n", encoding="utf-8")
    Report.load(tmp_path).save(tmp_path, docx=False)
    rebuilt = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## Structures\n\nEdited by the inspector." in rebuilt
    assert "REVIEWED structures" not in rebuilt and "REVIEWED services" in rebuilt


def test_save_docx(fakes, tmp_path):
    pypandoc = pytest.importorskip("pypandoc")
    try:
        pypandoc.get_pandoc_version()
    except OSError:
        pytest.skip("Pandoc binary not installed")
    paths = _synthesize().save(tmp_path)
    text = pypandoc.convert_file(str(paths["docx"]), "markdown")
    assert "Condition assessment" in text and "REVIEWED recommendations" in text
