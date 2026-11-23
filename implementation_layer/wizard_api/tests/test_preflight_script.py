"""The preflight script, run the way the Job runs it: ``python -c`` in the package dir (#252)."""

import subprocess
import sys
from pathlib import Path

import pytest
from wizard_api.services.preflight_script import PREFLIGHT_SCRIPT

pytest.importorskip("yaml")


def _run(poc: Path):
    return subprocess.run(
        [sys.executable, "-c", PREFLIGHT_SCRIPT],
        cwd=poc,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _package(tmp_path: Path, source: str) -> Path:
    poc = tmp_path / "poc"
    poc.mkdir()
    (poc / "run_poc.py").write_text(source)
    return poc


def test_a_package_that_imports_cleanly_passes(tmp_path):
    result = _run(_package(tmp_path, "import json\nfrom pathlib import Path\n"))

    assert result.returncode == 0, result.stdout
    assert "=== PREFLIGHT OK ===" in result.stdout


def test_a_syntax_error_is_reported_with_its_line(tmp_path):
    result = _run(_package(tmp_path, "import json\ndef main(:\n    pass\n"))

    assert result.returncode == 1
    assert "PROBLEM: run_poc.py does not parse (line 2" in result.stdout
    assert "=== PREFLIGHT FAILED: 1 problem(s) ===" in result.stdout


def test_a_module_the_image_lacks_is_reported_with_the_exception(tmp_path):
    result = _run(_package(tmp_path, "import json\nimport a_module_nobody_has\n"))

    assert result.returncode == 1
    assert "line 2: import a_module_nobody_has failed (ModuleNotFoundError" in result.stdout


def test_a_name_the_module_does_not_have_is_reported(tmp_path):
    result = _run(_package(tmp_path, "from yaml import safe_load, nothing_like_this\n"))

    assert result.returncode == 1
    assert "yaml has no name nothing_like_this" in result.stdout


def test_a_guarded_optional_import_and_a_local_module_do_not_fail_it(tmp_path):
    poc = _package(
        tmp_path,
        "import helper\ntry:\n    import some_optional_thing\nexcept ImportError:\n    pass\n",
    )
    (poc / "helper.py").write_text("x = 1\n")

    assert _run(poc).returncode == 0


def test_a_module_in_a_package_subfolder_is_the_packages_own(tmp_path):
    # UC03 (6 Oct 2026): run_poc.py puts schemas/ on sys.path at module level and
    # imports the wizard's own output_schema from there. The check does not run
    # that line, so it reported the import as failed and the tab showed a problem
    # the run never had.
    poc = _package(
        tmp_path,
        "import os\n"
        "import sys\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schemas'))\n"
        "from output_schema import QAResponse\n",
    )
    (poc / "schemas").mkdir()
    (poc / "schemas" / "output_schema.py").write_text("class QAResponse:\n    pass\n")

    result = _run(poc)

    assert result.returncode == 0, result.stdout
    assert "output_schema" not in result.stdout
    assert "=== PREFLIGHT OK ===" in result.stdout


def test_a_module_among_the_inputs_is_still_one_the_image_lacks(tmp_path):
    poc = _package(tmp_path, "import helper\n")
    (poc / "sample_input").mkdir()
    (poc / "sample_input" / "helper.py").write_text("")

    result = _run(poc)

    assert result.returncode == 1
    assert "line 1: import helper failed (ModuleNotFoundError" in result.stdout


def test_a_stage_whose_config_cannot_be_built_is_named(tmp_path):
    poc = _package(tmp_path, "import json\n")
    (poc / "config.yaml").write_text("stages:\n  extraction:\n    provider: nowhere\n")
    (poc / "provider_config.py").write_text(
        "def get_stage_config(config, stage):\n    raise ValueError('no key for ' + stage)\n"
    )

    result = _run(poc)

    assert result.returncode == 1
    assert (
        "PROBLEM: config.yaml stage extraction: ValueError: no key for extraction" in result.stdout
    )


def test_a_stage_that_builds_passes(tmp_path):
    poc = _package(tmp_path, "import json\n")
    (poc / "config.yaml").write_text("stages:\n  extraction:\n    provider: azure\n")
    (poc / "provider_config.py").write_text(
        "def get_stage_config(config, stage):\n    return {'provider': 'azure'}\n"
    )

    assert _run(poc).returncode == 0


def test_a_package_that_exits_while_loading_is_a_problem_not_an_unfinished_check(tmp_path):
    # sys.exit() in the package's own code ended the script before any PROBLEM line,
    # and the PoC tab then showed a fault in the package as a check that could not finish.
    poc = _package(tmp_path, "import json\n")
    (poc / "config.yaml").write_text("stages:\n  extraction:\n    provider: azure\n")
    (poc / "provider_config.py").write_text("import sys\n\nsys.exit('no key')\n")

    result = _run(poc)

    assert result.returncode == 1
    assert "PROBLEM: config.yaml / provider_config.py cannot be loaded (SystemExit: no key)" in (
        result.stdout
    )
