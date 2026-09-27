import pytest
from pydantic import ValidationError

from wizard_api.schemas.session import SessionCreate, SessionUpdate
from wizard_api.session_state import (
    merge_gate_statuses,
    validate_gate_statuses,
    validate_step,
)


def test_validate_step_accepts_range() -> None:
    validate_step(1)
    validate_step(12)


def test_validate_step_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="step must be between"):
        validate_step(0)
    with pytest.raises(ValueError, match="step must be between"):
        validate_step(13)


def test_validate_gate_statuses_rejects_unknown_key() -> None:
    with pytest.raises(ValueError, match="unknown gate keys"):
        validate_gate_statuses({"gate_5": "pending"})


def test_validate_gate_statuses_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="must be one of"):
        validate_gate_statuses({"gate_1": "maybe"})


def test_merge_gate_statuses_partial_patch() -> None:
    current = {"gate_1": "approved", "gate_2": "pending", "gate_3": "pending", "gate_4": "pending"}
    merged = merge_gate_statuses(current, {"gate_2": "approved"})
    assert merged["gate_1"] == "approved"
    assert merged["gate_2"] == "approved"


def test_session_create_rejects_blank_user_id() -> None:
    with pytest.raises(ValidationError):
        SessionCreate(user_id="   ")


def test_session_update_rejects_invalid_step() -> None:
    with pytest.raises(ValidationError):
        SessionUpdate(step=99)
