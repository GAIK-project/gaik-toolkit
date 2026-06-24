"""Wizard session step and gate validation (S1-3)."""

from typing import Literal

GateStatus = Literal["pending", "approved", "rejected"]

GATE_KEYS = ("gate_1", "gate_2", "gate_3", "gate_4")
MIN_STEP = 1
MAX_STEP = 12


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
            raise ValueError(
                f"{key} must be one of: pending, approved, rejected (got {value!r})"
            )


def merge_gate_statuses(current: dict[str, str], patch: dict[str, str]) -> dict[str, str]:
    validate_gate_statuses(patch)
    merged = {**default_gate_statuses(), **current, **patch}
    validate_gate_statuses(merged)
    return merged
