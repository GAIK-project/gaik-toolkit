"""Workflow step types the user reads in the review screen (customer test report, R5).

"Export results to Excel" was shown as an AI step. V1 calls every non-human step
``automated_task``, which covered both a component calling a model and a step
that just writes the result somewhere, and both mapped to ``ai``.

The component is the tie-breaker: it is what makes the model call.
"""

from wizard_api.services.artifact_sync import _steps_from_draft


def _draft(*steps: dict) -> dict:
    return {"workflow": {"steps": list(steps)}}


def _types(draft: dict) -> list[str]:
    return [s["type"] for s in _steps_from_draft(draft)]


def test_an_automated_step_with_a_component_is_an_ai_step():
    draft = _draft(
        {
            "id": "extract",
            "name": "Extract PO fields",
            "type": "automated_task",
            "component": "DocumentsToStructuredData",
        }
    )

    assert _types(draft) == ["ai"]


def test_an_automated_step_without_a_component_is_not_an_ai_step():
    """R5: the Excel export. Automated, but nothing calls a model."""
    draft = _draft({"id": "export", "name": "Export results to Excel", "type": "automated_task"})

    assert _types(draft) == ["io"]


def test_a_user_task_stays_io_and_a_human_review_stays_itself():
    draft = _draft(
        {"id": "upload", "name": "Upload purchase order PDF", "type": "user_task"},
        {"id": "review", "name": "Manager approves", "type": "human_review"},
    )

    assert _types(draft) == ["io", "human_review"]


def test_an_unknown_type_is_not_assumed_to_be_ai():
    """The old default claimed the wizard was running a model on any step whose
    type we did not recognise."""
    draft = _draft({"id": "wait", "name": "Wait for the nightly batch", "type": "timer"})

    assert _types(draft) == ["io"]


def test_an_unknown_type_with_a_component_is_still_an_ai_step():
    draft = _draft(
        {"id": "judge", "name": "Validate", "type": "service_task", "component": "LLMJudge"}
    )

    assert _types(draft) == ["ai"]


def test_the_real_example_blueprints_keep_their_shape():
    """Every component-bearing step in the shipped examples is automated, and
    every step without one is a user task or a review — so this change must not
    move any of them."""
    import json
    from pathlib import Path

    examples = Path(__file__).resolve().parents[2] / "solution_wizard" / "examples"
    incident = json.loads((examples / "incident_reporting_blueprint.json").read_text())

    steps = _steps_from_draft(incident)
    by_name = {s["name"]: s for s in steps}

    assert by_name["Transcribe audio recording"]["type"] == "ai"
    assert by_name["Record voice description and optional photo"]["type"] == "io"
    assert by_name["Safety manager reviews and approves report"]["type"] == "human_review"
