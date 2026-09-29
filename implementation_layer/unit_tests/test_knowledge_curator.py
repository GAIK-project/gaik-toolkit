"""Offline tests for KnowledgeCurator: the LLM client is a fake with scripted answers."""

from __future__ import annotations

import re
import time

import gaik.software_components.knowledge_curator.knowledge_curator as kc
import pytest
from gaik.software_components.knowledge_curator import (
    DroppedUnit,
    FactUnit,
    KnowledgeBase,
    KnowledgeCurator,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
    check_sections,
)
from gaik.software_components.llm.base import UsageCounter
from gaik.software_components.source_normalizer.models import NormalizedSource, NormalizedSources

NOTES = "14 March 2026, technical room. The supply-air unit vibrates and the housing is rusty."
REPORT = "[Page 3]\nMechanical ventilation installed in 1998.\nDesign life 25 years."

SOURCES = NormalizedSources(
    sources=[
        NormalizedSource(
            id="01_notes",
            file="notes.txt",
            source_class="primary",
            source_type="text",
            tool="provided",
            text=NOTES,
        ),
        NormalizedSource(
            id="02_report",
            file="report.pdf",
            source_class="secondary",
            source_type="pdf",
            tool="PyMuPDFParser",
            text=REPORT,
        ),
    ]
)


def _unit(quote: str, file: str = "notes.txt", locator: str | None = None) -> kc.CuratedUnit:
    return kc.CuratedUnit(
        topic="ventilation",
        time_qualifier=None,
        summary="A fact.",
        quote=quote,
        source=SourceRef(file=file, locator=locator),
        confidence="high",
    )


def _answer(*units: kc.CuratedUnit, missing=(), conflicts=()) -> kc.CurationResponse:
    return kc.CurationResponse(units=list(units), missing=list(missing), conflicts=list(conflicts))


GOOD = _answer(_unit("The supply-air unit vibrates"))


class _FakeClient:
    """Returns scripted answers per section id, read from the user prompt; records calls."""

    def __init__(self, answers: dict, delays: dict | None = None):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.delays = delays or {}
        self.calls: list[tuple[str, list[dict]]] = []
        self.kwargs: list[dict] = []
        self.usage = UsageCounter()

    def chat_parsed(self, messages, response_format, **kwargs):
        assert response_format is kc.CurationResponse
        section_id = re.search(r'<section id="([^"]+)">', messages[1]["content"]).group(1)
        self.calls.append((section_id, messages))
        self.kwargs.append(kwargs)
        self.usage.add({"prompt_tokens": 10, "completion_tokens": 2})
        time.sleep(self.delays.get(section_id, 0))
        answer = self.answers[section_id].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def fake(monkeypatch):
    def install(answers: dict, delays: dict | None = None) -> _FakeClient:
        client = _FakeClient(answers, delays)
        monkeypatch.setattr(kc, "create_llm_client", lambda cfg: client)
        return client

    return install


def _curate(sections, *, drop_unverified=True, **kwargs) -> KnowledgeBase:
    return KnowledgeCurator(
        {"provider": "openai", "model": "m"}, drop_unverified=drop_unverified
    ).curate(SOURCES, sections, **kwargs)


def test_happy_path_maps_ids_source_class_and_conflicts(fake):
    answer = _answer(
        _unit("the housing is rusty"),
        _unit("Mechanical ventilation installed in 1998.", "report.pdf", "page 3"),
        missing=["latest sewer camera inspection"],
        conflicts=[
            kc.CuratedConflict(
                topic="ventilation", description="d", status="resolved", unit_numbers=[2, 1]
            )
        ],
    )
    client = fake({"services": [answer]})
    section = SectionSpec(
        id="services",
        title="Building services",
        instructions="Heating and ventilation.",
        required_items=["ventilation system", "latest sewer camera inspection"],
    )
    progress: list[str] = []

    knowledge = _curate(
        [section], instructions="Recordings are primary.", progress_callback=progress.append
    )

    result = knowledge.get("services")
    assert [u.id for u in result.units] == ["services-01", "services-02"]
    assert [u.source_class for u in result.units] == ["primary", "secondary"]
    assert result.units[1].source.locator == "page 3"
    assert result.conflicts[0].unit_ids == ["services-02", "services-01"]
    assert result.missing == ["latest sewer camera inspection"]
    assert knowledge.verify_quotes(SOURCES) == []
    assert progress == [
        "Curating Building services",
        "Curated Building services: 2 units, 1 missing, 1 conflicts",
    ]
    ((_, messages),) = client.calls
    user = messages[1]["content"]
    assert f'<source file="notes.txt" class="primary" type="text">\n{NOTES}\n</source>' in user
    assert '<source file="report.pdf" class="secondary" type="pdf">' in user
    for text in (
        "Building services",
        "Heating and ventilation.",
        "- latest sewer camera inspection",
        "Recordings are primary.",
    ):
        assert text in user


def test_derived_sections_are_skipped_and_order_is_kept(fake):
    client = fake({"a": [GOOD], "b": [GOOD], "c": [GOOD]}, delays={"a": 0.1})
    sections = [
        SectionSpec(id="summary", title="Summary", depends_on=["a", "b"]),
        SectionSpec(id="a", title="A"),
        SectionSpec(id="b", title="B"),
        SectionSpec(id="c", title="C"),
    ]

    knowledge = _curate(sections)

    assert [s.section_id for s in knowledge.sections] == ["a", "b", "c"]
    assert sorted(section_id for section_id, _ in client.calls) == ["a", "b", "c"]


def test_only_derived_sections_raise(fake):
    client = fake({})
    sections = [
        SectionSpec(id="a", title="A", depends_on=["b"]),
        SectionSpec(id="b", title="B", depends_on=["a"]),
    ]
    with pytest.raises(ValueError, match="No non-derived section"):
        _curate(sections)
    assert client.calls == []


def test_empty_sources_raise(fake):
    client = fake({})
    curator = KnowledgeCurator({"provider": "openai", "model": "m"})
    with pytest.raises(ValueError, match="No sources"):
        curator.curate(NormalizedSources(sources=[]), [SectionSpec(id="a", title="A")])
    assert client.calls == []


def test_bad_quote_is_retried_once_with_feedback(fake):
    client = fake({"a": [_answer(_unit("The unit shakes")), GOOD]})

    knowledge = _curate([SectionSpec(id="a", title="A")])

    assert knowledge.get("a").units[0].quote == "The supply-air unit vibrates"
    assert len(client.calls) == 2
    retry = client.calls[1][1]
    assert retry[:2] == client.calls[0][1]
    assert "The unit shakes" in retry[-1]["content"]
    assert "verbatim" in retry[-1]["content"]


def test_usage_and_chat_options_cover_every_call(fake):
    client = fake({"a": [_answer(_unit("The unit shakes")), GOOD], "b": [GOOD]})
    client.usage.add({"prompt_tokens": 1000})  # earlier calls are not counted

    knowledge = KnowledgeCurator(
        {"provider": "openai", "model": "m"}, chat_options={"reasoning_effort": "low"}
    ).curate(SOURCES, [SectionSpec(id="a", title="A"), SectionSpec(id="b", title="B")])

    assert knowledge.usage == {"prompt_tokens": 30, "completion_tokens": 6}
    assert client.kwargs == [{"reasoning_effort": "low"}] * 3


def test_second_bad_answer_raises_when_not_dropping(fake):
    bad = _answer(_unit("The unit shakes"))
    fake({"a": [bad, bad]})
    with pytest.raises(ValueError, match=r"'a'.*The unit shakes"):
        _curate([SectionSpec(id="a", title="A")], drop_unverified=False)


def test_unknown_source_file_is_a_failure(fake):
    bad = _answer(_unit("The supply-air unit vibrates", file="unknown.txt"))
    client = fake({"a": [bad, bad]})
    with pytest.raises(ValueError, match="unknown.txt"):
        _curate([SectionSpec(id="a", title="A")], drop_unverified=False)
    assert "unknown.txt" in client.calls[1][1][-1]["content"]


def test_failing_units_are_dropped_after_the_retry_and_reported(fake):
    good = _unit("The supply-air unit vibrates")
    shaky = _unit("The unit shakes")
    unknown = _unit("Design life 25 years", file="unknown.txt")
    later = _unit("Mechanical ventilation installed in 1998.", file="report.pdf")
    bad = _answer(good, shaky, unknown, later)
    client = fake({"a": [bad, bad], "b": [GOOD]})
    messages: list[str] = []

    knowledge = _curate(
        [SectionSpec(id="a", title="Alpha"), SectionSpec(id="b", title="B")],
        progress_callback=messages.append,
    )

    assert len(client.calls) == 3  # one retry, no third attempt
    kept = knowledge.get("a").units
    assert [u.id for u in kept] == ["a-01", "a-02"]  # renumbered without gaps
    assert [u.quote for u in kept] == [good.quote, later.quote]
    assert knowledge.get("b").units[0].quote == GOOD.units[0].quote
    assert knowledge.dropped == [
        DroppedUnit(
            section_id="a",
            topic="ventilation",
            summary="A fact.",
            quote="The unit shakes",
            file="notes.txt",
            reason="quote not found in source",
        ),
        DroppedUnit(
            section_id="a",
            topic="ventilation",
            summary="A fact.",
            quote="Design life 25 years",
            file="unknown.txt",
            reason="file is not a source",
        ),
    ]
    assert "Dropped 2 fact(s) of Alpha: the quote is not in its source" in messages
    assert knowledge.verify_quotes(SOURCES) == []


def test_conflicts_are_renumbered_and_one_sided_ones_removed(fake):
    units = [
        _unit("The supply-air unit vibrates"),
        _unit("The unit shakes"),
        _unit("Mechanical ventilation installed in 1998.", file="report.pdf"),
    ]
    conflicts = [
        kc.CuratedConflict(
            topic="kept", description="d", status="resolved", unit_numbers=[1, 2, 3]
        ),
        kc.CuratedConflict(topic="gone", description="d", status="unresolved", unit_numbers=[2, 3]),
    ]
    bad = _answer(*units, conflicts=conflicts)
    fake({"a": [bad, bad]})

    knowledge = _curate([SectionSpec(id="a", title="A")]).get("a")

    assert [c.topic for c in knowledge.conflicts] == ["kept"]
    assert knowledge.conflicts[0].unit_ids == ["a-01", "a-02"]


def test_a_section_whose_units_all_fail_is_kept_empty(fake):
    bad = _answer(_unit("The unit shakes"))
    fake({"a": [bad, bad]})

    knowledge = _curate([SectionSpec(id="a", title="A", required_items=["vibration"])])

    assert knowledge.get("a").units == []
    assert len(knowledge.dropped) == 1


def test_a_retry_that_fixes_the_quotes_drops_nothing(fake):
    fake({"a": [_answer(_unit("The unit shakes")), GOOD]})

    assert _curate([SectionSpec(id="a", title="A")]).dropped == []


def test_dropping_still_rejects_an_out_of_range_conflict(fake):
    conflict = kc.CuratedConflict(
        topic="t", description="d", status="unresolved", unit_numbers=[1, 3]
    )
    bad = _answer(
        _unit("The unit shakes"), _unit("The supply-air unit vibrates"), conflicts=[conflict]
    )
    fake({"a": [bad, bad]})

    with pytest.raises(ValueError, match=r"'a'.*\[3\]"):
        _curate([SectionSpec(id="a", title="A")])


def test_dropped_units_are_not_saved(fake, tmp_path):
    bad = _answer(_unit("The unit shakes"), _unit("The supply-air unit vibrates"))
    fake({"a": [bad, bad]})
    knowledge = _curate([SectionSpec(id="a", title="A")])

    knowledge.save(tmp_path)

    assert KnowledgeBase.load(tmp_path).dropped == []
    assert "dropped" not in (tmp_path / "a.json").read_text(encoding="utf-8")


def test_out_of_range_conflict_index_raises(fake):
    conflict = kc.CuratedConflict(
        topic="t", description="d", status="unresolved", unit_numbers=[1, 2]
    )
    fake({"a": [_answer(_unit("The supply-air unit vibrates"), conflicts=[conflict])]})
    with pytest.raises(ValueError, match=r"'a'.*\[2\]"):
        _curate([SectionSpec(id="a", title="A")])


def test_client_exception_propagates(fake):
    fake({"a": [GOOD], "b": [RuntimeError("boom")]})
    with pytest.raises(RuntimeError, match="boom"):
        _curate([SectionSpec(id="a", title="A"), SectionSpec(id="b", title="B")])


def test_progress_callback_exception_propagates(fake):
    client = fake({"a": [GOOD]})

    def cancel(message: str) -> None:
        raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        _curate([SectionSpec(id="a", title="A")], progress_callback=cancel)
    assert client.calls == []


def test_model_override(monkeypatch):
    configs: list[dict] = []
    monkeypatch.setattr(kc, "create_llm_client", lambda cfg: configs.append(cfg))
    config = {"provider": "openai", "model": "default"}
    KnowledgeCurator(config, model="override")
    KnowledgeCurator(config)
    assert [c["model"] for c in configs] == ["override", "default"]


def _knowledge(quote: str) -> KnowledgeBase:
    unit = FactUnit(
        id="a-01",
        topic="t",
        time_qualifier="1998",
        summary="s",
        quote=quote,
        source=SourceRef(file="report.pdf", locator="page 3"),
        source_class="secondary",
        confidence="high",
    )
    return KnowledgeBase(
        sections=[SectionKnowledge(section_id="a", units=[unit], missing=["x"], conflicts=[])]
    )


def test_knowledge_base_save_load_round_trip(tmp_path):
    knowledge = _knowledge("Design life 25 years.")
    paths = knowledge.save(tmp_path)
    assert paths == {"a": tmp_path / "a.json"}
    assert KnowledgeBase.load(tmp_path) == knowledge


def test_verify_quotes_ignores_whitespace():
    assert _knowledge("installed in   1998.\n  Design life").verify_quotes(SOURCES) == []
    bad = _knowledge("installed in 1999.")
    assert bad.verify_quotes(SOURCES) == bad.sections[0].units


def test_check_sections_errors(fake):
    with pytest.raises(ValueError, match="Duplicate section ids"):
        check_sections([SectionSpec(id="a", title="A"), SectionSpec(id="a", title="B")])
    with pytest.raises(ValueError, match="unknown sections"):
        check_sections([SectionSpec(id="a", title="A", depends_on=["z"])])
    client = fake({})
    with pytest.raises(ValueError, match="Duplicate section ids"):
        _curate([SectionSpec(id="a", title="A"), SectionSpec(id="a", title="B")])
    assert client.calls == []
