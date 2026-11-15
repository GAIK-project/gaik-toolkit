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


# --------------------------------------------------------------------------- review additions

RAG_EXAMPLE = Path(__file__).parent.parent / "examples" / "rag_workflow_blueprint.json"


def _config(poc: Path) -> dict:
    import yaml

    return yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("where", ["use_case.id", "step id"])
def test_an_id_that_ends_in_a_line_break_stops_the_scaffolding(tmp_path, where) -> None:
    bp = _blueprint()
    if where == "use_case.id":
        bp.use_case.id = "invoices\n"
    else:
        bp.workflow.steps[0].id += "\n"
    with pytest.raises(ValueError, match="cannot go into the PoC code"):
        scaffold_poc(bp, tmp_path)


def test_a_keyword_as_output_field_stops_the_scaffolding(tmp_path) -> None:
    bp = _blueprint()
    bp.target_output_spec["fields"] = ["from"]
    with pytest.raises(ValueError, match="cannot go into the PoC code"):
        scaffold_poc(bp, tmp_path)


def test_the_automatic_language_setting_is_kept(tmp_path) -> None:
    bp = _blueprint()
    bp.technical_spec["language"] = "auto"
    assert _config(scaffold_poc(bp, tmp_path)["poc_dir"])["language"] == "auto"


def test_a_language_that_ends_in_a_line_break_falls_back_to_english(tmp_path) -> None:
    bp = _blueprint()
    bp.technical_spec["language"] = "fi\n"
    assert _config(scaffold_poc(bp, tmp_path)["poc_dir"])["language"] == "en"


def test_the_rag_evaluation_framework_keeps_its_name(tmp_path) -> None:
    poc = scaffold_poc(Blueprint.from_file(RAG_EXAMPLE), tmp_path)["poc_dir"]
    script = (poc / "evals" / "run_basic_eval.py").read_text(encoding="utf-8")
    ast.parse(script)
    assert "Evaluation framework: RAG_eval" in script
    assert "Evaluation framework: extraction_eval" not in script


def test_descriptions_and_allowed_values_stay_text_in_the_schema_source() -> None:
    from solution_wizard.schema_designer import build_pydantic_model

    statuses = ['paid "in full"', "open\n", "it's"]
    spec = {
        "schema_name": "Invoice",
        "fields": ["total", "status", "note"],
        "field_types": {"total": "decimal", "status": "string", "note": "string"},
        "required_fields": ["total"],
        "field_descriptions": {"total": TEXT, "status": TEXT, "note": TEXT},
        "allowed_values": {"status": statuses},
    }
    source = build_pydantic_model(spec)
    tree = ast.parse(source)
    # The text added no statement of its own: no print() call came from it.
    assert not _calls_named(source, "print")
    namespace: dict = {}
    exec(compile(tree, "<schema>", "exec"), namespace)
    model = namespace["Invoice"]
    for field in spec["fields"]:
        assert model.model_fields[field].description == TEXT
    assert [member.value for member in namespace["StatusEnum"]] == statuses


@pytest.mark.parametrize(
    ("spec", "what"),
    [
        ({"fields": ["from"]}, "field name"),
        ({"fields": ["total: int = 0\nx"]}, "field name"),
        ({"fields": ["total"], "schema_name": "Invoice(BaseModel)"}, "class name"),
    ],
)
def test_a_name_the_schema_source_cannot_carry_is_refused(spec, what) -> None:
    from solution_wizard.schema_designer import build_pydantic_model

    with pytest.raises(ValueError, match=f"{what} .* is not a valid Python name"):
        build_pydantic_model(spec)
