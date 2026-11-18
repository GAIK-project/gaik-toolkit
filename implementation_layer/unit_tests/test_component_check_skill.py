"""Offline checks of the component-check skill's runner and of its cases."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude/skills/component-check"


def _load_runner():
    spec = importlib.util.spec_from_file_location("component_check_runner", SKILL / "run_checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc = _load_runner()
CASES = json.loads((SKILL / "cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (551.57, "551,57"),
        (1234.5, "1 234,50"),
        (1250.0, "1,250.00"),
        (1250.0, "1.250,00 EUR"),
        (18.9, "18.90"),
        (2, 2),
        ("2026-03-14", "2026-03-14"),
        ("2026-03-14", dt.date(2026, 3, 14)),
        ("Esimerkki Oy", " esimerkki  OY "),
        (None, None),
    ],
)
def test_a_matching_value_is_accepted(expected, actual):
    assert rc.compare_value(expected, actual) == (True, "")


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (551.57, "439,50"),
        (551.57, None),
        (2, True),
        ("2026-03-14", "2026-03-28"),
        ("2026-03-14", "14.3.2026"),
        ("EUR", "USD"),
        (None, "x"),
    ],
)
def test_a_wrong_value_is_reported_with_both_sides(expected, actual):
    ok, detail = rc.compare_value(expected, actual)
    assert not ok
    assert repr(expected) in detail


def test_records_are_compared_by_count_and_value():
    expect = {"records": [{"a": "x", "n": 1.5}]}
    assert rc.check_extraction(expect, [{"a": "X", "n": "1,50"}]) == []
    problems = rc.check_extraction(expect, [{"a": "y", "n": 1.5}, {"a": "x"}])
    assert "expected 1 record(s), got 2" in problems
    assert any(p.startswith("record[0].a:") for p in problems)


def test_a_records_wrapper_is_unwrapped():
    assert rc.to_records({"records": [{"a": 1}]}) == [{"a": 1}]
    assert rc.to_records({"a": 1, "items": [{"b": 2}]}) == [{"a": 1, "items": [{"b": 2}]}]


def test_nested_items_are_found_and_a_renamed_list_is_reported():
    expect = {"parent": {"id": "A"}, "items_key": "line_items", "items": [{"q": 2}]}
    assert rc.check_extraction(expect, [{"id": "A", "line_items": [{"q": 2}]}]) == []
    problems = rc.check_extraction(expect, [{"id": "A", "rows": [{"q": 2}]}])
    assert problems == ["items came under 'rows', not 'line_items'"]
    missing = rc.check_extraction(expect, [{"id": "A", "rows": []}])
    assert missing[-1] == "no list of items under 'line_items'"


def _observed(fields, structure="flat", children=None):
    return {
        "structure_type": structure,
        "fields": {n: {"type": t, "enum": e, "format": None} for n, (t, e) in fields.items()},
        "children": {
            name: {n: {"type": t, "enum": None, "format": None} for n, t in kids.items()}
            for name, kids in (children or {}).items()
        },
    }


def test_schema_checks_names_types_enums_and_extra_fields():
    expect = {
        "structure_type": "flat",
        "fields": {"a": ["str"], "d": ["date"]},
        "exact_fields": True,
        "enums": {"a": ["EUR", "USD"]},
    }
    good = _observed({"a": ("str", ["usd", "eur"]), "d": ("date", None)})
    assert rc.check_schema(expect, good) == []
    bad = _observed({"a": ("str", ["EUR"]), "d": ("str", None), "x": ("int", None)})
    problems = rc.check_schema(expect, bad)
    assert any("d: type 'str'" in p for p in problems)
    assert any("unexpected field(s) ['x']" in p for p in problems)
    assert any("enum ['EUR']" in p for p in problems)


def test_a_nested_schema_needs_its_child_list():
    expect = {
        "structure_type": "parent_with_nested_list",
        "child_container": "line_items",
        "child_fields": {"q": ["int"]},
    }
    good = _observed({}, "parent_with_nested_list", {"line_items": {"q": "int"}})
    assert rc.check_schema(expect, good) == []
    flat = _observed({}, "flat", {"rows": {"q": "int"}})
    problems = rc.check_schema(expect, flat)
    assert any("structure 'flat'" in p for p in problems)
    assert any("no child list 'line_items'" in p for p in problems)


def test_the_judge_gets_no_api_key_but_keeps_its_login():
    environ = {
        "PATH": "/bin",
        "HOME": "/home/x",
        "ANTHROPIC_API_KEY": "a",
        "ANTHROPIC_BASE_URL": "https://gateway",
        "OPENAI_API_KEY": "b",
        "CODEX_API_KEY": "c",
        "GEMINI_API_KEY": "d",
        "GOOGLE_API_KEY": "e",
        "AZURE_API_KEY": "f",
        "AZURE_ENDPOINT": "https://x",
        "AITTA_API_TOKEN": "g",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "GOOGLE_APPLICATION_CREDENTIALS": "/k.json",
        "CLAUDE_CODE_OAUTH_TOKEN": "subscription",
    }
    kept = rc.judge_env(environ)
    assert kept == {"PATH": "/bin", "HOME": "/home/x", "CLAUDE_CODE_OAUTH_TOKEN": "subscription"}


def test_secrets_are_redacted_from_errors():
    secrets = rc.secret_values({"AZURE_API_KEY": "abcdefgh12345", "PATH": "/usr/bin/longpath"})
    assert secrets == ["abcdefgh12345"]
    text = "key abcdefgh12345 and sk-abcdefghijklmnopqrstu and Bearer abcdefghijklmnop"
    assert rc.redact(text, secrets) == "key *** and *** and ***"


def test_model_precedence():
    env = {"CHECK_AZURE_MODEL": "check", "RELEASE_AZURE_MODEL": "release"}
    assert rc.model_for("azure", {"azure": "flag"}, env) == "flag"
    assert rc.model_for("azure", {}, env) == "check"
    assert rc.model_for("azure", {}, {"RELEASE_AZURE_MODEL": "release"}) == "release"
    assert rc.model_for("azure", {}, {}) is None
    assert rc.vision_model_for("azure", "m", {"CHECK_AZURE_VISION_MODEL": "v"}) == "v"
    assert rc.vision_model_for("azure", "m", {}) == "m"


def test_a_chosen_extraction_case_brings_its_schema_case():
    args = rc.parse_args(["--only", "vision-invoice-lines"])
    assert [c["id"] for c in rc.select_cases(args)] == [
        "schema-invoice-lines",
        "vision-invoice-lines",
    ]


def test_the_run_folder_must_be_outside_the_repository():
    with pytest.raises(SystemExit, match="outside the repository"):
        rc.main(["--out", str(ROOT / "component-check-out")])


@pytest.mark.parametrize("kind", ["claude", "codex", "agy"])
def test_each_judge_runs_without_tools_and_with_the_schema(kind, monkeypatch, tmp_path):
    monkeypatch.setattr(rc.shutil, "which", lambda name: f"/bin/{name}")
    cmd, stdin = rc.judge_command(kind, "m", tmp_path, "PROMPT")
    joined = " ".join(cmd)
    if kind == "claude":
        assert cmd[cmd.index("--tools") + 1] == "" and "--json-schema" in cmd
        assert stdin == "PROMPT"
    elif kind == "codex":
        assert "--sandbox read-only" in joined and (tmp_path / "schema.json").is_file()
        assert cmd[-1] == "-" and stdin == "PROMPT"
    else:
        assert "--mode plan" in joined and "--sandbox" in cmd and "--output-format json" in joined
        assert cmd[cmd.index("-p") + 1] == "PROMPT" and stdin is None
    assert "m" in cmd


def test_every_case_is_consistent_with_its_fixtures():
    ids = {c["id"]: c for c in CASES}
    assert len(ids) == len(CASES), "case ids must be unique"
    for case in CASES:
        assert case["component"] in rc.COMPONENTS
        assert case.get("rubric"), case["id"]
        if case["component"] == "schema_generator":
            assert case["requirements"] and case["expect"].get("fields") is not None
            continue
        parent = ids[case["schema_from"]]
        assert parent["component"] == "schema_generator", case["id"]
        sources = case.get("documents") or [case["source_text"]]
        text = "\n".join((SKILL / p).read_text(encoding="utf-8") for p in sources)
        for path in case.get("files", []):
            assert (SKILL / path).is_file(), path
        # Every expected string is written in the inputs, so a case cannot expect an
        # invented value; numbers and dates are written in their local form there.
        expect = case["expect"]
        records = expect.get("records", []) + [expect.get("parent", {})] + expect.get("items", [])
        named = set(parent["expect"].get("fields", {})) | set(
            parent["expect"].get("child_fields", {})
        )
        for record in records:
            for name, value in record.items():
                assert name in named, f"{case['id']}: {name} is not in {parent['id']}"
                if isinstance(value, str) and not rc._DATE.match(value):
                    assert value in text, f"{case['id']}: {value!r} is not in its input"


def test_the_fixtures_are_synthetic():
    text = (SKILL / "fixtures/invoice-fi.txt").read_text(encoding="utf-8")
    # The business ID's check digit is deliberately wrong (the right one is 1).
    digits = [int(d) for d in "1234567"]
    remainder = sum(d * w for d, w in zip(digits, (7, 9, 10, 5, 8, 4, 2))) % 11
    assert "1234567-8" in text and str(11 - remainder) != "8"


def test_the_baseline_reports_a_lost_pass_but_not_a_decimal_read_back_as_text():
    from decimal import Decimal

    def run(status, output):
        return {"providers": {"azure": {"cases": {"c": {"status": status, "output": output}}}}}

    baseline = run("pass", [{"total": "551.57"}])
    assert rc.diff_baseline(run("pass", [{"total": Decimal("551.57")}]), baseline) == []
    notes = rc.diff_baseline(run("fail", [{"total": "439.50"}]), baseline)
    assert notes == [
        "azure / c: was pass, now fail",
        "azure / c: output differs from the baseline",
    ]


def test_codex_judges_with_gpt_6_2_sol_unless_told_otherwise():
    assert rc.DEFAULT_JUDGE_MODELS["codex"] == "gpt-6.2-sol"
    assert rc.parse_args(["--judge", "codex"]).judge_model in (None, "")
    assert "claude" not in rc.DEFAULT_JUDGE_MODELS and "agy" not in rc.DEFAULT_JUDGE_MODELS
