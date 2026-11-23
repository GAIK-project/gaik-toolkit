"""Shared pytest setup for the offline unit tests."""

import os
import sys
from pathlib import Path

import pytest
from gaik.software_components.env_file import load_env_file

# Importing litellm otherwise downloads its model cost map from GitHub. Pytest
# loads this file before collecting any test module, so the bundled map is used.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# The live tests decide at import whether their keys are set, and importing gaik
# reads no .env file, so the repository's .env is loaded here, before collection.
# GAIK_NO_DOTENV=1 keeps it out.
load_env_file()

#: Solution Wizard v2's deploy tests. Most of them run its shell scripts with a POSIX
#: bash and PATH=/usr/bin:/bin; on Windows `bash` is WSL's launcher and a .sh file is
#: not a program. The whole files skip on Windows, their few checks that only read
#: files too. All of them run on Linux in test.yml, and three of the files also in
#: solution-wizard-v2.yml's deploy-manifests job (--noconftest, past this hook).
POSIX_SHELL_TESTS = frozenset(
    {
        "test_deploy_instances.py",
        "test_deploy_signin.py",
        "test_sandbox_job_manifest.py",
        "test_sandbox_network_policy.py",
    }
)


_HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(reason="runs Solution Wizard v2's deploy scripts with a POSIX bash")
    for item in items:
        if item.path.parent == _HERE and item.path.name in POSIX_SHELL_TESTS:
            item.add_marker(skip)


@pytest.fixture
def symlink():
    """Make a symlink, ``symlink(link, target)``; skip only where making one
    needs a right this account lacks (WinError 1314 on Windows)."""

    def make(link, target):
        try:
            os.symlink(target, link, target_is_directory=os.path.isdir(target))
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                pytest.skip(f"cannot make a symlink here: {exc}")
            raise

    return make
