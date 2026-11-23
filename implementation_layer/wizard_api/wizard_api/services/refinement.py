"""Gate 3 refinement: what feedback after a run is allowed to change (#96).

After a sandbox run the user says what was wrong. V1's SKILL.md already carries
the classification — a long table of change types, each marked "update the
blueprint first?" — and the judgement of which row a piece of feedback falls
into belongs to the agent, not here.

What belongs here is the rule that table exists to protect:

    If feedback changes workflow intent, the blueprint is updated and approved
    first, and only then are the PoC files regenerated from it.

V1 states it as a rule the agent should follow. A rule an agent should follow is
one it can skip under pressure, and the consequence is the one SKILL.md names:
the blueprint says one thing and run_poc.py does another, and nothing downstream
can be trusted. So the server holds the sequence instead of asking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: What a piece of post-run feedback turns out to be.
#:
#: `intent` — a design decision the blueprint formally represents changed: a
#: prompt, a schema field, a component, a workflow step, an output format, an
#: evaluation criterion, the model.
#:
#: `implementation` — the blueprint still describes what the user wants, and the
#: package does not do it: a path, a log line, an off-by-one, a wiring bug.
Classification = Literal["intent", "implementation"]

CLASSIFICATIONS: tuple[str, ...] = ("intent", "implementation")

#: The reason each classification is treated differently, in the words the user
#: should see rather than a code.
INTENT_RULE = (
    "This changes what the solution is meant to do, so the blueprint is updated "
    "and approved first — otherwise the blueprint and the generated package "
    "would describe different things."
)
IMPLEMENTATION_RULE = (
    "This does not change any decision the blueprint records, so the package is "
    "patched directly and the approved blueprint is left alone."
)


class RefinementRejectedError(ValueError):
    """The feedback, or what it asks for next, does not hold together."""


@dataclass(frozen=True)
class Refinement:
    """One round of the run → feedback → fix loop."""

    classification: Classification
    feedback: str
    rule: str

    @property
    def requires_blueprint_change(self) -> bool:
        return self.classification == "intent"


def classify(feedback: str, classification: str) -> Refinement:
    """Record a classified piece of feedback.

    The classification is supplied — by the agent, which has the table and the
    conversation — and checked rather than guessed at here. Empty feedback is
    refused: "it did not work" recorded against a run helps nobody later, and the
    loop is meant to leave a trail of what was actually asked for.
    """
    text = (feedback or "").strip()
    if not text:
        raise RefinementRejectedError("say what was wrong with the run")
    if len(text) > 4000:
        raise RefinementRejectedError("the feedback is too long")
    if classification not in CLASSIFICATIONS:
        raise RefinementRejectedError(
            f"classification must be one of {', '.join(CLASSIFICATIONS)} (got {classification!r})"
        )
    rule = INTENT_RULE if classification == "intent" else IMPLEMENTATION_RULE
    return Refinement(classification=classification, feedback=text, rule=rule)  # type: ignore[arg-type]


def check_regeneration_allowed(
    refinement: Refinement,
    *,
    blueprint_version_at_feedback: int,
    blueprint_version_now: int,
) -> None:
    """Refuse to regenerate for an intent change the blueprint has not taken.

    The version is the evidence: an intent change means the blueprint moved, so
    if it is where it was when the feedback was given, the change was not
    applied and regenerating now would produce a package that disagrees with the
    document it is supposed to come from.

    An implementation fix is never blocked — by definition it changes nothing the
    blueprint records.
    """
    if not refinement.requires_blueprint_change:
        return
    if blueprint_version_now <= blueprint_version_at_feedback:
        raise RefinementRejectedError(
            "this was classified as an intent change, so update and approve the "
            f"blueprint before regenerating (still at version {blueprint_version_now})"
        )
