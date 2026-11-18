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
        if case["component"] not in rc.SCHEMA_CONSUMERS:
            continue  # checked in test_the_new_component_cases_match_their_fixtures
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


def test_line_items_need_one_parent_record():
    expect = {"parent": {"id": "A"}, "items_key": "line_items", "items": [{"q": 2}]}
    flat_rows = [{"id": "A", "q": 2}, {"id": "A", "q": 3}]
    assert rc.check_extraction(expect, flat_rows) == ["expected 1 parent record, got 2"]
    two_parents = [{"id": "A", "line_items": [{"q": 2}]}, {"id": "B", "line_items": []}]
    assert rc.check_extraction(expect, two_parents) == ["expected 1 parent record, got 2"]


def _json_schema(currency_enum=("EUR", "USD"), lines_type="array"):
    return {
        "$defs": {"Line": {"properties": {"q": {"type": "integer"}}, "type": "object"}},
        "properties": {
            "total": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "currency": {
                "anyOf": [{"enum": list(currency_enum), "type": "string"}, {"type": "null"}]
            },
            "line_items": {"type": lines_type, "items": {"$ref": "#/$defs/Line"}},
        },
        "type": "object",
    }


def test_the_generated_model_is_checked_as_well_as_its_requirements():
    expect = {
        "fields": {"total": ["decimal"], "currency": ["str"]},
        "enums": {"currency": ["EUR", "USD"]},
        "child_container": "line_items",
        "child_fields": {"q": ["int"]},
    }
    assert rc.check_model(expect, _json_schema()) == []
    problems = rc.check_model(
        {**expect, "fields": {**expect["fields"], "date": ["date"]}},
        _json_schema(currency_enum=("EUR",), lines_type="object"),
    )
    assert any("no property 'date'" in p for p in problems)
    assert any("model.currency: allows ['EUR']" in p for p in problems)
    assert any("'line_items' is not a list" in p for p in problems)


def test_cases_are_checked_and_schema_cases_run_first():
    schema = {"id": "s", "component": "schema_generator"}
    extract = {"id": "e", "component": "extractor", "schema_from": "s"}
    assert [c["id"] for c in rc.check_cases([extract, schema])] == ["s", "e"]
    with pytest.raises(SystemExit, match="appears twice"):
        rc.check_cases([schema, dict(schema)])
    with pytest.raises(SystemExit, match="is not a schema_generator case"):
        rc.check_cases([{"id": "e", "component": "extractor", "schema_from": "missing"}])
    with pytest.raises(SystemExit, match="component must be one of"):
        rc.check_cases([{"id": "x", "component": "parser"}])


def test_the_baseline_compares_the_schema_but_not_its_wording():
    def run(field_type, description):
        observed = {
            "structure_type": "flat",
            "fields": {"total": {"type": field_type, "enum": None, "description": description}},
            "children": {},
        }
        return {"providers": {"azure": {"cases": {"s": {"status": "pass", "observed": observed}}}}}

    baseline = run("decimal", "The total.")
    assert rc.diff_baseline(run("decimal", "Invoice total incl. VAT."), baseline) == []
    assert rc.diff_baseline(run("float", "The total."), baseline) == [
        "azure / s: schema differs from the baseline"
    ]


@pytest.mark.parametrize(
    ("kind", "output", "ok"),
    [
        (
            "claude",
            '{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "firstParty"}',
            True,
        ),
        (
            "claude",
            '{"loggedIn": true, "authMethod": "apiKeyHelper", "apiProvider": "firstParty"}',
            False,
        ),
        (
            "claude",
            '{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "bedrock"}',
            False,
        ),
        ("claude", '{"loggedIn": false}', False),
        ("claude", "not json", False),
        ("codex", "Logged in using ChatGPT", True),
        ("codex", "Logged in using an API key - sk-***", False),
        ("agy", "", True),
    ],
)
def test_a_judge_runs_only_on_a_subscription_login(kind, output, ok):
    assert (rc.login_problem(kind, output) is None) is ok


def test_a_public_run_keeps_no_provider_error_text():
    error = rc._error(RuntimeError("upstream said: request body ..."), [], public=True)
    assert error == {"error_type": "RuntimeError", "status_code": None, "message": ""}
    local = rc._error(RuntimeError("upstream said: x"), [])
    assert local["message"] == "upstream said: x"


def test_the_judge_does_not_inherit_the_nesting_markers():
    kept = rc.judge_env({"PATH": "/bin", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"})
    assert kept == {"PATH": "/bin"}


def test_the_models_empty_enum_value_is_not_a_difference():
    schema = _json_schema(currency_enum=("", "EUR", "USD"))
    expect = {"fields": {"currency": ["str"]}, "enums": {"currency": ["EUR", "USD"]}}
    assert rc.check_model(expect, schema) == []


# ---------------------------------------------------------------------------
# Schema structures and field rules
# ---------------------------------------------------------------------------


def _spec(name, field_type, **extra):
    from gaik.software_components.extractor import FieldSpec

    return FieldSpec(field_name=name, field_type=field_type, description=name, **extra)


def test_describe_requirements_keeps_the_list_name_defaults_and_nullability():
    from gaik.software_components.extractor import ExtractionRequirements

    requirements = ExtractionRequirements(
        use_case_name="inspection",
        fields=[
            _spec("comment", "str", default="not given", has_explicit_default=True),
            _spec("score", "int", nullable=True),
        ],
    )
    nested = rc.describe_requirements(requirements, "nested_list", "inventory_items")
    assert nested["container"] == "inventory_items"
    comment, score = nested["fields"]["comment"], nested["fields"]["score"]
    assert (comment["default"], comment["has_explicit_default"], comment["nullable"]) == (
        "not given",
        True,
        False,
    )
    assert score["nullable"] is True and score["default"] is None
    # Only a nested_list has a list name of its own.
    assert "container" not in rc.describe_requirements(requirements, "flat", "records")


def test_a_nested_list_schema_needs_its_list_name():
    expect = {
        "structure_type": "nested_list",
        "container": "inventory_items",
        "fields": {"quantity": ["int"]},
        "exact_fields": True,
    }
    good = {**_observed({"quantity": ("int", None)}, "nested_list"), "container": "inventory_items"}
    assert rc.check_schema(expect, good) == []
    renamed = {**good, "container": "items"}
    assert rc.check_schema(expect, renamed) == [
        "records listed under 'items', not 'inventory_items'"
    ]


def _nested_list_model(container="inventory_items"):
    """A nested_list model built the way gaik's parse_nested_requirements builds one."""
    from gaik.software_components.extractor import ExtractionRequirements, create_extraction_model
    from pydantic import Field, create_model

    item = create_extraction_model(
        ExtractionRequirements(
            use_case_name="inventory",
            fields=[
                _spec("product_name", "str"),
                _spec("category", "str", enum=["tools", "consumables"]),
            ],
        )
    )
    return create_model(
        "Inventory_Collection", **{container: (list[item], Field(description="items"))}
    )


def test_the_model_of_a_nested_list_is_checked_inside_its_list():
    expect = {
        "container": "inventory_items",
        "fields": {"product_name": ["str"], "category": ["str"]},
        "enums": {"category": ["tools", "consumables"]},
    }
    assert rc.check_model(expect, _nested_list_model().model_json_schema()) == []
    problems = rc.check_model(expect, _nested_list_model("records").model_json_schema())
    assert problems == ["model: 'inventory_items' is not a list (got records)"]
    wrong = {**expect, "fields": {"sku": ["str"]}, "enums": {"category": ["tools"]}}
    problems = rc.check_model(wrong, _nested_list_model().model_json_schema())
    assert any("model.inventory_items: no property 'sku'" in p for p in problems)
    assert any("model.inventory_items.category: allows" in p for p in problems)


def test_two_child_lists_are_checked_and_an_extra_one_is_reported():
    expect = {
        "structure_type": "parent_with_nested_list",
        "fields": {"meeting_title": ["str"]},
        "exact_fields": True,
        "children": {"participants": {"name": ["str"]}, "action_items": {"task": ["str"]}},
    }
    children = {"participants": {"name": "str"}, "action_items": {"task": "str"}}
    good = _observed({"meeting_title": ("str", None)}, "parent_with_nested_list", children)
    assert rc.check_schema(expect, good) == []
    merged = _observed(
        {"meeting_title": ("str", None)},
        "parent_with_nested_list",
        {"participants": {"name": "str", "task": "str"}, "notes": {"text": "str"}},
    )
    problems = rc.check_schema(expect, merged)
    assert "no child list 'action_items' (got participants, notes)" in problems
    assert "participants: unexpected field(s) ['task']" in problems
    assert "unexpected child list(s) ['notes']" in problems
    # The single-child form keeps its old, non-exact check.
    legacy = {"child_container": "participants", "child_fields": {"name": ["str"]}}
    assert rc.check_schema(legacy, merged) == []


def test_the_model_needs_every_child_list():
    schema = {
        "$defs": {
            "P": {"properties": {"name": {"type": "string"}}, "type": "object"},
            "A": {"properties": {"task": {"type": "string"}}, "type": "object"},
        },
        "properties": {
            "participants": {"type": "array", "items": {"$ref": "#/$defs/P"}},
            "action_items": {"type": "array", "items": {"$ref": "#/$defs/A"}},
        },
        "type": "object",
    }
    expect = {"children": {"participants": {"name": ["str"]}, "action_items": {"task": ["str"]}}}
    assert rc.check_model(expect, schema) == []
    del schema["properties"]["action_items"]
    assert rc.check_model(expect, schema) == ["model: 'action_items' is not a list"]


def test_a_date_format_and_a_stated_default_are_checked():
    def observed(fmt, default, explicit):
        result = _observed({"day": ("date", None), "comment": ("str", None)})
        result["fields"]["day"]["format"] = fmt
        result["fields"]["comment"].update(default=default, has_explicit_default=explicit)
        return result

    expect = {
        "fields": {"day": ["date"], "comment": ["str"]},
        "formats": {"day": "%d.%m.%Y"},
        "defaults": {"comment": "not given"},
    }
    assert rc.check_schema(expect, observed("%d.%m.%Y", "Not given", True)) == []
    problems = rc.check_schema(expect, observed("%Y-%m-%d", "not given", False))
    assert problems == [
        "fields.day: format '%Y-%m-%d', expected '%d.%m.%Y'",
        "fields.comment: no explicit default, expected 'not given'",
    ]
    assert rc.check_schema(expect, observed("%d.%m.%Y", "", True)) == [
        "fields.comment: default '', expected 'not given'"
    ]


def test_the_models_default_is_the_stated_one():
    from gaik.software_components.extractor import ExtractionRequirements, create_extraction_model

    def schema(**default):
        requirements = ExtractionRequirements(
            use_case_name="inspection", fields=[_spec("comment", "str", **default)]
        )
        return create_extraction_model(requirements).model_json_schema()

    expect = {"fields": {"comment": ["str"]}, "defaults": {"comment": "not given"}}
    assert rc.check_model(expect, schema(default="not given", has_explicit_default=True)) == []
    # Without a stated default the text field is required and has no default at all.
    assert rc.check_model(expect, schema()) == ["model.comment: default None, expected 'not given'"]


def test_the_baseline_does_not_flag_what_an_older_run_did_not_record():
    old = {"structure_type": "flat", "fields": {"a": {"type": "str", "enum": None}}}
    new = {
        "structure_type": "flat",
        "fields": {
            "a": {
                "type": "str",
                "enum": None,
                "default": None,
                "has_explicit_default": False,
                "nullable": False,
            }
        },
        "children": {},
    }
    assert rc._contract(old) == rc._contract(new)
    new["fields"]["a"]["nullable"] = True
    assert rc._contract(old) != rc._contract(new)


def test_every_schema_task_names_what_its_case_expects():
    """The tasks name every field and list, so the checks can be exact."""
    for case in CASES:
        if case["component"] != "schema_generator":
            continue
        task, expect = case["requirements"], case["expect"]
        names = list(expect.get("fields", {})) + [expect.get("container") or ""]
        for container, fields in rc.expected_children(expect).items():
            names += [container, *fields]
        for name in filter(None, names):
            assert name in task, f"{case['id']}: {name!r} is not in its task"
        for values in expect.get("enums", {}).values():
            assert all(v in task for v in values), case["id"]
        for value in expect.get("defaults", {}).values():
            assert f'"{value}"' in task, case["id"]
        for fmt in expect.get("formats", {}).values():
            written = fmt.replace("%d", "DD").replace("%m", "MM").replace("%Y", "YYYY")
            assert written in task, case["id"]


# ---------------------------------------------------------------------------
# RAG, the tabular agent and the vision parser
# ---------------------------------------------------------------------------

RETRIEVED = [
    {"document_name": "invoice-en.txt", "page_number": 1, "source": "fixtures/invoice-en.txt"},
    {"document_name": "invoice-fi.txt", "page_number": 1, "source": "fixtures/invoice-fi.txt"},
]
RAG_EXPECT = {
    "answer_contains": [["551,57", "551.57"]],
    "cited_document": "fixtures/invoice-fi.txt",
}


@pytest.mark.parametrize(
    ("answer", "cited"),
    [
        ("Total 551,57 EUR [invoice-fi.txt, page 1].", [("invoice-fi.txt", "1")]),
        ("551.57 [Document: invoice-fi.txt, Page: 1]", [("invoice-fi.txt", "1")]),
        (
            "See [invoice-fi.txt, page 1; invoice-en.txt, page 1]",
            [("invoice-fi.txt", "1"), ("invoice-en.txt", "1")],
        ),
        ("The total is [EUR] 551,57 [invoice-fi.txt]", []),
    ],
)
def test_citations_are_read_in_gaiks_form(answer, cited):
    found = rc.parse_citations(answer)
    assert [(c["document_name"], c["page"]) for c in found] == cited


def test_a_rag_answer_must_cite_the_retrieved_document_it_used():
    good = {"answer": "It is 551,57 EUR [invoice-fi.txt, page 1].", "retrieved": RETRIEVED}
    assert rc.check_rag(RAG_EXPECT, good) == []
    wrong_doc = {**good, "answer": "It is 551,57 EUR [invoice-en.txt, page 1]."}
    assert rc.check_rag(RAG_EXPECT, wrong_doc) == [
        "no citation resolves to fixtures/invoice-fi.txt (cited: ['invoice-en.txt, page 1'])"
    ]
    invented = {**good, "answer": "551,57 [invoice-fi.txt, page 1] [invoice-99.txt, page 2]"}
    assert rc.check_rag(RAG_EXPECT, invented) == [
        "citation(s) naming no retrieved chunk: ['invoice-99.txt, page 2']"
    ]
    wrong_page = {**good, "answer": "551,57 [invoice-fi.txt, page 3]"}
    assert "no citation resolves" in rc.check_rag(RAG_EXPECT, wrong_page)[0]
    uncited = {**good, "answer": "The total is 1,250.00 EUR."}
    assert rc.check_rag(RAG_EXPECT, uncited) == [
        "the answer has no '551,57' or '551.57'",
        "the answer has no citation in the form [document_name, page X]",
    ]
    not_retrieved = {"answer": good["answer"], "retrieved": RETRIEVED[:1]}
    problems = rc.check_rag(RAG_EXPECT, not_retrieved)
    assert problems[0].startswith("the retriever did not return fixtures/invoice-fi.txt")


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("The sum is 439.50.", ["439.50"]),
        ("Summa on 439,50 EUR", ["439,50"]),
        ("Lines 300.00 + 94.50 + 45.00", ["300.00", "94.50", "45.00"]),
        ("Total 1,250.00 or 1 250,00", ["1,250.00", "1 250,00"]),
        ("Items 2, 5 and 1", ["2", "5", "1"]),
    ],
)
def test_numbers_are_read_as_they_are_written(text, tokens):
    assert rc.number_tokens(text) == tokens


def test_a_tabular_answer_needs_the_number_in_its_rows_and_its_answer():
    expect = {"number": 439.5}
    good = {
        "succeeded": True,
        "rows": [{"sum(line_total)": 439.5}],
        "answer": "The sum of line_total for INV-2026-0042 is 439.50 EUR.",
    }
    assert rc.check_tabular(expect, good) == []
    from decimal import Decimal

    assert rc.check_tabular(expect, {**good, "rows": [{"total": Decimal("439.50")}]}) == []
    wrong = {**good, "rows": [{"total": 1689.5}], "answer": "The sum is 1,689.50."}
    problems = rc.check_tabular(expect, wrong)
    assert problems[0].startswith("the query result holds no 439.5")
    assert problems[1].startswith("the answer states no 439.5")
    failed = {"succeeded": False, "attempts": 3, "error": "Binder Error", "rows": [], "answer": ""}
    assert rc.check_tabular(expect, failed)[0] == (
        "the query failed after 3 attempt(s): Binder Error"
    )
    # The invoice number's digits are not the answer.
    assert rc.check_tabular({"number": 42}, good)[1].startswith("the answer states no 42")


def test_markdown_must_hold_each_string_or_one_of_its_alternatives():
    expect = {"contains": ["INV-2026-0042", "Esimerkki Oy", ["551,57", "551.57"]]}
    markdown = (
        "# LASKU\n\n**Laskun numero:** INV-2026-0042\n\nToimittaja: Esimerkki  Oy\n| 551,57 |"
    )
    assert rc.check_markdown(expect, {"markdown": markdown}) == []
    assert rc.check_markdown(expect, {"markdown": "INV-2026-0042 551.5"}) == [
        "the markdown has no 'Esimerkki Oy'",
        "the markdown has no '551,57' or '551.57'",
    ]


def test_a_typographic_dash_reads_as_a_hyphen_but_a_wrong_digit_does_not():
    en_dash, minus = chr(0x2013), chr(0x2212)
    expect = {"contains": ["INV-2026-0042"]}
    for dash in (en_dash, minus, chr(0x2011)):
        markdown = f"Laskun numero: INV{dash}2026{dash}0042"
        assert rc.check_markdown(expect, {"markdown": markdown}) == []
    wrong = {"markdown": f"INV{en_dash}2026{en_dash}0043"}
    assert rc.check_markdown(expect, wrong) == ["the markdown has no 'INV-2026-0042'"]
    assert rc.check_markdown(expect, {"markdown": "INV 2026 0042"}) != []


def test_rag_skips_a_provider_without_embeddings():
    assert "no embeddings API" in rc.rag_skip_reason("anthropic", {"model": "m"}, None)
    assert "no embeddings API" in rc.rag_skip_reason("anthropic_foundry", {}, "x")
    reason = rc.rag_skip_reason("aitta", {"embedding_model": ""}, None)
    assert "CHECK_AITTA_EMBEDDING_MODEL" in reason
    assert rc.rag_skip_reason("aitta", {"embedding_model": ""}, "bge-m3") is None
    azure = {"embedding_model": "text-embedding-3-small"}
    assert rc.rag_skip_reason("azure", azure, None) is None


def test_embedding_model_precedence():
    env = {"CHECK_AZURE_EMBEDDING_MODEL": "check", "RELEASE_AZURE_EMBEDDING_MODEL": "release"}
    assert rc.embedding_model_for("azure", env) == "check"
    assert rc.embedding_model_for("azure", {"RELEASE_AZURE_EMBEDDING_MODEL": "r"}) == "r"
    assert rc.embedding_model_for("azure", {"CHECK_AZURE_EMBEDDING_MODEL": " "}) is None


def test_usage_is_counted_on_a_raw_client_and_read_from_a_provider_client():
    from types import SimpleNamespace

    def response(**usage):
        return SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: usage))

    completions = SimpleNamespace(
        create=lambda **kw: response(
            prompt_tokens=10,
            completion_tokens=4,
            total_tokens=14,
            completion_tokens_details={"reasoning_tokens": 2},
        )
    )
    raw = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        embeddings=SimpleNamespace(create=lambda **kw: response(prompt_tokens=7, total_tokens=7)),
    )
    tap = rc.UsageTap()
    tap.watch(raw)
    raw.chat.completions.create(model="m")
    raw.embeddings.create(model="e", input=["x"])
    counts = {"input_tokens": 17, "output_tokens": 4, "thinking_tokens": 2, "total_tokens": 21}
    assert tap.result() == counts

    class Counter:
        totals = {"prompt_tokens": 5}

        def snapshot(self):
            return dict(self.totals)

    provider = SimpleNamespace(usage=Counter())
    tap = rc.UsageTap()
    tap.watch(provider)
    provider.usage.totals = {"prompt_tokens": 8, "completion_tokens": 3}
    assert tap.result() == {"input_tokens": 3, "output_tokens": 3}
    assert rc.UsageTap().result() is None


def test_cases_without_a_schema_need_no_schema_from():
    standalone = [
        {"id": "r", "component": "rag"},
        {"id": "t", "component": "tabular_agent"},
        {"id": "p", "component": "vision_parser"},
    ]
    assert [c["id"] for c in rc.check_cases(standalone)] == ["r", "t", "p"]
    args = rc.parse_args(["--only", "parse-invoice-pdf"])
    assert [c["id"] for c in rc.select_cases(args)] == ["parse-invoice-pdf"]


def _case(component):
    return next(c for c in CASES if c["component"] == component)


def test_the_new_component_cases_match_their_fixtures():
    import csv
    import re

    rag = _case("rag")
    texts = {p: (SKILL / p).read_text(encoding="utf-8") for p in rag["documents"]}
    cited = rag["expect"]["cited_document"]
    assert cited in texts
    for options in rag["expect"]["answer_contains"]:
        assert any(o in texts[cited] for o in options)
    # The question names an invoice that only the cited document holds.
    invoice = re.search(r"INV-\d{4}-\d{4}", rag["question"]).group()
    assert [p for p, t in texts.items() if invoice in t] == [cited]

    tabular = _case("tabular_agent")
    invoice = re.search(r"INV-\d{4}-\d{4}", tabular["question"]).group()
    with (SKILL / tabular["files"][0]).open(encoding="utf-8", newline="") as handle:
        lines = [row for row in csv.DictReader(handle) if row["invoice_number"] == invoice]
    total = sum(float(row["line_total"]) for row in lines)
    assert total == pytest.approx(tabular["expect"]["number"])
    # Its lines are the Finnish invoice's, and their sum is its net total.
    finnish = (SKILL / "fixtures/invoice-fi.txt").read_text(encoding="utf-8")
    assert invoice in finnish and f"Veroton yhteensä: {total:.2f}".replace(".", ",") in finnish
    for row in lines:
        assert row["description"] in finnish
        assert row["line_total"].replace(".", ",") in finnish

    parser = _case("vision_parser")
    assert all((SKILL / p).is_file() for p in parser["files"])
    source = (SKILL / parser["source_text"]).read_text(encoding="utf-8")
    for item in parser["expect"]["contains"]:
        options = [item] if isinstance(item, str) else item
        assert any(o in source for o in options), item


def test_the_judge_sees_the_input_and_the_output_of_each_new_component():
    outputs = {
        "rag": {"answer": "ANSWER-TEXT", "retrieved": []},
        "tabular_agent": {"answer": "ANSWER-TEXT", "sql": "SELECT 1", "rows": []},
        "vision_parser": {"markdown": "ANSWER-TEXT"},
    }
    for component, output in outputs.items():
        case = _case(component)
        prompt = rc.judge_prompt(case, {"output": output, "problems": []})
        assert "ANSWER-TEXT" in prompt and case["rubric"] in prompt
        if component == "vision_parser":
            assert "Esimerkki Oy" in prompt  # the text the PDF was rendered from
        else:
            assert case["question"] in prompt
        if component == "tabular_agent":
            assert "line_total" in prompt and "Tiivistesarja" in prompt  # the CSV itself
    extraction = rc.judge_prompt(_case("extractor"), {"output": {}, "problems": []})
    assert extraction.startswith("You check one output of a document-extraction component")


def test_the_summary_names_the_embedding_model_and_why_a_case_was_skipped():
    summary = {
        "started": "now",
        "gaik_version": "0",
        "gaik_from": "src",
        "git_commit": "abc",
        "git_dirty": False,
        "judge": None,
        "case_ids": ["rag-invoice-total"],
        "providers": {
            "azure": {
                "model": "m",
                "embedding_model": "text-embedding-3-small",
                "cases": {"rag-invoice-total": {"status": "pass"}},
            },
            "anthropic": {
                "model": "c",
                "cases": {"rag-invoice-total": {"status": "skip", "reason": "no embeddings API"}},
            },
        },
    }
    text = rc.render_summary(summary)
    assert "| azure | m | - | text-embedding-3-small |  |" in text
    assert "## Skipped\n\n- anthropic / rag-invoice-total: no embeddings API" in text


def test_a_typographic_dash_passes_with_a_warning():
    warnings: list[str] = []
    problems = rc.check_contains(["INV-2026-0042"], "Lasku INV\u20132026\u20130042", "md", warnings)
    assert problems == []
    assert warnings == ["md writes 'INV-2026-0042' with a typographic dash"]
    exact: list[str] = []
    assert rc.check_contains(["INV-2026-0042"], "INV-2026-0042", "md", exact) == []
    assert exact == []
    assert rc.check_contains(["INV-2026-0042"], "INV-2026-0043", "md", []) != []


def test_the_summary_shows_extra_attempts_and_warnings():
    summary = {
        "started": "now",
        "gaik_version": "x",
        "gaik_from": "here",
        "git_commit": "abc",
        "git_dirty": False,
        "judge": None,
        "case_ids": ["s", "p"],
        "providers": {
            "azure": {
                "model": "m",
                "cases": {
                    "s": {
                        "status": "pass",
                        "attempts": 2,
                        "earlier_attempts": [
                            {"status": "fail", "problems": ["fields: no field 'x'"]}
                        ],
                    },
                    "p": {
                        "status": "pass",
                        "warnings": ["md writes 'A-1' with a typographic dash"],
                    },
                },
            }
        },
    }
    text = rc.render_summary(summary)
    assert "| s | pass (attempt 2) |" in text
    assert "| p | pass (warning) |" in text
    assert "## Needed another attempt" in text and "attempt 1 fail: fields: no field 'x'" in text
    assert "## Warnings" in text and "azure / p: md writes 'A-1'" in text


def test_attempts_default_to_one():
    assert rc.parse_args([]).attempts == 1
    assert rc.parse_args(["--attempts", "2"]).attempts == 2
