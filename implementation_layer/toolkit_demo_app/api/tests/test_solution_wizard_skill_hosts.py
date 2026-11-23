"""The demo's wizard chat and Solution Wizard v2 read one SKILL.md.

SKILL.md gives some instructions only for v2's web app (its PoC tab, test data
step, gate buttons, reopen_gate tool and sandbox) and the rest of its readers an
"elsewhere" instruction. The demo is a web chat too, so its bootstrap prompt says
which of the two it is. These tests keep the prompt and SKILL.md's wording
together: when SKILL.md renames what the prompt points at, they fail here instead
of the demo's agent following v2's instructions in a chat that has none of it.
"""

from __future__ import annotations

from pathlib import Path

from api.routers import solution_wizard as route

#: The words in SKILL.md that mark a v2-only instruction, as the prompt quotes them.
V2_MARKERS = ("the wizard's web app", "the web session", "the wizard's sandbox")


def _skill_text() -> str:
    assert route.WIZARD_DIR is not None, "the wizard assets were not found"
    return (route.WIZARD_DIR / "SKILL.md").read_text(encoding="utf-8")


def test_the_demo_prompt_says_it_is_not_the_v2_web_app(tmp_path: Path) -> None:
    prompt = route._bootstrap_prompt(tmp_path)

    assert "NOT THE SOLUTION WIZARD V2 WEB APP" in prompt
    for marker in V2_MARKERS:
        assert f'"{marker}"' in prompt, marker


def test_skill_md_still_marks_v2_only_instructions_as_the_prompt_says() -> None:
    skill = _skill_text()

    for marker in V2_MARKERS:
        assert marker in skill, f"SKILL.md no longer says {marker!r}: update the demo prompt"
    # The demo follows the instruction SKILL.md gives every other host.
    assert "Elsewhere (Claude Code), ask them to put the file in `poc/sample_input/`" in skill
    assert "elsewhere, show the change and ask the user to confirm it" in skill
