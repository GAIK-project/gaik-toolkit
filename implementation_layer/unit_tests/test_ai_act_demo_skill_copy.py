"""The AI Act screening demo ships a generated copy of the skill text.

Fails when the skill under no-code-assets changes without regenerating it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT / "implementation_layer" / "toolkit_demo_app" / "scripts" / "build_ai_act_skill.py"
)
REGENERATE = "uv run python implementation_layer/toolkit_demo_app/scripts/build_ai_act_skill.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_ai_act_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_skill_text_is_current():
    builder = _builder()
    committed = builder.OUT.read_text(encoding="utf-8")
    assert committed == builder.build(), f"stale; run: {REGENERATE}"
