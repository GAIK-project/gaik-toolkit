"""An edit to output_schema.py reaches the PoC's load_schema().

gaik's load_schema() reads schemas/output_schema_model.json whenever it exists and never
imports output_schema.py, so a correction made to the .py after the schema was saved
(SKILL.md Step 4.5, a Gate 3 refinement) ran on the old schema without a word. The audio
and document PoCs now write the model file again when the .py is newer.

The cases run the scaffolded run_poc.py's own schema functions on the scaffolded files.
"""

import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402

pytest.importorskip("gaik.software_components.extractor.saved_schema")
documents = pytest.importorskip("gaik.software_modules.documents_to_structured_data")
audio = pytest.importorskip("gaik.software_modules.audio_to_structured_data")

EXAMPLES = Path(__file__).parent.parent / "examples"
SCRIPT = Path(__file__).parent.parent / "scripts" / "refresh_schema_model.py"

PATTERNS = {
    "document_to_structured": (
        "document_extraction_blueprint.json",
        documents.DocumentsToStructuredData,
    ),
    "audio_to_structured": ("incident_reporting_blueprint.json", audio.AudioToStructuredData),
}


class Run:
    """What one call of the PoC's _load_schema_if_fresh gave."""

    def __init__(self, schema, out: str, err: str, exit_code: int | None):
        self.schema, self.stdout, self.stderr, self.returncode = schema, out, err, exit_code or 0


def _scaffold(tmp_path: Path, pattern: str, nested: dict | None = None) -> Path:
    blueprint = Blueprint.from_file(EXAMPLES / PATTERNS[pattern][0])
    if nested:
        blueprint.target_output_spec["nested"] = nested
    scaffold_poc(blueprint, tmp_path)
    return tmp_path / "poc"


def _edit(poc: Path, old: str, new: str) -> None:
    """Edit output_schema.py the way the agent does, a little after the model file."""
    py_path = poc / "schemas" / "output_schema.py"
    source = py_path.read_text(encoding="utf-8")
    assert old in source
    py_path.write_text(source.replace(old, new, 1), encoding="utf-8")
    later = (poc / "schemas" / "output_schema_model.json").stat().st_mtime + 5
    os.utime(py_path, (later, later))


def _load(poc: Path, pattern: str, capsys) -> Run:
    """Call the generated run_poc.py's _load_schema_if_fresh, as its main() does."""
    source = (poc / "run_poc.py").read_text(encoding="utf-8")
    functions = source[source.index("def _requirements_hash") : source.index("def find_input_file")]
    namespace = {
        "__file__": str(poc / "run_poc.py"),
        "hashlib": hashlib,
        "json": json,
        "Path": Path,
        "sys": sys,
        "poc_output": types.SimpleNamespace(error_detail=str),
    }
    exec(compile(functions, str(poc / "run_poc.py"), "exec"), namespace)
    pipeline_cls = PATTERNS[pattern][1]
    capsys.readouterr()
    try:
        schema, _requirements, _hash = namespace["_load_schema_if_fresh"](
            pipeline_cls.__new__(pipeline_cls), poc / "schemas", "output_schema"
        )
        code = None
    except SystemExit as exc:
        schema, code = None, exc.code
    captured = capsys.readouterr()
    return Run(schema, captured.out, captured.err, code)


def _schema(run: Run) -> dict:
    assert run.returncode == 0, run.stderr[-2000:]
    return run.schema.model_json_schema()


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_an_edit_to_output_schema_py_reaches_load_schema(capsys, tmp_path, pattern):
    poc = _scaffold(tmp_path, pattern)
    root = json.loads((poc / "schemas" / "output_schema_requirements.json").read_text())[
        "model_name"
    ]
    _edit(
        poc,
        f"class {root}(BaseModel):\n",
        f"class {root}(BaseModel):\n    reviewer_note: Optional[str] = None\n",
    )

    run = _load(poc, pattern, capsys)

    assert "reviewer_note" in _schema(run)["properties"]
    assert "model file written again" in run.stdout
    saved = (poc / "schemas" / "output_schema_model.json").read_text(encoding="utf-8")
    assert "reviewer_note" in saved


def test_an_edit_to_a_nested_row_reaches_load_schema(capsys, tmp_path):
    poc = _scaffold(
        tmp_path,
        "document_to_structured",
        nested={"line_items": {"fields": ["sku", "quantity"], "field_types": {"quantity": "int"}}},
    )
    _edit(
        poc,
        "class LineItem(BaseModel):\n    model_config = ConfigDict(extra='forbid')\n\n",
        "class LineItem(BaseModel):\n    model_config = ConfigDict(extra='forbid')\n\n"
        "    unit: Optional[str] = None\n",
    )

    schema = _schema(_load(poc, "document_to_structured", capsys))

    assert "unit" in schema["$defs"]["LineItem"]["properties"]
    assert schema["properties"]["line_items"]["type"] == "array"


def test_files_that_agree_are_loaded_as_before(capsys, tmp_path):
    """The .py is not newer: it is not imported (even broken), the model file is read."""
    poc = _scaffold(tmp_path, "document_to_structured")
    model_path = poc / "schemas" / "output_schema_model.json"
    py_path = poc / "schemas" / "output_schema.py"
    before = model_path.read_bytes()
    py_path.write_text("raise SystemExit('imported')\n", encoding="utf-8")
    earlier = model_path.stat().st_mtime - 5
    os.utime(py_path, (earlier, earlier))

    run = _load(poc, "document_to_structured", capsys)

    assert "po_number" in _schema(run)["properties"]
    assert model_path.read_bytes() == before
    assert "written again" not in run.stdout


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        (
            "class PurchaseOrder(BaseModel):\n",
            "class PurchaseOrder(BaseModel)\n",
            "does not import",
        ),
        ("class PurchaseOrder(BaseModel):\n", "class Order(BaseModel):\n", "has no class"),
    ],
    ids=["syntax", "renamed"],
)
def test_an_edit_that_cannot_be_saved_stops_the_run(capsys, tmp_path, old, new, reason):
    """Never the old schema without a word: the run stops and keeps the model file."""
    poc = _scaffold(tmp_path, "document_to_structured")
    model_path = poc / "schemas" / "output_schema_model.json"
    before = model_path.read_bytes()
    _edit(poc, old, new)

    run = _load(poc, "document_to_structured", capsys)

    assert run.returncode == 1
    assert reason in run.stderr
    assert model_path.read_bytes() == before
    assert not (poc / "schemas" / "output_schema_model.json.tmp").exists()


def test_gaiks_read_only_copy_is_not_imported(capsys, tmp_path):
    """A schema the PoC generated in a run is saved by gaik with a .py for reading,
    which may not import; a copy that makes it look newer must not stop the run."""
    poc = _scaffold(tmp_path, "document_to_structured")
    py_path = poc / "schemas" / "output_schema.py"
    py_path.write_text(
        '"""\nAuto-generated schema module (do not edit manually).\n"""\n\n'
        "class PurchaseOrder(gaik.Unknown):\n    pass\n",
        encoding="utf-8",
    )
    later = (poc / "schemas" / "output_schema_model.json").stat().st_mtime + 5
    os.utime(py_path, (later, later))

    run = _load(poc, "document_to_structured", capsys)

    assert "po_number" in _schema(run)["properties"]
    assert "read-only copy" in run.stdout


def test_the_poc_writes_what_refresh_schema_model_writes(capsys, tmp_path):
    """The PoC and scripts/refresh_schema_model.py give the same model file."""
    import importlib.util
    import shutil

    poc = _scaffold(tmp_path / "a", "document_to_structured")
    _edit(poc, "    currency: Optional[str] = None\n", "    currency: Optional[str] = 'EUR'\n")
    copy = tmp_path / "b" / "schemas"
    shutil.copytree(poc / "schemas", copy)

    _schema(_load(poc, "document_to_structured", capsys))
    spec = importlib.util.spec_from_file_location("_refresh_schema_model_cli", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.refresh(copy)

    assert (poc / "schemas" / "output_schema_model.json").read_text(encoding="utf-8") == (
        copy / "output_schema_model.json"
    ).read_text(encoding="utf-8")
