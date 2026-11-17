"""The wizard skill keeps customer content out of what it writes, asks for a real sample
before generating test data, and handles needs outside GAIK as external services."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _text()
    return text[text.index(start) : text.index(end, text.index(start))]


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_constraints_keep_customer_content_out_of_every_artifact() -> None:
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


def test_the_rule_is_repeated_where_artifacts_are_written() -> None:
    assert "Example values are invented" in _section("## Phase 4", "## Phase 5")
    phase_10 = _flat(_section("## Phase 10", "## Phase 11"))
    assert "No values from the user's material in the code or its comments" in phase_10
    assert "with invented examples and nothing from the user's files" in phase_10
    phase_13 = _flat(_section("## Phase 13", "## Assumption Recording Format"))
    assert "carries no customer content or personal data" in phase_13


def test_phase_10_asks_for_a_real_sample_before_synthetic_data() -> None:
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


def test_a_need_outside_gaik_is_named_explained_asked_and_recorded() -> None:
    step = _flat(_section("**Step 2b -- Needs outside GAIK", "**Step 3 --"))

    assert "do not invent a GAIK capability" in step
    for need in ("an account and an API key", "the cost", "the terms of use", "governance"):
        assert need in step
    assert "**Ask whether they can provide it**" in step
    assert "technical_spec.external_services" in step
    assert "user_can_provide: false" in step and "open item" in step


def test_the_poc_skips_an_external_service_it_cannot_reach() -> None:
    phase_10 = _flat(_section("## Phase 10", "## Phase 11"))

    assert "external_service(name, module, env_vars)" in phase_10
    assert "never with an `import` statement of your own" in phase_10
    assert "fallback" in phase_10
    assert "SKIPPED <service>" in _section("## Phase 11", "## Phase 12")
