"""Knowledge Synthesis endpoints: a fake ReportSynthesizer stands in for gaik's, so no test
calls a model; gaik's real models validate the sections, the knowledge and the report."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from api.routers import knowledge_synthesis as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_components import knowledge_curator as kc
from gaik.software_components.draft_reviewer.models import Edit
from gaik.software_components.knowledge_curator import FactUnit, SectionKnowledge, SourceRef
from gaik.software_components.report_synthesizer import Report, ReportSection
from gaik.software_components.report_synthesizer.models import ReviewEntry

CONFIG = {"provider": "fake", "model": "fake-model"}
CALLS: list[dict] = []
UNIT = FactUnit(
    id="vent-01",
    topic="t",
    time_qualifier=None,
    summary="A fact.",
    quote="The unit vibrates.",
    source=SourceRef(file="notes.txt", locator=None),
    source_class="primary",
    confidence="high",
)
KNOWLEDGE = {
    "knowledge/vent.json": SectionKnowledge(
        section_id="vent", units=[UNIT], missing=["age"], conflicts=[]
    ).model_dump_json(),
}
REQUEST = {
    "title": "Site report",
    "language": "Finnish",
    "instructions": "Cite files.",
    "sections": [
        {"id": "sum", "title": "Summary", "depends_on": ["vent"]},
        {"id": "vent", "title": "Ventilation", "required_items": ["age"]},
    ],
    "options": {
        "writer_model": "wr",
        "reviewer_model": "rev",
        "writer_effort": "low",
        "review_attempts": 2,
        "strict_review": True,
        "citations": False,
    },
}
FIX = Edit(search="DRAFT", replace="REVIEWED", reason="fix")


class FakeSynthesizer:
    def __init__(
        self,
        config,
        model=None,
        *,
        reviewer_model=None,
        strict_review=False,
        review_attempts=5,
        writer_options=None,
        reviewer_options=None,
        citations=True,
    ) -> None:
        assert config is CONFIG
        self.model = model
        self.kwargs = {
            "reviewer_model": reviewer_model,
            "strict_review": strict_review,
            "review_attempts": review_attempts,
            "writer_options": writer_options,
            "reviewer_options": reviewer_options,
            "citations": citations,
        }

    def synthesize(
        self,
        knowledge,
        sections,
        *,
        title,
        language,
        instructions,
        sample_report,
        progress_callback,
    ):
        CALLS.append(
            {
                "model": self.model,
                **self.kwargs,
                "knowledge": [k.section_id for k in knowledge.sections],
                "sections": [(s.id, s.derived) for s in sections],
                "title": title,
                "language": language,
                "instructions": instructions,
                "sample": sample_report,
            }
        )
        for s in sections:
            progress_callback(f"Writing {s.title}")
        if title == "boom":
            raise ValueError("Knowledge for unknown, derived or duplicate sections: ['x']")
        return Report(
            title=title,
            sections=[
                ReportSection(id=s.id, title=s.title, text=f"Body of {s.id}.") for s in sections
            ],
            review_log=[
                ReviewEntry(section_id=s.id, applied=[FIX], unresolved=[]) for s in sections
            ],
            usage={"total_tokens": 42},
        )


class OldSynthesizer(FakeSynthesizer):
    """gaik 0.8.2: no `citations` option, and it always cites."""

    def __init__(
        self,
        config,
        model=None,
        *,
        reviewer_model=None,
        strict_review=False,
        review_attempts=5,
        writer_options=None,
        reviewer_options=None,
    ) -> None:
        super().__init__(
            config,
            model,
            reviewer_model=reviewer_model,
            strict_review=strict_review,
            review_attempts=review_attempts,
            writer_options=writer_options,
            reviewer_options=reviewer_options,
        )
        self.kwargs.pop("citations")


class FakeNormalizer:
    def to_markdown(self, path):
        CALLS.append({"converted": path.suffix})
        return "# Converted sample"


class FakeGaik:
    """The real gaik models with the synthesizer and the normalizer replaced."""

    KnowledgeBase = kc.KnowledgeBase
    SectionKnowledge = kc.SectionKnowledge
    SectionSpec = kc.SectionSpec
    Report = Report
    ReportSection = ReportSection
    ReportSynthesizer = FakeSynthesizer
    SourceNormalizer = FakeNormalizer


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    CALLS.clear()
    monkeypatch.setattr(route, "_gaik", lambda: FakeGaik)
    monkeypatch.setattr(route, "get_api_config", lambda: CONFIG)
    monkeypatch.setattr(route, "_docx", lambda report: b"PK docx bytes")
    app = FastAPI()
    app.include_router(route.router, prefix="/knowledge-synthesis")
    return TestClient(app)


def _run(client, request=REQUEST, artifacts=KNOWLEDGE, sample=None):
    files = [("artifacts", ("artifacts.json", json.dumps(artifacts).encode()))]
    if sample:
        files.append(("sample_report", sample))
    return client.post(
        "/knowledge-synthesis/run",
        data={"request": request if isinstance(request, str) else json.dumps(request)},
        files=files,
    )


def _events(response) -> list[tuple[str, dict]]:
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.split("\n\n"):
        if block.startswith("event: "):
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


# ---------------------------------------------------------------------------
# /run
# ---------------------------------------------------------------------------


def test_run_returns_the_report_review_log_usage_and_docx(client):
    events = _events(_run(client))

    assert [name for name, _ in events] == ["progress", "progress", "result"]
    result = events[-1][1]
    assert result["title"] == "Site report"
    assert (
        result["markdown"]
        == "# Site report\n\n## Summary\n\nBody of sum.\n\n## Ventilation\n\nBody of vent.\n"
    )
    assert [(s["id"], s["text"]) for s in result["sections"]] == [
        ("sum", "Body of sum."),
        ("vent", "Body of vent."),
    ]
    assert result["review_log"][0] == {
        "section_id": "sum",
        "applied": [FIX.model_dump()],
        "unresolved": [],
    }
    assert result["usage"] == {"total_tokens": 42}
    assert base64.b64decode(result["docx_b64"]) == b"PK docx bytes"
    assert result["docx_error"] is None


def test_run_passes_sections_options_and_knowledge_to_the_synthesizer(client):
    _events(_run(client))

    assert CALLS == [
        {
            "model": "wr",
            "reviewer_model": "rev",
            "strict_review": True,
            "review_attempts": 2,
            "writer_options": {"reasoning_effort": "low"},
            "reviewer_options": {},
            "citations": False,
            "knowledge": ["vent"],
            "sections": [("sum", True), ("vent", False)],
            "title": "Site report",
            "language": "Finnish",
            "instructions": "Cite files.",
            "sample": None,
        }
    ]


def test_options_default_to_citations_on_and_docx_on(client):
    request = {**REQUEST, "options": {}}
    result = _events(_run(client, request))[-1][1]

    assert CALLS[0]["citations"] is True
    assert CALLS[0]["strict_review"] is False and CALLS[0]["review_attempts"] == 5
    assert result["docx_b64"] is not None


def test_docx_can_be_switched_off(client):
    request = {**REQUEST, "options": {"docx": False}}
    result = _events(_run(client, request))[-1][1]

    assert result["docx_b64"] is None and result["docx_error"] is None


def test_a_docx_failure_keeps_the_report(client, monkeypatch):
    def broken(report):
        raise OSError("No pandoc executable found")

    monkeypatch.setattr(route, "_docx", broken)
    result = _events(_run(client))[-1][1]

    assert result["docx_b64"] is None
    assert "No pandoc executable found" in result["docx_error"]
    assert result["markdown"].startswith("# Site report")


@pytest.mark.parametrize(
    "name, data, converted",
    [
        ("format.md", b"# Sample\n\nText.", None),
        ("format.txt", "Öljy".encode("utf-8-sig"), None),
        ("format.docx", b"PK", ".docx"),
    ],
)
def test_the_sample_report_reaches_the_synthesizer(client, name, data, converted):
    _events(_run(client, sample=(name, data)))

    sample = next(c["sample"] for c in CALLS if "sample" in c)
    if converted:
        assert {"converted": converted} in CALLS
        assert sample == "# Converted sample"
    else:
        assert sample == data.decode("utf-8-sig")


def test_a_synthesizer_error_is_an_error_event(client):
    events = _events(_run(client, {**REQUEST, "title": "boom"}))

    assert events[-1][0] == "error"
    assert "Knowledge for unknown, derived or duplicate sections" in events[-1][1]["message"]


@pytest.mark.parametrize(
    "request_body, artifacts, sample, message",
    [
        ("not json", KNOWLEDGE, None, "Invalid request"),
        ({**REQUEST, "sections": []}, KNOWLEDGE, None, "Invalid request"),
        ({**REQUEST, "extra": 1}, KNOWLEDGE, None, "Invalid request"),
        ({**REQUEST, "options": {"review_attempts": 99}}, KNOWLEDGE, None, "Invalid request"),
        ({**REQUEST, "options": {"writer_effort": "loud"}}, KNOWLEDGE, None, "Invalid request"),
        (
            {**REQUEST, "sections": [{"id": "a b", "title": "T"}]},
            KNOWLEDGE,
            None,
            "Invalid request",
        ),
        (
            {**REQUEST, "sections": [{"id": "a", "title": "A"}, {"id": "a", "title": "B"}]},
            KNOWLEDGE,
            None,
            "must be distinct",
        ),
        (REQUEST, {}, None, "curate knowledge in the Knowledge Curator first"),
        (REQUEST, {"normalized/a.md": "x"}, None, "not allowed"),
        (REQUEST, {"knowledge/vent.json": "{"}, None, "knowledge/vent.json is not valid knowledge"),
        (
            REQUEST,
            {"knowledge/vent.json": '{"section_id": "vent"}'},
            None,
            "is not valid knowledge",
        ),
        (REQUEST, KNOWLEDGE, ("format.exe", b"MZ"), "must be one of"),
        (REQUEST, KNOWLEDGE, ("format.md", b"\xff\xfe\x00"), "not UTF-8"),
    ],
)
def test_bad_run_requests_are_400(client, request_body, artifacts, sample, message):
    response = _run(client, request_body, artifacts, sample)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert not [c for c in CALLS if "sections" in c]


# ---------------------------------------------------------------------------
# /rebuild
# ---------------------------------------------------------------------------


def _rebuild(client, body):
    return client.post(
        "/knowledge-synthesis/rebuild",
        data={"request": body if isinstance(body, str) else json.dumps(body)},
    )


REBUILD = {
    "title": "Site report",
    "sections": [
        {"id": "a", "title": "A", "text": "Edited text.\n"},
        {"id": "b", "title": "B", "text": "Two."},
    ],
}


def test_rebuild_reassembles_the_markdown_and_the_docx(client):
    body = _rebuild(client, REBUILD).json()

    assert body["markdown"] == "# Site report\n\n## A\n\nEdited text.\n\n## B\n\nTwo.\n"
    assert base64.b64decode(body["docx_b64"]) == b"PK docx bytes"
    assert body["docx_error"] is None


def test_rebuild_without_docx_and_with_a_docx_failure(client, monkeypatch):
    assert _rebuild(client, {**REBUILD, "docx": False}).json()["docx_b64"] is None

    def broken(report):
        raise RuntimeError("pandoc missing")

    monkeypatch.setattr(route, "_docx", broken)
    body = _rebuild(client, REBUILD).json()
    assert body["docx_b64"] is None and "pandoc missing" in body["docx_error"]
    assert body["markdown"].startswith("# Site report")


@pytest.mark.parametrize(
    "body, message",
    [
        ("{", "Invalid request"),
        ({**REBUILD, "sections": []}, "Invalid request"),
        ({**REBUILD, "sections": [{"id": "x y", "title": "T", "text": ""}]}, "Invalid request"),
        (
            {
                **REBUILD,
                "sections": [
                    {"id": "a", "title": "A", "text": "1"},
                    {"id": "a", "title": "B", "text": "2"},
                ],
            },
            "must be distinct",
        ),
    ],
)
def test_bad_rebuild_requests_are_400(client, body, message):
    response = _rebuild(client, body)

    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_a_docx_conversion_is_run_by_gaik_when_not_faked():
    """The real _docx writes through Report.save: a stand-in report proves the wiring."""
    saved = {}

    class Recorder:
        def save(self, directory, *, docx):
            saved["docx"] = docx
            path = directory / "report.docx"
            path.write_bytes(b"real docx")
            return SimpleNamespace(**{}) if False else {"docx": path}

    assert route._docx(Recorder()) == b"real docx"
    assert saved == {"docx": True}


# ---------------------------------------------------------------------------
# An older gaik release, as the deployed image installs it
# ---------------------------------------------------------------------------


@pytest.fixture
def old_gaik(monkeypatch):
    class OldGaik(FakeGaik):
        ReportSynthesizer = OldSynthesizer

    monkeypatch.setattr(route, "_gaik", lambda: OldGaik)


def test_an_older_gaik_writes_reports_with_citations_on(client, old_gaik):
    request = {**REQUEST, "options": {"citations": True}}
    result = _events(_run(client, request))[-1]

    assert result[0] == "result"
    assert "citations" not in CALLS[0]  # the option is not passed to a release without it


def test_an_older_gaik_refuses_citations_off_with_a_clear_message(client, old_gaik):
    response = _run(client, {**REQUEST, "options": {"citations": False}})

    assert response.status_code == 400
    assert "cannot write a report without citations" in response.json()["detail"]
    assert not CALLS
