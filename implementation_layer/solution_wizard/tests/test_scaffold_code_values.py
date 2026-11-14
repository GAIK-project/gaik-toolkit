"""Blueprint values reach the generated PoC code only as checked ids or escaped text."""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402

EXAMPLE = Path(__file__).parent.parent / "examples" / "document_extraction_blueprint.json"
TEXT = 'Invoices """ end\nprint("x") # \\ and \'quotes\''


def _blueprint() -> Blueprint:
    return Blueprint.from_file(EXAMPLE)


def _calls_named(source: str, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name
    ]


def test_free_text_in_the_use_case_name_stays_text(tmp_path) -> None:
    bp = _blueprint()
    bp.use_case.name = TEXT
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]

    for name in ("run_poc.py", "evals/run_basic_eval.py"):
        source = (poc / name).read_text(encoding="utf-8")
        before = len(_calls_named(_example_source(tmp_path, name), "print"))
        # Parses, and the text added no statement of its own.
        assert len(_calls_named(source, "print")) == before, name
    env = (poc / ".env.example").read_text(encoding="utf-8")
    assert env.splitlines()[0].startswith("# ")
    assert "\nprint(" not in env


def _example_source(tmp_path: Path, name: str) -> str:
    clean = tmp_path / "clean"
    clean.mkdir(exist_ok=True)
    poc = scaffold_poc(_blueprint(), clean)["poc_dir"]
    return (poc / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "where",
    ["use_case.id", "step id", "artifact", "schema name", "field"],
)
def test_an_id_outside_the_pattern_stops_the_scaffolding(tmp_path, where) -> None:
    bp = _blueprint()
    odd = 'x")\nimport os  #'
    if where == "use_case.id":
        bp.use_case.id = odd
    elif where == "step id":
        bp.workflow.steps[0].id = odd
    elif where == "artifact":
        bp.workflow.steps[0].outputs = [odd]
    elif where == "schema name":
        bp.target_output_spec["schema_name"] = "Invoice(BaseModel)"
    else:
        bp.target_output_spec["fields"] = ["total amount"]
    with pytest.raises(ValueError, match="cannot go into the PoC code"):
        scaffold_poc(bp, tmp_path)


def test_a_language_that_is_not_a_code_falls_back_to_english(tmp_path) -> None:
    bp = _blueprint()
    bp.technical_spec["language"] = 'fi")\nimport os  #'
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    ast.parse((poc / "run_poc.py").read_text(encoding="utf-8"))
    assert "import os" not in (poc / "run_poc.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("base_url", "http://example.org/v1"),
        ("base_url", "https://user:pw@example.org/v1"),
        ("azure_endpoint", "ftp://example.org"),
        ("api_version", "env:AZURE_API_KEY"),
        ("api_version", "env:lower_case"),
    ],
)
def test_an_unsafe_endpoint_or_env_reference_stops_the_scaffolding(tmp_path, key, value) -> None:
    bp = _blueprint()
    bp.models = {**(bp.models or {}), key: value}
    with pytest.raises(ValueError, match="Unsafe model settings"):
        scaffold_poc(bp, tmp_path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("base_url", "https://my-resource.openai.azure.com/openai/v1"),
        ("base_url", "http://localhost:8000/v1"),
        ("api_version", "env:AZURE_API_VERSION"),
    ],
)
def test_a_provider_endpoint_or_setting_reference_is_kept(tmp_path, key, value) -> None:
    bp = _blueprint()
    bp.models = {**(bp.models or {}), key: value}
    scaffold_poc(bp, tmp_path)
