"""Tests for the Section-9 requirement completeness checker (V3 Gate 1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.requirements import check_completeness, summary


def _complete_data() -> dict:
    """A blueprint whose specs answer all 13 checklist points."""
    return {
        "blueprint_version": "1.0",
        "use_case": {"id": "uc", "name": "UC", "description": "Do the thing.", "domain": "test"},
        "business_spec": {
            "current_process": "manual",
            "proposed_solution": "automate it",
            "intended_users": ["clerk"],
            "reviewers": ["supervisor"],
            "poc_goal": "show extraction works",
        },
        "technical_spec": {
            "input_types": ["pdf"],
            "output_types": ["structured_json"],
            "language": "en",
            "domain_vocabulary": "none",
            "model_provider": "configurable",
            "integration_targets": [],
            "human_review": True,
            "evaluation_requirements": "field F1 >= 0.9",
            "security_constraints": "none",
        },
        "target_output_spec": {
            "schema_name": "Out",
            "fields": ["a", "b"],
            "required_fields": ["a"],
        },
    }


def test_complete_blueprint_has_no_gaps():
    bp = Blueprint.model_validate(_complete_data())
    assert check_completeness(bp) == []
    assert "PASSED" in summary(bp)


def test_missing_language_is_flagged():
    data = _complete_data()
    del data["technical_spec"]["language"]
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 6 in gaps  # language is checklist point 6


def test_missing_users_and_poc_goal_flagged():
    data = _complete_data()
    data["business_spec"].pop("intended_users")
    data["business_spec"].pop("poc_goal")
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 2 in gaps and 13 in gaps


def test_explicit_unknown_counts_as_answered():
    """An explicit 'unknown' is a deliberate deferral, not a silent gap."""
    data = _complete_data()
    data["technical_spec"]["language"] = "unknown"
    data["business_spec"]["poc_goal"] = "unknown"
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 6 not in gaps and 13 not in gaps


def test_empty_integration_list_is_answered():
    """integration_targets: [] means 'no integration' -- a valid answer."""
    data = _complete_data()
    data["technical_spec"]["integration_targets"] = []
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 11 not in gaps


def test_missing_integration_key_is_flagged():
    data = _complete_data()
    del data["technical_spec"]["integration_targets"]
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 11 in gaps


def test_privacy_satisfied_by_governance():
    """Governance resolving PII/sensitivity answers the privacy point even with
    no explicit security_constraints field."""
    data = _complete_data()
    del data["technical_spec"]["security_constraints"]
    data["governance"] = {
        "data_handling": {"contains_personal_data": "no", "output_sensitivity": "low"}
    }
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 9 not in gaps


def test_rag_output_satisfies_required_fields_point():
    """A non-structured output type (answer) answers point 5 without a field list."""
    data = _complete_data()
    data["technical_spec"]["output_types"] = ["answer"]
    data["target_output_spec"] = {}
    bp = Blueprint.model_validate(data)
    gaps = {g.number for g in check_completeness(bp)}
    assert 5 not in gaps


def test_summary_lists_all_13_points():
    bp = Blueprint.model_validate(_complete_data())
    text = summary(bp)
    for n in range(1, 14):
        assert f"{n:>2}." in text or f"{n}." in text
