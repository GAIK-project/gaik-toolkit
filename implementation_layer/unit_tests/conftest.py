"""Shared pytest setup for the offline unit tests."""

import os

import pytest
from gaik.software_components.env_file import load_env_file

# Importing litellm otherwise downloads its model cost map from GitHub. Pytest
# loads this file before collecting any test module, so the bundled map is used.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# The live tests decide at import whether their keys are set, and importing gaik
# reads no .env file, so the repository's .env is loaded here, before collection.
# GAIK_NO_DOTENV=1 keeps it out.
load_env_file()


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
