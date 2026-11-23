"""The demo's wizard chat and Solution Wizard v2 read one SKILL.md.

SKILL.md gives some instructions only for v2's web app (its PoC tab, test data
step, gate buttons and Gate 4, the reopen_gate tool, the sandbox), and its
"Where this skill runs" paragraph tells the other hosts what to do instead. The
demo is a web chat too, so its bootstrap prompt says it is not v2 and points to
that paragraph. These tests keep the two together: when SKILL.md renames the
paragraph or drops the tool that tells v2 apart, they fail here instead of the
demo's agent following v2's instructions in a chat that has none of it.
"""

from __future__ import annotations

from pathlib import Path

from api.routers import solution_wizard as route

HOSTS_PARAGRAPH = "**Where this skill runs.**"

#: What SKILL.md's v2-only instructions speak of; the paragraph must name each one.
V2_ONLY = ('"the web app"', '"the web session"', '"the sandbox"', "Gate 4", "`reopen_gate`")


def _skill_text() -> str:
    assert route.WIZARD_DIR is not None, "the wizard assets were not found"
    return (route.WIZARD_DIR / "SKILL.md").read_text(encoding="utf-8")


def _hosts_paragraph(skill: str) -> str:
    start = skill.index(HOSTS_PARAGRAPH)
    return skill[start : skill.index("\n\n", start)]


def test_skill_md_says_which_host_is_v2_and_what_the_others_do() -> None:
    paragraph = _hosts_paragraph(_skill_text())

    assert "You are in v2 only when you have its `reopen_gate`" in paragraph
    for term in V2_ONLY:
        assert term in paragraph, term
    assert "Anywhere else, follow the instruction given for elsewhere" in paragraph


def test_the_demo_prompt_says_it_is_not_v2_and_points_to_that_paragraph(tmp_path: Path) -> None:
    prompt = route._bootstrap_prompt(tmp_path)

    assert "NOT SOLUTION WIZARD V2" in prompt
    assert '"Where this skill runs"' in prompt
    assert HOSTS_PARAGRAPH.strip("*").rstrip(".") in _skill_text()
    # The demo's own words must not read as v2's "web session".
    assert "web session" not in prompt.lower()


def test_the_v2_marker_is_a_tool_the_demo_does_not_give_its_agent() -> None:
    source = Path(route.__file__).read_text(encoding="utf-8")
    allowed = source[source.index("allowed_tools=") :].split("]", 1)[0]

    assert "reopen_gate" not in allowed
