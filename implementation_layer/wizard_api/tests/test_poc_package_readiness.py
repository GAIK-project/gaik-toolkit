"""A PoC package is only offered when it is one (customer test report, 19 / T8, R6).

The download appeared as soon as any file existed under ``poc/``, so a package
with no README, no requirements.txt and an entrypoint wiring nothing could be
taken away — and then did nothing when run. These tests pin what "complete"
means, using the two checks the reviewer named plus the two files the report
found missing.
"""

from pathlib import Path

from wizard_api.services.poc_service import package_is_ready, package_problems

WIRED_ENTRYPOINT = (
    "import sys\nfrom gaik.software_modules.audio_to_structured_data import AudioToStructuredData\n"
)
STUB_ENTRYPOINT = '"""TODO: wire the pipeline."""\n\nif __name__ == "__main__":\n    pass\n'


def _package(
    tmp_path: Path, *, entrypoint=WIRED_ENTRYPOINT, requirements="gaik[extract]\n", readme="# PoC\n"
) -> str:
    poc = tmp_path / "poc"
    poc.mkdir()
    if entrypoint is not None:
        (poc / "run_poc.py").write_text(entrypoint)
    if requirements is not None:
        (poc / "requirements.txt").write_text(requirements)
    if readme is not None:
        (poc / "README.md").write_text(readme)
    return str(poc)


def test_a_complete_package_is_ready(tmp_path):
    poc = _package(tmp_path)

    assert package_problems(poc) == []
    assert package_is_ready(poc)


def test_a_package_with_only_some_files_is_not_ready(tmp_path):
    """19: the download was live while the package was still only a few prompt
    and schema files."""
    poc = tmp_path / "poc"
    poc.mkdir()
    (poc / "schemas").mkdir()
    (poc / "schemas" / "output_schema.py").write_text("x = 1\n")

    problems = package_problems(str(poc))

    assert len(problems) == 3
    assert not package_is_ready(str(poc))


def test_an_entrypoint_that_wires_nothing_is_not_a_package(tmp_path):
    """The scaffolder's _generic fallback renders a TODO stub: the file exists,
    the package runs, and nothing happens."""
    problems = package_problems(_package(tmp_path, entrypoint=STUB_ENTRYPOINT))

    assert problems == ["run_poc.py does not wire any gaik component"]


def test_requirements_without_gaik_is_not_a_package(tmp_path):
    """Pertti's UC02 review: requirements.txt had no gaik at all, which makes
    the imports impossible."""
    problems = package_problems(_package(tmp_path, requirements="pydantic>=2\n"))

    assert problems == ["requirements.txt does not require gaik"]


def test_a_missing_readme_is_reported(tmp_path):
    problems = package_problems(_package(tmp_path, readme=None))

    assert problems == ["README.md is missing"]


def test_a_missing_entrypoint_is_reported(tmp_path):
    problems = package_problems(_package(tmp_path, entrypoint=None))

    assert problems == ["run_poc.py is missing"]


def test_every_problem_is_reported_not_just_the_first(tmp_path):
    """The user should learn what is wrong in one go, not one file per attempt."""
    problems = package_problems(
        _package(tmp_path, entrypoint=STUB_ENTRYPOINT, requirements="pydantic\n", readme=None)
    )

    assert len(problems) == 3


# ---------------------------------------------------------------------------
# What the deployable package leaves behind (#143)
# ---------------------------------------------------------------------------


def test_the_developers_test_data_does_not_travel_with_the_package():
    """sample_input is the developer's document and output/ is the last run's
    result. Neither is part of what someone else installs."""
    from wizard_api.services.poc_service import is_deployable_path

    assert not is_deployable_path("sample_input/purchase-order.pdf")
    assert not is_deployable_path("output/result.json")


def test_pycache_is_not_shipped():
    """A package review found __pycache__ inside a delivered zip."""
    from wizard_api.services.poc_service import is_deployable_path

    assert not is_deployable_path("__pycache__/run_poc.cpython-311.pyc")
    assert not is_deployable_path("schemas/__pycache__/output_schema.cpython-311.pyc")
    assert not is_deployable_path("schemas/output_schema.pyc")


def test_a_filled_env_file_is_never_shipped():
    """.env.example is the template and travels; .env holds the user's key."""
    from wizard_api.services.poc_service import is_deployable_path

    assert not is_deployable_path(".env")
    assert is_deployable_path(".env.example")


def test_the_wizard_s_own_bookkeeping_does_not_travel():
    from wizard_api.services.poc_service import MANIFEST_NAME, is_deployable_path

    assert not is_deployable_path(MANIFEST_NAME)


def test_everything_the_package_needs_to_run_travels(tmp_path):
    from wizard_api.services.poc_service import deployable_files

    poc = tmp_path / "poc"
    (poc / "schemas").mkdir(parents=True)
    (poc / "sample_input").mkdir()
    (poc / "output").mkdir()
    (poc / "run_poc.py").write_text("from gaik.software_components.extractor import Extractor\n")
    (poc / "requirements.txt").write_text("gaik[extract]\n")
    (poc / "README.md").write_text("# PoC\n")
    (poc / "config.yaml").write_text("use_azure: true\n")
    (poc / ".env.example").write_text("AZURE_API_KEY=\n")
    (poc / "schemas" / "output_schema.py").write_text("x = 1\n")
    (poc / "sample_input" / "order.pdf").write_text("%PDF")
    (poc / "output" / "result.json").write_text("{}")

    shipped = deployable_files(str(poc))

    assert shipped == [
        ".env.example",
        "README.md",
        "config.yaml",
        "requirements.txt",
        "run_poc.py",
        "schemas/output_schema.py",
    ]


# -- what the entrypoint and schema checks (#252) must and must not flag ----------


def _entry(tmp_path, source):
    return package_problems(_package(tmp_path, entrypoint=source))


def test_a_skeleton_whose_component_calls_are_comments_is_not_ready(tmp_path):
    """The check used to look for the word gaik anywhere, comments included."""
    skeleton = (
        "# from gaik.software_components.transcriber import Transcriber\n"
        "# transcriber = Transcriber(api_config=...)\n"
        "def main():\n    pass\n"
    )

    assert _entry(tmp_path, skeleton) == ["run_poc.py does not wire any gaik component"]


def test_an_entrypoint_the_agent_has_not_finished_is_not_ready(tmp_path):
    """UC03 (#252): the tab said ready while run_poc.py still had nine TODO
    markers, because it already imported gaik. The markers mean unfinished."""
    unfinished = (
        WIRED_ENTRYPOINT
        + "def main():\n"
        + "    # TODO: load the access manifest\n"
        + "    pass  # FIXME wire the retriever\n"
    )

    problems = _entry(tmp_path, unfinished)

    assert problems == [
        "run_poc.py still has 2 TODO marker(s), first at line 4: the package is not finished"
    ]


def test_a_word_that_merely_contains_todo_is_not_a_marker(tmp_path):
    source = WIRED_ENTRYPOINT + "todos = []\nMASTODON = 1\n"

    assert _entry(tmp_path, source) == []


def test_an_entrypoint_that_does_not_parse_is_reported_with_its_line(tmp_path):
    problems = _entry(tmp_path, "from gaik import x\ndef main(:\n    pass\n")

    assert len(problems) == 1 and problems[0].startswith("run_poc.py does not parse (line 2")


def test_a_module_the_sandbox_image_lacks_is_reported(tmp_path):
    import importlib.util

    if importlib.util.find_spec("gaik") is None:
        import pytest

        pytest.skip("gaik not installed: the module check is skipped without it")
    source = WIRED_ENTRYPOINT + "import pandas_that_does_not_exist\n"

    problems = _entry(tmp_path, source)

    assert problems == [
        "run_poc.py line 3 imports pandas_that_does_not_exist, "
        "which the sandbox image does not have"
    ]


def test_a_guarded_optional_import_and_a_local_module_are_not_flagged(tmp_path):
    source = (
        WIRED_ENTRYPOINT
        + "import provider_config\n"
        + "try:\n    import some_optional_thing\n"
        + "except ImportError:\n    some_optional_thing = None\n"
    )
    poc = _package(tmp_path, entrypoint=source)
    (Path(poc) / "provider_config.py").write_text("x = 1\n")

    assert package_problems(poc) == []


def test_a_module_in_a_package_subfolder_is_local(tmp_path):
    """UC03, 6 Oct 2026: run_poc.py did sys.path.insert(0, .../schemas) and imported
    output_schema; the package was refused as needing a module the sandbox lacks."""
    source = WIRED_ENTRYPOINT + "from output_schema import QAResponse\n"
    poc = _package(tmp_path, entrypoint=source)
    (Path(poc) / "schemas").mkdir(exist_ok=True)
    (Path(poc) / "schemas" / "output_schema.py").write_text("QAResponse = dict\n")

    assert package_problems(poc) == []


def test_a_file_among_the_inputs_does_not_count_as_package_code(tmp_path):
    import importlib.util

    if importlib.util.find_spec("gaik") is None:
        import pytest

        pytest.skip("gaik not installed: the module check is skipped without it")
    source = WIRED_ENTRYPOINT + "import uploaded_helper\n"
    poc = _package(tmp_path, entrypoint=source)
    (Path(poc) / "sample_input").mkdir(exist_ok=True)
    (Path(poc) / "sample_input" / "uploaded_helper.py").write_text("x = 1\n")

    assert any("uploaded_helper" in p for p in package_problems(poc))


def test_requirements_json_that_is_not_json_is_reported(tmp_path):
    poc = _package(tmp_path)
    (Path(poc) / "schemas").mkdir()
    (Path(poc) / "schemas" / "output_schema_requirements.json").write_text("{not json")

    problems = package_problems(poc)

    assert len(problems) == 1 and "is not valid JSON" in problems[0]


def _requirements_file(poc, fields, requirements_type="extraction"):
    import json

    (Path(poc) / "schemas").mkdir(exist_ok=True)
    (Path(poc) / "schemas" / "output_schema_requirements.json").write_text(
        json.dumps(
            {
                "model_name": "Ticket",
                "requirements_type": requirements_type,
                "requirements": {"use_case_name": "t", "fields": fields},
            }
        )
    )


def test_a_requirements_file_gaik_cannot_load_is_reported(tmp_path):
    import pytest

    pytest.importorskip("gaik.software_components.extractor")
    poc = _package(tmp_path)
    _requirements_file(poc, [{"field_name": "a", "field_type": "dict", "description": "x"}])

    problems = package_problems(poc)

    assert len(problems) == 1 and "cannot be loaded by gaik" in problems[0]


def test_a_list_default_is_not_a_reason_to_hold_the_package(tmp_path):
    """run_poc.py resets it to null before loading (#249)."""
    import pytest

    pytest.importorskip("gaik.software_components.extractor")
    poc = _package(tmp_path)
    _requirements_file(
        poc,
        [{"field_name": "a", "field_type": "list[str]", "description": "x", "default": []}],
    )

    assert package_problems(poc) == []


def test_a_composite_requirements_file_is_left_to_gaik_at_run_time(tmp_path):
    poc = _package(tmp_path)
    _requirements_file(poc, [], requirements_type="parent_with_nested_list")

    assert package_problems(poc) == []


# ---------------------------------------------------------------------------
# The package's test page (app.py, ui/)
# ---------------------------------------------------------------------------


def test_the_test_page_travels_with_the_package():
    from wizard_api.services.poc_service import is_deployable_path

    assert is_deployable_path("app.py")
    assert is_deployable_path("ui/index.html")
    assert is_deployable_path("ui/solution.json")
    assert is_deployable_path("ui/fonts/sora-latin-wght-normal.woff2")
    assert is_deployable_path("ui/fonts/OFL.txt")
    assert is_deployable_path("ui/gaik.svg")


def test_the_scaffolded_test_page_is_shipped_and_is_no_problem_of_the_package(tmp_path):
    """The page's server is a second Python file at the package's root: the checks
    read every .py there, and it must not look like a component the package wires."""
    import shutil

    import pytest

    pytest.importorskip("solution_wizard.scaffolder")
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.scaffolder import TEMPLATES_DIR, scaffold_poc
    from wizard_api.services import poc_service

    example = TEMPLATES_DIR.parent.parent / "examples" / "document_extraction_blueprint.json"
    poc = scaffold_poc(Blueprint.from_file(example), tmp_path)["poc_dir"]

    shipped = set(poc_service.deployable_files(str(poc)))
    assert {
        "app.py",
        "ui/index.html",
        "ui/solution.json",
        "ui/fonts/sora-latin-wght-normal.woff2",
        "ui/fonts/sora-latin-ext-wght-normal.woff2",
        "ui/fonts/OFL.txt",
        "ui/gaik.svg",
    } <= {name.replace("\\", "/") for name in shipped}
    with_page = package_problems(str(poc))
    assert not poc_service._package_transcribes(str(poc))

    (poc / "app.py").unlink()
    shutil.rmtree(poc / "ui")
    assert package_problems(str(poc)) == with_page


def _page_package(tmp_path):
    """A complete package with the test page as the scaffolder writes it."""
    import pytest

    pytest.importorskip("solution_wizard.scaffolder")
    from solution_wizard.scaffolder import TEMPLATES_DIR, TEST_PAGE_TEMPLATES

    poc = Path(_package(tmp_path))
    for relative, template in TEST_PAGE_TEMPLATES.items():
        (poc / relative).parent.mkdir(parents=True, exist_ok=True)
        (poc / relative).write_bytes((TEMPLATES_DIR / template).read_bytes())
    return poc


def test_a_changed_test_page_is_a_problem_of_the_package(tmp_path):
    """Nothing checked that the shipped app.py and ui/index.html were still the template's."""
    poc = _page_package(tmp_path)
    assert package_problems(str(poc)) == []

    app = poc / "app.py"
    app.write_bytes(app.read_bytes() + b"\nprint('one more thing')\n")
    page = poc / "ui" / "index.html"
    page.write_bytes(page.read_bytes().replace(b"<body", b"<body data-changed", 1))

    assert package_problems(str(poc)) == [
        "app.py is not the wizard's current test page: the package was generated with an "
        "earlier version of it, or the file was changed afterwards. Generate the package "
        "again to update it",
        "ui/index.html is not the wizard's current test page: the package was generated "
        "with an earlier version of it, or the file was changed afterwards. Generate the "
        "package again to update it",
    ]


def test_the_test_page_with_other_line_ends_is_the_same_page(tmp_path):
    """The scaffolder writes text files, so on Windows the copy has CRLF line ends."""
    poc = _page_package(tmp_path)
    for relative in ("app.py", "ui/index.html"):
        path = poc / relative
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    assert package_problems(str(poc)) == []


def test_a_manifest_hash_does_not_make_a_changed_test_page_pass(tmp_path):
    """The scaffold manifest is in the session folder, which the agent can write: a hash
    recorded there for a changed app.py does not make the change the wizard's."""
    import hashlib
    import json

    from wizard_api.services.poc_service import MANIFEST_NAME

    poc = _page_package(tmp_path)
    changed = (poc / "app.py").read_bytes() + b"\nprint('one more thing')\n"
    (poc / "app.py").write_bytes(changed)
    (poc.parent / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "blueprint": "x",
                "files": ["app.py"],
                "hashes": {"app.py": hashlib.sha256(changed).hexdigest()},
            }
        ),
        encoding="utf-8",
    )

    assert package_problems(str(poc)) == [
        "app.py is not the wizard's current test page: the package was generated with an "
        "earlier version of it, or the file was changed afterwards. Generate the package "
        "again to update it",
    ]
