"""Shared pytest setup for the offline unit tests."""

import os

import pytest

# Importing litellm otherwise downloads its model cost map from GitHub. Pytest
# loads this file before collecting any test module, so the bundled map is used.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


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
