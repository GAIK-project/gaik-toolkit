"""Upload file names stay out of the logs; a tag follows one upload instead."""

from __future__ import annotations

import logging

import pytest
from api.utils.log_names import file_tag


def test_a_tag_keeps_the_extension_and_hides_the_name():
    tag = file_tag("Matti_Virtanen_lab_results.PDF")

    assert tag.startswith("upload ") and tag.endswith(".pdf")
    assert "Matti" not in tag and "Virtanen" not in tag
    assert len(tag) == len("upload 12345678.pdf")


def test_the_same_name_gets_the_same_tag_and_another_name_another():
    assert file_tag("a/b/report.docx") == file_tag("a/b/report.docx")
    assert file_tag("report.docx") != file_tag("report2.docx")


@pytest.mark.parametrize("name", [None, ""])
def test_no_name_is_just_upload(name):
    assert file_tag(name) == "upload"


@pytest.mark.parametrize(
    "name", ["notes", "x.tar.gz;rm -rf", "evil.<script>", "Virtanen.Matti", "J.Doe", "a.äöå"]
)
def test_only_a_known_file_type_is_kept_as_the_extension(name):
    tag = file_tag(name)

    assert "." not in tag  # the part after the last dot may be part of the name


def test_error_kind_keeps_the_http_status_and_drops_the_message():
    from types import SimpleNamespace

    from api.utils.log_names import error_kind

    class HTTPError(Exception):
        pass

    failed = HTTPError("401 for Matti_Virtanen.pdf")
    failed.response = SimpleNamespace(status_code=401)

    assert error_kind(failed) == "HTTPError (HTTP 401)"
    assert error_kind(ValueError("could not convert 'Matti'")) == "ValueError"


def test_gaiks_tabular_loader_does_not_log_at_info_in_the_api():
    import api.main  # noqa: F401 - sets the logger levels

    loader = logging.getLogger("gaik.software_components.tabular_agent.loader")
    assert not loader.isEnabledFor(logging.INFO)


def test_the_tabular_route_logs_its_upload_by_tag(monkeypatch, tmp_path, caplog):
    # The component's own loader is replaced here; its log level is checked above.
    import asyncio

    from api.routers import tabular_agent as route
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(route, "_SESSIONS", {})
    monkeypatch.setattr(route, "_SESSIONS_LOCK", asyncio.Lock())
    monkeypatch.setattr(route.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(route, "_load_agent", lambda path, layout: (object(), [], "schema"))
    app = FastAPI()
    app.include_router(route.router, prefix="/tabular-agent")

    with caplog.at_level(logging.INFO):
        response = TestClient(app).post(
            "/tabular-agent/upload",
            files={"file": ("Matti_Virtanen_salaries.csv", b"a,b\n1,2\n", "text/csv")},
        )

    assert response.status_code == 200, response.text
    assert "loaded upload " in caplog.text
    assert "Matti" not in caplog.text and "Virtanen" not in caplog.text
