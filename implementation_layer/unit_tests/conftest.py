"""Shared pytest setup for the offline unit tests."""

import os

# Importing litellm otherwise downloads its model cost map from GitHub. Pytest
# loads this file before collecting any test module, so the bundled map is used.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
