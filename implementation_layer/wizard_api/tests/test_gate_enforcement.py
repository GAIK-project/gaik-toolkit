"""The server enforces the approval gates (customer test report, T4, 18/R3, 22/R8).

Until now the gate map was computed in the browser only, and the server accepted
any step between 1 and 13. So a session could be walked past a gate the user had
not approved — the reported symptom being the agent declaring "Gate 1 passed"
from a chat "yes" while the screen still showed the approval button, and the
chat running on through Gates 2 and 3 while the screen stayed put.

These tests pin the server side of that: what it refuses, what it still allows,
and that going back does not cost an approval already given.
"""

import pytest
from wizard_api.session_state import (
    GateNotApprovedError,
    check_gates_for_step_change,
    default_gate_statuses,
)


def _gates(**approved: str) -> dict[str, str]:
    return {**default_gate_statuses(), **approved}


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------


def test_stepping_past_a_pending_gate_is_refused():
    """18 / R3: the chat's "yes" cannot carry the session past Gate 1."""
    with pytest.raises(GateNotApprovedError) as exc:
        check_gates_for_step_change(4, 5, _gates())

    assert exc.value.gate_key == "gate_1"
    assert exc.value.gate_step == 4
    assert exc.value.status == "pending"


def test_jumping_over_several_gates_at_once_is_refused():
    """18 / R1: the chat ran through Gates 2 and 3 while the screen stayed at 3
    of 13. A single jump is refused at the first gate it would pass."""
    with pytest.raises(GateNotApprovedError) as exc:
        check_gates_for_step_change(3, 13, _gates())

    assert exc.value.gate_key == "gate_1"


def test_a_rejected_gate_does_not_let_the_session_past():
    with pytest.raises(GateNotApprovedError) as exc:
        check_gates_for_step_change(4, 6, _gates(gate_1="rejected"))

    assert exc.value.status == "rejected"


def test_the_second_gate_is_enforced_once_the_first_is_approved():
    with pytest.raises(GateNotApprovedError) as exc:
        check_gates_for_step_change(8, 10, _gates(gate_1="approved"))

    assert exc.value.gate_key == "gate_2"


# ---------------------------------------------------------------------------
# What is still allowed
# ---------------------------------------------------------------------------


def test_reaching_a_gate_is_allowed():
    """Arriving at the gate is how it becomes reviewable — only passing it is
    gated. Without this the session could never reach Gate 1 at all."""
    check_gates_for_step_change(3, 4, _gates())


def test_moving_inside_a_section_is_allowed():
    check_gates_for_step_change(1, 3, _gates())


def test_an_approved_gate_lets_the_session_past():
    check_gates_for_step_change(4, 5, _gates(gate_1="approved"))


def test_every_gate_approved_allows_the_whole_run():
    check_gates_for_step_change(
        1, 13, _gates(gate_1="approved", gate_2="approved", gate_3="approved")
    )


# ---------------------------------------------------------------------------
# Going back (22 / R8)
# ---------------------------------------------------------------------------


def test_going_back_is_never_gated():
    """22 / R8: going back to revise is allowed from anywhere."""
    check_gates_for_step_change(10, 3, _gates(gate_1="approved"))
    check_gates_for_step_change(5, 4, _gates())


def test_going_back_and_forward_again_does_not_need_re_approval():
    """The other half of 22 / R8: after going back the user was blocked from
    moving forward again, because the approval had been recomputed away. The
    stored approval is what counts, so the way forward stays open."""
    gates = _gates(gate_1="approved")

    check_gates_for_step_change(6, 2, gates)  # back
    check_gates_for_step_change(2, 6, gates)  # and forward again


def test_following_the_agent_stops_on_the_first_pending_gate() -> None:
    from wizard_api.session_state import furthest_step_before_pending_gate

    gates = {"gate_1": "approved", "gate_2": "pending"}
    assert furthest_step_before_pending_gate(5, 10, gates) == 9  # reaches Gate 2, not past
    assert furthest_step_before_pending_gate(5, 8, gates) == 8  # no gate on the way
    assert furthest_step_before_pending_gate(9, 10, gates) == 9  # standing on a pending gate
    assert furthest_step_before_pending_gate(5, 10, {**gates, "gate_2": "approved"}) == 10
    assert furthest_step_before_pending_gate(1, 9, {"gate_1": "pending"}) == 4
    assert furthest_step_before_pending_gate(7, 7, gates) == 7
    assert furthest_step_before_pending_gate(7, 3, gates) == 3  # backward is not capped
