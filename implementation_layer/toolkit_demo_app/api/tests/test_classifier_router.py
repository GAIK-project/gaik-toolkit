"""The classify endpoint hands the chosen parser on to the component."""

from __future__ import annotations

import pytest
from api.routers import classifier as route
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch) -> TestClient:
    seen: dict = {}

    class FakeClassifier:
        def __init__(self, config):
            pass

        def classify(self, file_or_dir, classes, parser=None):
            seen.update(classes=classes, parser=parser)
            from pathlib import Path

            return {
                Path(file_or_dir).name: {"class": classes[0], "confidence": 0.9, "reasoning": "x"}
            }

    monkeypatch.setattr(
        "gaik.software_components.doc_classifier.DocumentClassifier", FakeClassifier
    )
    monkeypatch.setattr(route, "get_api_config", lambda: {"model": "m"})
    app = FastAPI()
    app.include_router(route.router, prefix="/classify")
    test_client = TestClient(app)
    test_client.seen = seen  # type: ignore[attr-defined]
    return test_client


@pytest.mark.parametrize("parser, expected", [("vision", "vision"), ("auto", None)])
def test_parser_choice_reaches_the_classifier(client, parser, expected) -> None:
    response = client.post(
        "/classify",
        files={"file": ("scan.png", b"not really a png", "image/png")},
        data={"classes": "invoice,receipt", "parser": parser},
    )

    assert response.status_code == 200
    assert response.json()["classification"] == "invoice"
    assert client.seen["parser"] == expected  # type: ignore[attr-defined]


def test_unknown_parser_is_rejected(client) -> None:
    response = client.post(
        "/classify",
        files={"file": ("a.pdf", b"x", "application/pdf")},
        data={"classes": "a,b", "parser": "magic"},
    )

    assert response.status_code == 422
