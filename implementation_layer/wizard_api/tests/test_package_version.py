"""What changes a package's version.

The approved-package digest (Gate 3) and the reuse of a passed preflight both rest
on ``package_version``. It covered a fixed list of files, so a change to a helper
the entrypoint imports (``poc_output.py``, ``document_manifest.py``,
``input_bundle.py``) or to ``schemas/output_schema_model.json``, which gaik loads
since 0.11.0, did not count as a change to the approved package.
"""

import pytest
from wizard_api.services import poc_service

_PACKAGE = {
    "run_poc.py": "import poc_output\n",
    "config.yaml": "stages: {}\n",
    "provider_config.py": "",
    "poc_output.py": "VERBOSE = False\n",
    "document_manifest.py": "",
    "input_bundle.py": "",
    "evals/run_basic_eval.py": "",
    "schemas/output_schema.py": "",
    "schemas/output_schema_requirements.json": "{}",
    "schemas/output_schema_model.json": "{}",
    "app.py": "PACKAGE_DIR = None\n",
    "ui/index.html": "<!doctype html>\n",
    "ui/solution.json": "{}",
    "sample_input/case.py": "x = 1\n",
    "output/session_results.json": "[]",
}


@pytest.fixture
def poc(tmp_path):
    root = tmp_path / "poc"
    for name, text in _PACKAGE.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "name",
    [
        "run_poc.py",
        "poc_output.py",
        "document_manifest.py",
        "input_bundle.py",
        "evals/run_basic_eval.py",
        "schemas/output_schema_model.json",
        "agent_helper.py",  # a module the agent adds
        "app.py",  # the package's test page server: a Python file like any other
    ],
)
def test_a_change_to_the_packages_code_or_schemas_changes_its_version(poc, name) -> None:
    before = poc_service.package_version(str(poc))

    (poc / name).write_text("# changed\n", encoding="utf-8")

    assert poc_service.package_version(str(poc)) != before


@pytest.mark.parametrize(
    "name", ["sample_input/case.py", "sample_input/new.py", "output/session_results.json"]
)
def test_a_runs_inputs_and_outputs_leave_the_version_as_it_is(poc, name) -> None:
    before = poc_service.package_version(str(poc))

    (poc / name).write_text("# changed\n", encoding="utf-8")

    assert poc_service.package_version(str(poc)) == before


def test_the_version_is_the_same_for_the_same_files(poc, tmp_path) -> None:
    copy = tmp_path / "copy"
    for name, text in _PACKAGE.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    assert poc_service.package_version(str(copy)) == poc_service.package_version(str(poc))


@pytest.mark.parametrize("name", ["ui/index.html", "ui/solution.json"])
def test_the_test_pages_markup_and_data_leave_the_version_as_it_is(poc, name) -> None:
    """ui/ decides nothing a run does; the package check compares the page with its template."""
    before = poc_service.package_version(str(poc))

    (poc / name).write_text("changed\n", encoding="utf-8")

    assert poc_service.package_version(str(poc)) == before
