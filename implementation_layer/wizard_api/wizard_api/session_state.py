"""Wizard session step and gate validation (S1-3)."""

from typing import Literal

GateStatus = Literal["pending", "approved", "rejected"]

GATE_KEYS = ("gate_1", "gate_2", "gate_3", "gate_4")
MIN_STEP = 1
MAX_STEP = 13

#: The step each gate sits on, mirroring the UI's GATE_STEP_TO_API. The browser
#: knew this and the server did not, so a step change that skipped a pending
#: gate was accepted: the agent could walk a session past Gate 1 while the user
#: was still looking at the approval button.
GATE_STEP_TO_KEY: dict[int, str] = {4: "gate_1", 9: "gate_2", 11: "gate_3", 13: "gate_4"}
#: And the other way: the step a gate is decided on.
GATE_KEY_TO_STEP: dict[str, int] = {key: step for step, key in GATE_STEP_TO_KEY.items()}


class GateNotApprovedError(Exception):
    """A step change would pass a gate the user has not approved."""

    def __init__(self, gate_key: str, gate_step: int, status: str) -> None:
        self.gate_key = gate_key
        self.gate_step = gate_step
        self.status = status
        super().__init__(
            f"{gate_key} (step {gate_step}) is {status}; "
            f"approve it before moving past step {gate_step}"
        )


def check_gates_for_step_change(
    current_step: int, new_step: int, gate_statuses: dict[str, str]
) -> None:
    """Refuse a forward step change that passes an unapproved gate.

    Moving *to* a gate step is how a session reaches the gate, so only moving
    *past* one is checked. Backward moves are never checked: going back to
    revise something is allowed, and the approval already given is kept (see
    ``update_session``), so the way forward stays open.
    """
    if new_step <= current_step:
        return
    for gate_step, gate_key in sorted(GATE_STEP_TO_KEY.items()):
        if current_step <= gate_step < new_step:
            status = gate_statuses.get(gate_key, "pending")
            if status != "approved":
                raise GateNotApprovedError(gate_key, gate_step, status)


def furthest_step_before_pending_gate(
    current_step: int, wanted_step: int, gate_statuses: dict[str, str]
) -> int:
    """How far forward a session may follow the agent: ``wanted_step``, or the
    first unapproved gate on the way there (reaching a gate is allowed, passing
    it is not). Backward or equal moves come back unchanged."""
    if wanted_step <= current_step:
        return wanted_step
    for gate_step, gate_key in sorted(GATE_STEP_TO_KEY.items()):
        if current_step <= gate_step < wanted_step:
            if gate_statuses.get(gate_key, "pending") != "approved":
                return gate_step
    return wanted_step


def default_gate_statuses() -> dict[str, str]:
    return {key: "pending" for key in GATE_KEYS}


def validate_step(step: int) -> None:
    if not MIN_STEP <= step <= MAX_STEP:
        raise ValueError(f"step must be between {MIN_STEP} and {MAX_STEP}")


def validate_gate_statuses(gate_statuses: dict[str, str]) -> None:
    unknown_keys = set(gate_statuses) - set(GATE_KEYS)
    if unknown_keys:
        raise ValueError(f"unknown gate keys: {sorted(unknown_keys)}")
    for key, value in gate_statuses.items():
        if value not in ("pending", "approved", "rejected"):
            raise ValueError(f"{key} must be one of: pending, approved, rejected (got {value!r})")


def merge_gate_statuses(current: dict[str, str], patch: dict[str, str]) -> dict[str, str]:
    validate_gate_statuses(patch)
    merged = {**default_gate_statuses(), **current, **patch}
    validate_gate_statuses(merged)
    return merged
