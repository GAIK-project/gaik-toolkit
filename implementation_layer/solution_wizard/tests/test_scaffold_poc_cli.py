"""The scaffolder CLI's repo guard (#180).

`scripts/scaffold_poc.py` refuses to write its output inside the GAIK checkout.
The root used to be a fixed `parent.parent`, which resolved to "/" once the
package was installed at an image root -- and then every absolute output dir
looked like it was inside the repo, so the agent's Phase 10 scaffold failed for
every use case in the container. These tests pin both halves: a checkout is
still protected, and an installed package no longer refuses everything.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "scaffold_poc.py"


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("scaffold_poc_cli", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Finding the repo root
# ---------------------------------------------------------------------------


def test_the_checkout_is_found_from_the_script_location(cli, tmp_path):
    repo = tmp_path / "gaik-toolkit"
    (repo / ".git").mkdir(parents=True)
    wizard = repo / "implementation_layer" / "solution_wizard"
    wizard.mkdir(parents=True)

    assert cli._find_repo_root(wizard) == repo


def test_a_git_worktree_counts_as_a_checkout(cli, tmp_path):
    """In a worktree `.git` is a file, not a directory."""
    repo = tmp_path / "gaik-worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")
    wizard = repo / "implementation_layer" / "solution_wizard"
    wizard.mkdir(parents=True)

    assert cli._find_repo_root(wizard) == repo


def test_an_installed_package_has_no_repo_root(cli, tmp_path):
    """The container case: no marker above the package, so nothing to protect."""
    wizard = tmp_path / "solution_wizard"
    wizard.mkdir()

    assert cli._find_repo_root(wizard) is None


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------


def test_an_installed_package_accepts_an_absolute_output_dir(cli, monkeypatch):
    """This is #180: `/data/sessions/...` was refused because the root was "/"."""
    monkeypatch.setattr(cli, "_REPO_ROOT", None)

    cli._check_output_dir(Path("/data/sessions/abc"))  # must not exit


def test_a_checkout_still_refuses_output_inside_itself(cli, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit) as exit_info:
        cli._check_output_dir(tmp_path / "implementation_layer" / "poc")

    assert exit_info.value.code == 1


def test_a_checkout_still_accepts_output_outside_itself(cli, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(cli, "_REPO_ROOT", repo)

    cli._check_output_dir(tmp_path / "elsewhere" / "poc")  # must not exit


def test_wizard_workspaces_stays_exempt(cli, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_REPO_ROOT", tmp_path)

    cli._check_output_dir(tmp_path / ".wizard_workspaces" / "session-1")  # must not exit


def test_the_real_container_path_has_no_repo_root(cli):
    """The exact layout from #180: the package installed at /solution_wizard.

    The old root was `_WIZARD_ROOT.parent.parent`, which is "/" for this path --
    and `Path("/data/sessions/abc").relative_to("/")` succeeds, so the guard
    refused it. No filesystem needed to pin this: the path itself is the bug.
    """
    assert cli._find_repo_root(Path("/solution_wizard")) is None

    # The mechanism the fix removes, spelled out.
    old_root = Path("/solution_wizard").parent.parent
    assert old_root == Path("/")
    assert Path("/data/sessions/abc").relative_to(old_root) == Path("data/sessions/abc")
