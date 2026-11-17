"""Generated outputs say which blueprint version produced them, and SKILL.md states
which commands and folders the wizard agent may use."""

import ast
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.docs_generator import DOC_NAMES, generate_docs
from solution_wizard.scaffolder import _build_pdf_report_section, scaffold_poc

WIZARD = Path(__file__).parent.parent
EXAMPLES = WIZARD / "examples"


def _blueprint(name: str = "document_extraction_blueprint.json") -> Blueprint:
    return Blueprint.from_file(EXAMPLES / name)


def test_the_fingerprint_changes_with_the_blueprint_but_not_with_a_redrawn_diagram():
    blueprint = _blueprint()
    first = blueprint.fingerprint()
    assert re.fullmatch(r"[0-9a-f]{64}", first["blueprint_sha256"])
    assert first["blueprint_version"] == blueprint.blueprint_version
    assert first["blueprint_id"] in (blueprint.metadata.blueprint_id, blueprint.use_case.id)

    assert blueprint.model_copy(deep=True).fingerprint() == first
    redrawn = blueprint.model_copy(update={"visualizations": {"bpmn_mapping": {"a": "b"}}})
    assert redrawn.fingerprint() == first

    changed = blueprint.model_copy(deep=True)
    changed.use_case.description += " Also the invoice date."
    assert changed.fingerprint()["blueprint_sha256"] != first["blueprint_sha256"]


def test_the_poc_config_and_readme_carry_the_blueprint_fingerprint(tmp_path):
    blueprint = _blueprint()
    fingerprint = blueprint.fingerprint()
    poc = scaffold_poc(blueprint, tmp_path)["poc_dir"]

    config = yaml.safe_load((poc / "config.yaml").read_text(encoding="utf-8"))
    assert config["blueprint"] == fingerprint
    readme = (poc / "README.md").read_text(encoding="utf-8")
    assert fingerprint["blueprint_sha256"] in readme
    assert "${" not in readme


def test_every_generated_document_names_the_blueprint(tmp_path):
    blueprint = _blueprint()
    sha = blueprint.fingerprint()["blueprint_sha256"]
    written = generate_docs(blueprint, tmp_path)
    assert [p.stem for p in written] == DOC_NAMES
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert f"SHA-256 {sha}" in text, path.name
        assert "${" not in text, path.name


def test_the_pdf_report_block_carries_the_hash_and_keeps_the_use_case_name_as_text():
    blueprint = _blueprint()
    blueprint.technical_spec = {**blueprint.technical_spec, "output_types": ["pdf"]}
    blueprint.use_case.name = 'Invoices "Q3" \\ north\nregion'
    block = _build_pdf_report_section(blueprint, "InvoiceSchema")
    assert blueprint.fingerprint()["blueprint_sha256"] in block
    # The block parses as the body of a function, so the name stayed inside its literal.
    ast.parse("def main(_pdf_source, output_dir):\n" + block)


def test_validate_blueprint_prints_the_hash_outputs_carry():
    blueprint_path = EXAMPLES / "document_extraction_blueprint.json"
    result = subprocess.run(
        [
            sys.executable,
            str(WIZARD / "scripts" / "validate_blueprint.py"),
            "--blueprint",
            str(blueprint_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = Blueprint.from_file(blueprint_path).fingerprint()["blueprint_sha256"]
    assert f"Blueprint SHA-256: {sha}" in result.stdout


def _boundary() -> str:
    text = (WIZARD / "SKILL.md").read_text(encoding="utf-8")
    start = text.index("**What you may run, read and change.**")
    return " ".join(text[start : text.index("\n---\n", start)].split())


def test_skill_names_every_wizard_script_as_allowed_or_ask_first():
    boundary = _boundary()
    scripts = sorted(p.name for p in (WIZARD / "scripts").glob("*.py"))
    assert scripts, "no scripts found"
    for name in scripts:
        assert f"`{name}`" in boundary, f"{name} is not in the SKILL.md boundary"
    assert "Ask first for `promote_template.py`" in boundary
    assert "`run_wizard.py --export-schema`" in boundary


def test_skill_limits_writes_to_the_output_directory_and_never_reads_env_files():
    boundary = _boundary()
    assert "only inside the output directory from Step 1.1" in boundary
    assert "Never read `.env` files" in boundary
    assert "needs the user's yes first" in boundary
    assert "`validate_blueprint.py` prints it" in boundary
