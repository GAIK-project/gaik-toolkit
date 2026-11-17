"""What SKILL.md says: keep customer content out of what the agent writes, ask for a real
sample before generating test data, and handle needs outside GAIK as external services.

These tests check the skill's text, not what an agent does with it. The one exception is
the Phase 10 service example, which is run."""

import re
import sys
import types
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _text()
    return text[text.index(start) : text.index(end, text.index(start))]


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_skill_says_customer_content_stays_out_of_every_artifact() -> None:
    constraints = _flat(_section("**Constraints:**", "## Phase 1"))

    assert "No customer content or personal data in what you write" in constraints
    for kind in ("names", "e-mail addresses", "phone numbers", "identifiers", "addresses"):
        assert kind in constraints
    for where in (
        "the blueprint",
        "schema descriptions",
        "prompts",
        "code and its comments",
        "the documentation",
        "synthetic test data",
        "a template promoted in Phase 13",
        "handoff message in the chat",
    ):
        assert where in constraints
    assert "invented placeholders" in constraints
    assert "which is not part of the deployable package" in constraints


def test_the_skill_repeats_that_rule_where_artifacts_are_written() -> None:
    assert "Example values are invented" in _section("## Phase 4", "## Phase 5")
    phase_10 = _flat(_section("## Phase 10", "## Phase 11"))
    assert "No values from the user's material in the code or its comments" in phase_10
    assert "with invented examples and nothing from the user's files" in phase_10
    phase_13 = _flat(_section("## Phase 13", "## Assumption Recording Format"))
    assert "carries no customer content or personal data" in phase_13


def test_the_skill_says_phase_10_asks_for_a_real_sample_before_synthetic_data() -> None:
    phase_10 = _flat(_section("## Phase 10", "## Phase 11"))

    assert "ask for a real sample first" in phase_10
    assert '"Testiaineisto" in Finnish' in phase_10
    assert "sample_input/.uploaded" in phase_10
    assert "**ask for permission** to generate synthetic test data" in phase_10
    assert "invented organisations and people only" in phase_10
    assert "record the choice as an assumption" in phase_10
    assert "Audio cannot be synthesised" in phase_10 and "ask for a recording" in phase_10
    # The old advice to generate placeholder documents without asking is gone.
    assert "you may generate synthetic sample documents" not in phase_10
    assert phase_10.index("ask for a real sample first") < phase_10.index("ask for permission")


def test_the_skill_says_a_need_outside_gaik_is_named_explained_asked_and_recorded() -> None:
    step = _flat(_section("**Step 2b -- Needs outside GAIK", "**Step 3 --"))

    assert "do not invent a GAIK capability" in step
    for need in ("an account and an API key", "the cost", "the terms of use", "governance"):
        assert need in step
    assert "**Ask whether they can provide it**" in step
    assert "technical_spec.external_services" in step
    assert "user_can_provide: false" in step and "open item" in step
    assert 'write `"none"`' in step


def test_the_skill_says_a_service_added_after_gate_2_reopens_it() -> None:
    step = _flat(_section("**Step 2b -- Needs outside GAIK", "**Step 3 --"))

    assert "**A service added or changed after Gate 2 is approved**" in step
    assert "call the `reopen_gate` tool for Gate 2 before you make the change" in step
    assert "ask the user to confirm it" in step


def test_the_skill_says_the_poc_skips_an_external_service_it_cannot_reach() -> None:
    phase_10 = _flat(_section("## Phase 10", "## Phase 11"))

    assert "external_service(name, module, env_vars)" in phase_10
    assert "never with an `import` statement of your own" in phase_10
    assert "fallback" in phase_10
    assert "SKIPPED <service>" in _section("## Phase 11", "## Phase 12")


def test_the_phase_10_service_example_runs_as_written(monkeypatch) -> None:
    """The example the agent copies into run_poc.py reads the service's key and calls
    it; a name it forgot to import would end in its own except and skip the service."""
    phase_10 = _section("## Phase 10", "## Phase 11")
    blocks = re.findall(r"```python\n(.*?)```", phase_10, re.DOTALL)
    code = next(block for block in blocks if "external_service(" in block)
    keys: list[str] = []

    class Client:
        def __init__(self, api_key: str) -> None:
            keys.append(api_key)

        def search(self, query: str) -> dict:
            return {"results": [query]}

    stub = types.ModuleType("provider_config")
    stub.external_service = lambda name, module, env_vars: types.SimpleNamespace(
        TavilyClient=Client
    )
    monkeypatch.setitem(sys.modules, "provider_config", stub)
    monkeypatch.setenv("TAVILY_API_KEY", "not-a-real-key")
    namespace = {"supplier_name": "Example Supplier Oy"}

    exec(compile(code, "SKILL.md Phase 10", "exec"), namespace)

    assert keys == ["not-a-real-key"]
    assert namespace["supplier_news"] == ["Example Supplier Oy"]
