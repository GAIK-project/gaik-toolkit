"""The live smoke test's runner, checked without a model.

The checks themselves call a real model and run with ``python -m api.smoke``. These
tests keep the runner honest: every check is registered, a failure fails the run, a
retry is visible, and an unexpected error does not leak its message.
"""

import inspect

import pytest
from api import smoke
from api.main import app
from fastapi.testclient import TestClient


def test_every_check_function_is_registered_under_its_own_name():
    defined = {
        name.removeprefix("check_"): function
        for name, function in inspect.getmembers(smoke, inspect.isfunction)
        if name.startswith("check_")
    }

    assert smoke.CHECKS == defined
    assert all((function.__doc__ or name == "health") for name, function in defined.items())


def test_checks_that_need_no_model_pass_against_the_real_app():
    with TestClient(app) as client:
        report = smoke.run_checks(client, ["health", "parse_pdf"])

    assert [(entry["check"], entry["ok"], entry["attempts"]) for entry in report] == [
        ("health", True, 1),
        ("parse_pdf", True, 1),
    ]


def test_failed_check_is_retried_once_and_the_retry_shows_in_the_report(monkeypatch):
    calls = []

    def flaky(client):
        calls.append(1)
        if len(calls) == 1:
            raise AssertionError("first answer was short")
        return "fine"

    monkeypatch.setitem(smoke.CHECKS, "flaky", flaky)

    report = smoke.run_checks(None, ["flaky"])

    assert report[0]["ok"] is True
    assert report[0]["attempts"] == 2
    assert "(attempt 2)" in smoke.format_report(report)


def test_check_that_keeps_failing_fails_the_run_with_its_reason(monkeypatch):
    def broken(client):
        raise AssertionError("classification is 'contract'")

    monkeypatch.setitem(smoke.CHECKS, "broken", broken)

    report = smoke.run_checks(None, ["broken"])
    text = smoke.format_report(report)

    assert report[0]["ok"] is False
    assert report[0]["attempts"] == smoke.ATTEMPTS
    assert "FAIL  broken" in text
    assert "classification is 'contract'" in text
    assert "0 of 1 checks passed; failed: broken" in text


def test_unexpected_error_is_reported_by_type_without_its_message(monkeypatch):
    def crashing(client):
        raise RuntimeError("provider said: key sk-secret is invalid")

    monkeypatch.setitem(smoke.CHECKS, "crashing", crashing)

    report = smoke.run_checks(None, ["crashing"])

    assert report[0]["ok"] is False
    assert report[0]["detail"] == "RuntimeError raised"
    assert "sk-secret" not in smoke.format_report(report)


def test_list_prints_the_check_names_and_an_unknown_name_is_refused(capsys):
    assert smoke.main(["--list"]) == 0
    assert capsys.readouterr().out.split() == list(smoke.CHECKS)

    assert smoke.main(["--only", "extract,nope"]) == 2
    assert "Unknown checks: nope" in capsys.readouterr().out


@pytest.mark.parametrize(("failing", "expected"), [(False, 0), (True, 1)])
def test_exit_code_follows_the_checks(monkeypatch, failing, expected):
    def only_check(client):
        if failing:
            raise AssertionError("no")
        return "yes"

    monkeypatch.setattr(smoke, "CHECKS", {"only": only_check})

    assert smoke.main([]) == expected
