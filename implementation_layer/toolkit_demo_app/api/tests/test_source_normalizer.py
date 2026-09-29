"""Source Normalizer endpoint: a fake SourceNormalizer stands in for gaik's, so no test
calls a model; the real NormalizedSources writes the files the endpoint returns."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from api.routers import source_normalizer as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_components.source_normalizer import NormalizedSource, NormalizedSources

CONFIG = {"provider": "fake", "model": "fake-model"}
FILES = [("notes.txt", b"Meeting notes"), ("budget.csv", b"item,cost\nroof,100\n")]
MANIFEST = {
    "sources": [
        {"name": "notes.txt", "source_class": "primary"},
        {"name": "budget.csv", "source_class": "secondary"},
    ]
}
CALLS: list[dict] = []


class FakeNormalizer:
    def __init__(self, config, **options) -> None:
        assert config is CONFIG
        self.options = options

    def normalize(self, groups, *, progress_callback):
        CALLS.append(
            {"groups": {k: [p.name for p in v] for k, v in groups.items()}, **self.options}
        )
        items = [(cls, p) for cls, paths in groups.items() for p in paths]
        sources = []
        for i, (cls, path) in enumerate(items, start=1):
            progress_callback(f"Normalizing {path.name} ({i}/{len(items)})")
            if path.name == "broken.pdf":
                raise ValueError("broken.pdf: PDF has no text layer")
            sources.append(
                NormalizedSource(
                    id=route_id(i, path.name),
                    file=path.name,
                    source_class=cls,
                    source_type="text",
                    tool="text",
                    text=path.read_text(encoding="utf-8"),
                )
            )
        return NormalizedSources(sources=sources, usage={"audio_seconds": 30})


def route_id(i: int, name: str) -> str:
    return f"{i:02d}_{Path(name).stem}"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    CALLS.clear()
    monkeypatch.setattr(route, "_gaik", lambda: FakeNormalizer)
    monkeypatch.setattr(route, "get_api_config", lambda: CONFIG)
    app = FastAPI()
    app.include_router(route.router, prefix="/source-normalizer")
    return TestClient(app)


def _run(client, manifest=MANIFEST, files=FILES):
    return client.post(
        "/source-normalizer/run",
        data={"manifest": manifest if isinstance(manifest, str) else json.dumps(manifest)},
        files=[("files", f) for f in files],
    )


def _events(response) -> list[tuple[str, dict]]:
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.split("\n\n"):
        if block.startswith("event: "):
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_run_returns_the_saved_files_and_usage(client):
    events = _events(_run(client))

    assert [name for name, _ in events] == ["progress", "progress", "result"]
    assert events[0][1]["message"] == "Normalizing notes.txt (1/2)"
    result = events[-1][1]
    assert sorted(result["artifacts"]) == [
        "normalized/01_notes.md",
        "normalized/02_budget.md",
        "normalized/sources.json",
    ]
    assert result["artifacts"]["normalized/01_notes.md"] == "Meeting notes"
    manifest = json.loads(result["artifacts"]["normalized/sources.json"])
    assert [(s["file"], s["source_class"]) for s in manifest] == [
        ("notes.txt", "primary"),
        ("budget.csv", "secondary"),
    ]
    assert "text" not in manifest[0]
    assert result["usage"] == {"audio_seconds": 30}


def test_files_are_grouped_by_class_and_options_reach_the_normalizer(client):
    manifest = {
        "sources": [
            {"name": "budget.csv", "source_class": "secondary"},
            {"name": "notes.txt", "source_class": "primary"},
        ],
        "options": {"transcription_model": "gpt-4o-transcribe", "language": "fi"},
    }
    _events(_run(client, manifest, files=[FILES[1], FILES[0]]))

    assert CALLS == [
        {
            "groups": {"primary": ["notes.txt"], "secondary": ["budget.csv"]},
            "vision_model": None,
            "transcription_model": "gpt-4o-transcribe",
            "language": "fi",
        }
    ]


def test_a_failing_file_is_an_error_event_naming_it(client):
    manifest = {"sources": [{"name": "broken.pdf", "source_class": "primary"}]}
    events = _events(_run(client, manifest, files=[("broken.pdf", b"%PDF")]))

    assert events[-1][0] == "error"
    assert "broken.pdf: PDF has no text layer" in events[-1][1]["message"]


def test_the_temp_folder_is_removed(client, monkeypatch):
    seen: list[Path] = []
    original = route.tempfile.mkdtemp

    def spy(*args, **kwargs):
        seen.append(Path(original(*args, **kwargs)))
        return str(seen[-1])

    monkeypatch.setattr(route.tempfile, "mkdtemp", spy)
    _events(_run(client))

    assert len(seen) == 1 and not seen[0].exists()


@pytest.mark.parametrize(
    "manifest, files, message",
    [
        ("not json", FILES, "Invalid manifest"),
        ({"sources": []}, FILES, "Invalid manifest"),
        ({**MANIFEST, "extra": 1}, FILES, "Invalid manifest"),
        (
            {"sources": [{"name": "../x.txt", "source_class": "primary"}]},
            [("x.txt", b"x")],
            "not paths",
        ),
        (
            {
                "sources": [
                    {"name": "a.txt", "source_class": "primary"},
                    {"name": "a.txt", "source_class": "secondary"},
                ]
            },
            [("a.txt", b"x"), ("a.txt", b"y")],
            "distinct",
        ),
        (MANIFEST, FILES[:1], "expected 2, got 1"),
    ],
)
def test_bad_requests_are_400(client, manifest, files, message):
    response = _run(client, manifest, files)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert not CALLS
