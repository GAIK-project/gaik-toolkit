"""Knowledge Curator endpoints: a fake KnowledgeCurator stands in for gaik's, so no test
calls a model; gaik's real models validate the sections and the knowledge files."""

from __future__ import annotations

import json

import pytest
from api.routers import knowledge_curator as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_components import knowledge_curator as kc_module
from gaik.software_components.knowledge_curator import (
    DroppedUnit,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SourceRef,
)
from gaik.software_components.source_normalizer import NormalizedSource, NormalizedSources

CONFIG = {"provider": "fake", "model": "fake-model"}
NOTES = "The supply-air unit vibrates. The housing is rusty."
REPORT = "Mechanical ventilation installed in 1998."
SOURCES = NormalizedSources(
    sources=[
        NormalizedSource(
            id="01_notes",
            file="notes.txt",
            source_class="primary",
            source_type="text",
            tool="text",
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
NORMALIZED = {
    "normalized/01_notes.md": NOTES,
    "normalized/02_report.md": REPORT,
    "normalized/sources.json": json.dumps(
        [s.model_dump(exclude={"text"}) for s in SOURCES.sources]
    ),
}
REQUEST = {
    "sections": [
        {"id": "vent", "title": "Ventilation", "required_items": ["age"]},
        {"id": "roof", "title": "Roof", "instructions": "Condition."},
    ],
    "instructions": "Prefer primary sources.",
    "options": {"model": "gpt-x", "reasoning_effort": "low", "max_workers": 2},
}
CALLS: list[dict] = []


def _unit(uid: str, quote: str, file: str = "notes.txt") -> FactUnit:
    return FactUnit(
        id=uid,
        topic="t",
        time_qualifier=None,
        summary="A fact.",
        quote=quote,
        source=SourceRef(file=file, locator=None),
        source_class="primary",
        confidence="high",
    )


class FakeCurator:
    def __init__(self, config, model=None, *, max_workers, chat_options) -> None:
        assert config is CONFIG
        self.model, self.max_workers, self.chat_options = model, max_workers, chat_options

    def curate(self, sources, sections, *, instructions, progress_callback):
        CALLS.append(
            {
                "model": self.model,
                "workers": self.max_workers,
                "chat_options": self.chat_options,
                "instructions": instructions,
                "sections": [s.id for s in sections],
                "files": [s.file for s in sources.sources],
            }
        )
        for s in sections:
            progress_callback(f"Curating {s.title}")
        if sections[0].id == "boom":
            raise ValueError("Section 'boom': something failed")
        knowledge = [
            SectionKnowledge(
                section_id=s.id,
                units=[_unit(f"{s.id}-01", "The supply-air unit vibrates")],
                missing=[],
                conflicts=[],
            )
            for s in sections
        ]
        dropped = [
            DroppedUnit(
                section_id=sections[0].id,
                topic="t",
                summary="s",
                quote="The unit shakes",
                file="notes.txt",
                reason="quote not found in source",
            )
        ]
        return KnowledgeBase(sections=knowledge, usage={"prompt_tokens": 5}, dropped=dropped)


class FakeGaik:
    """The real gaik models with the curator replaced."""

    KnowledgeCurator = FakeCurator
    KnowledgeBase = kc_module.KnowledgeBase
    SectionKnowledge = kc_module.SectionKnowledge
    SectionSpec = kc_module.SectionSpec
    NormalizedSource = NormalizedSource
    NormalizedSources = NormalizedSources


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    CALLS.clear()
    monkeypatch.setattr(route, "_gaik", lambda: FakeGaik)
    monkeypatch.setattr(route, "get_api_config", lambda: CONFIG)
    app = FastAPI()
    app.include_router(route.router, prefix="/knowledge-curator")
    return TestClient(app)


def _run(client, request=REQUEST, artifacts=NORMALIZED):
    return client.post(
        "/knowledge-curator/run",
        data={"request": request if isinstance(request, str) else json.dumps(request)},
        files={"artifacts": ("artifacts.json", json.dumps(artifacts).encode())},
    )


def _verify(client, files):
    return client.post(
        "/knowledge-curator/verify",
        files={"artifacts": ("artifacts.json", json.dumps(files).encode())},
    )


def _events(response) -> list[tuple[str, dict]]:
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.split("\n\n"):
        if block.startswith("event: "):
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def _knowledge(*units: FactUnit, section_id="vent") -> str:
    return SectionKnowledge(
        section_id=section_id, units=list(units), missing=[], conflicts=[]
    ).model_dump_json()


# ---------------------------------------------------------------------------
# /run
# ---------------------------------------------------------------------------


def test_run_returns_knowledge_files_usage_and_dropped_facts(client):
    events = _events(_run(client))

    assert [name for name, _ in events] == ["progress", "progress", "result"]
    result = events[-1][1]
    assert sorted(result["artifacts"]) == ["knowledge/roof.json", "knowledge/vent.json"]
    vent = SectionKnowledge.model_validate_json(result["artifacts"]["knowledge/vent.json"])
    assert vent.units[0].quote == "The supply-air unit vibrates"
    assert result["usage"] == {"prompt_tokens": 5}
    assert result["dropped"] == [
        {
            "section_id": "vent",
            "topic": "t",
            "summary": "s",
            "quote": "The unit shakes",
            "file": "notes.txt",
            "reason": "quote not found in source",
        }
    ]


def test_run_passes_sections_sources_and_options_to_the_curator(client):
    _events(_run(client))

    assert CALLS == [
        {
            "model": "gpt-x",
            "workers": 2,
            "chat_options": {"reasoning_effort": "low"},
            "instructions": "Prefer primary sources.",
            "sections": ["vent", "roof"],
            "files": ["notes.txt", "report.pdf"],
        }
    ]


def test_a_curator_failure_is_an_error_event(client):
    request = {**REQUEST, "sections": [{"id": "boom", "title": "Boom"}]}
    events = _events(_run(client, request))

    assert events[-1][0] == "error"
    assert "Section 'boom': something failed" in events[-1][1]["message"]


def _without(key):
    return {k: v for k, v in NORMALIZED.items() if k != key}


@pytest.mark.parametrize(
    "request_body, artifacts, message",
    [
        ("not json", NORMALIZED, "Invalid request"),
        ({**REQUEST, "sections": []}, NORMALIZED, "Invalid request"),
        ({**REQUEST, "extra": 1}, NORMALIZED, "Invalid request"),
        (
            {**REQUEST, "sections": [{"id": "has space", "title": "T"}]},
            NORMALIZED,
            "Invalid request",
        ),
        (
            {**REQUEST, "sections": [{"id": "a", "title": "A"}, {"id": "a", "title": "B"}]},
            NORMALIZED,
            "must be distinct",
        ),
        ({**REQUEST, "options": {"max_workers": 99}}, NORMALIZED, "Invalid request"),
        (REQUEST, {"knowledge/x.json": "{}"}, "not allowed"),
        (REQUEST, _without("normalized/sources.json"), "sources.json is missing"),
        (REQUEST, _without("normalized/02_report.md"), "02_report.md is missing"),
        (REQUEST, {**NORMALIZED, "normalized/sources.json": "[]"}, "non-empty list"),
        (
            REQUEST,
            {**NORMALIZED, "normalized/sources.json": "{"},
            "Invalid normalized/sources.json",
        ),
    ],
)
def test_bad_run_requests_are_400(client, request_body, artifacts, message):
    response = _run(client, request_body, artifacts)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert not CALLS


# ---------------------------------------------------------------------------
# /verify
# ---------------------------------------------------------------------------


def test_verify_accepts_verbatim_quotes_ignoring_whitespace(client):
    knowledge = _knowledge(
        _unit("vent-01", "The supply-air unit vibrates."),
        _unit("vent-02", "Mechanical  ventilation\ninstalled in 1998.", "report.pdf"),
    )
    body = _verify(client, {**NORMALIZED, "knowledge/vent.json": knowledge}).json()

    assert body == {"units": 2, "failures": []}


def test_verify_lists_failing_quotes_with_their_reason(client):
    knowledge = _knowledge(
        _unit("vent-01", "The supply-air unit vibrates."),
        _unit("vent-02", "The unit shakes"),
        _unit("vent-03", "Design life 25 years", "unknown.txt"),
    )
    other = _knowledge(_unit("roof-01", "The housing is rusty."), section_id="roof")
    body = _verify(
        client,
        {**NORMALIZED, "knowledge/vent.json": knowledge, "knowledge/roof.json": other},
    ).json()

    assert body["units"] == 4
    assert body["failures"] == [
        {
            "section_id": "vent",
            "unit_id": "vent-02",
            "file": "notes.txt",
            "quote": "The unit shakes",
            "reason": "quote not found in source",
        },
        {
            "section_id": "vent",
            "unit_id": "vent-03",
            "file": "unknown.txt",
            "quote": "Design life 25 years",
            "reason": "file is not a source",
        },
    ]


def test_verify_attributes_duplicate_unit_ids_to_their_own_section(client):
    bad = _unit("x-01", "The unit shakes")
    good = _unit("x-01", "The housing is rusty.")
    body = _verify(
        client,
        {
            **NORMALIZED,
            "knowledge/a.json": _knowledge(good, section_id="a"),
            "knowledge/b.json": _knowledge(bad, section_id="b"),
        },
    ).json()

    assert [f["section_id"] for f in body["failures"]] == ["b"]


@pytest.mark.parametrize(
    "files, message",
    [
        ({**NORMALIZED}, "No knowledge files"),
        ({**NORMALIZED, "knowledge/vent.json": "{"}, "knowledge/vent.json is not valid knowledge"),
        (
            {**NORMALIZED, "knowledge/vent.json": '{"section_id": "vent"}'},
            "knowledge/vent.json is not valid knowledge",
        ),
        ({"knowledge/vent.json": _knowledge()}, "sources.json is missing"),
        ({**NORMALIZED, "report/report.md": "x"}, "not allowed"),
    ],
)
def test_bad_verify_requests_are_400(client, files, message):
    response = _verify(client, files)

    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_an_older_gaik_without_dropped_facts_still_curates(client, monkeypatch):
    """gaik 0.8.2 has no KnowledgeBase.dropped: the result reports an empty list."""
    from types import SimpleNamespace

    class OldCurator(FakeCurator):
        def curate(self, sources, sections, *, instructions, progress_callback):
            knowledge = super().curate(
                sources, sections, instructions=instructions, progress_callback=progress_callback
            )
            return SimpleNamespace(sections=knowledge.sections, usage=knowledge.usage)

    class OldGaik(FakeGaik):
        KnowledgeCurator = OldCurator

    monkeypatch.setattr(route, "_gaik", lambda: OldGaik)
    result = _events(_run(client))[-1]

    assert result[0] == "result"
    assert result[1]["dropped"] == []
    assert sorted(result[1]["artifacts"]) == ["knowledge/roof.json", "knowledge/vent.json"]
