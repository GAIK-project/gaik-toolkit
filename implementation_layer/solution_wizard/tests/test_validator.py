"""Tests for BlueprintValidator (WP3)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import (
    Artifact,
    ArtifactSource,
    Blueprint,
    Components,
    SelectedModule,
    UseCase,
    Workflow,
    WorkflowStep,
)
from solution_wizard.validator import validate

EXAMPLES = Path(__file__).parent.parent / "examples"


def _base_blueprint(**overrides) -> Blueprint:
    data = dict(
        use_case=UseCase(id="test", name="Test", description="Test", domain="test"),
        artifacts={
            "input_audio": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
            "transcript": Artifact(type="transcript", source=ArtifactSource.GENERATED, optional=False, produced_by="step_a", final_output=True),
        },
        components=Components(selected_building_blocks=["Transcriber"]),
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="Transcribe", type="automated_task", component="Transcriber", inputs=["input_audio"], outputs=["transcript"]),
        ]),
    )
    data.update(overrides)
    return Blueprint(**data)


# ---------------------------------------------------------------------------
# Examples pass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", [
    "incident_reporting_blueprint.json",
    "document_extraction_blueprint.json",
    "rag_workflow_blueprint.json",
])
def test_example_blueprints_validate(filename):
    bp = Blueprint.from_file(EXAMPLES / filename)
    result = validate(bp)
    assert result.ok, result.summary()


# ---------------------------------------------------------------------------
# Rule 1: unique step IDs
# ---------------------------------------------------------------------------

def test_rule1_duplicate_step_id():
    bp = _base_blueprint(
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="A", type="automated_task", component="Transcriber", inputs=["input_audio"], outputs=["transcript"]),
            WorkflowStep(id="step_a", name="A dup", type="automated_task", component="Transcriber", inputs=["input_audio"], outputs=["transcript"]),
        ])
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 1 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 2: undeclared artifact reference
# ---------------------------------------------------------------------------

def test_rule2_undeclared_artifact():
    bp = _base_blueprint(
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="A", type="automated_task", component="Transcriber", inputs=["nonexistent_artifact"], outputs=["transcript"]),
        ])
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 2 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 3: unknown component
# ---------------------------------------------------------------------------

def test_rule3_unknown_component():
    bp = _base_blueprint(
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="A", type="automated_task", component="GhostComponent", inputs=["input_audio"], outputs=["transcript"]),
        ])
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 3 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 7: artifact consumed before produced
# ---------------------------------------------------------------------------

def test_rule7_consume_before_produce():
    bp = Blueprint(
        use_case=UseCase(id="t", name="T", description="T", domain="t"),
        artifacts={
            "src": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
            "mid": Artifact(type="text", source=ArtifactSource.GENERATED, optional=False, produced_by="step_b"),
            "out": Artifact(type="structured_json", source=ArtifactSource.GENERATED, optional=False, produced_by="step_a", final_output=True),
        },
        workflow=Workflow(steps=[
            # step_a consumes 'mid' which is produced by step_b (later)
            WorkflowStep(id="step_a", name="A", type="automated_task", component="Extractor", inputs=["mid"], outputs=["out"]),
            WorkflowStep(id="step_b", name="B", type="automated_task", component="Transcriber", inputs=["src"], outputs=["mid"]),
        ]),
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 7 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 8: cycle detection
# ---------------------------------------------------------------------------

def test_rule8_cycle_detected():
    bp = Blueprint(
        use_case=UseCase(id="t", name="T", description="T", domain="t"),
        artifacts={
            "a": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
            "b": Artifact(type="text", source=ArtifactSource.GENERATED, optional=False, produced_by="step_a", final_output=True),
        },
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="A", type="automated_task", component="Transcriber", inputs=["a"], outputs=["b"], depends_on=["step_b"]),
            WorkflowStep(id="step_b", name="B", type="automated_task", component="Transcriber", inputs=["a"], outputs=["b"], depends_on=["step_a"]),
        ]),
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 8 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 7b: produced_by must match step.outputs (crosscheck)
# ---------------------------------------------------------------------------

def test_rule7_produced_by_not_in_step_outputs():
    """Artifact claims produced_by a step that doesn't list it in outputs."""
    bp = Blueprint(
        use_case=UseCase(id="t", name="T", description="T", domain="t"),
        artifacts={
            "src": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
            "out": Artifact(
                type="text", source=ArtifactSource.GENERATED, optional=False,
                produced_by="step_a",   # step_a outputs "other_thing", not "out"
                final_output=True,
            ),
            "other_thing": Artifact(
                type="text", source=ArtifactSource.GENERATED, optional=False,
                produced_by="step_a", final_output=False,
            ),
        },
        workflow=Workflow(steps=[
            WorkflowStep(
                id="step_a", name="A", type="automated_task",
                component="Transcriber",
                inputs=["src"],
                outputs=["other_thing"],  # does NOT include "out"
            ),
        ]),
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 7 and "out" in e.message for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 9: no final output
# ---------------------------------------------------------------------------

def test_rule9_no_final_output():
    bp = Blueprint(
        use_case=UseCase(id="t", name="T", description="T", domain="t"),
        artifacts={
            "src": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
            "out": Artifact(type="text", source=ArtifactSource.GENERATED, optional=False, produced_by="step_a", final_output=False),
        },
        workflow=Workflow(steps=[
            WorkflowStep(id="step_a", name="A", type="automated_task", component="Transcriber", inputs=["src"], outputs=["out"]),
        ]),
    )
    result = validate(bp)
    assert not result.ok
    assert any(e.rule == 9 for e in result.errors)


# ---------------------------------------------------------------------------
# Rule 12: redundant subsumed sub-component (warning, non-blocking) -- V3
# ---------------------------------------------------------------------------

def _audio_enhance_data(separate_enhancer: bool) -> dict:
    steps = [
        {"id": "transcribe", "name": "Transcribe", "type": "automated_task", "component": "Transcriber",
         "inputs": ["src_audio"], "outputs": ["raw_transcript"]},
    ]
    artifacts = {
        "src_audio": {"type": "audio", "source": "user_upload", "optional": False},
        "raw_transcript": {"type": "transcript", "source": "generated", "optional": False,
                            "produced_by": "transcribe", "final_output": not separate_enhancer},
    }
    blocks = ["Transcriber"]
    if separate_enhancer:
        steps.append({"id": "enhance", "name": "Enhance", "type": "automated_task", "component": "TranscriptEnhancer",
                      "inputs": ["raw_transcript"], "outputs": ["enh_transcript"], "depends_on": ["transcribe"]})
        artifacts["enh_transcript"] = {"type": "enhanced_transcript", "source": "generated", "optional": False,
                                       "produced_by": "enhance", "final_output": True}
        blocks.append("TranscriptEnhancer")
    return {
        "blueprint_version": "1.0",
        "use_case": {"id": "audio_uc", "name": "Audio", "description": "x", "domain": "test"},
        "components": {"selected_modules": [], "selected_building_blocks": blocks, "custom_components": []},
        "artifacts": artifacts,
        "workflow": {"steps": steps},
    }


def test_redundant_transcript_enhancer_warns_but_does_not_block():
    bp = Blueprint.model_validate(_audio_enhance_data(separate_enhancer=True))
    result = validate(bp)
    rule12 = [w for w in result.warnings if w.rule == 12]
    assert rule12, "expected a Rule-12 redundancy warning"
    assert any("TranscriptEnhancer" in w.message for w in rule12)
    assert result.ok, "redundancy is a warning, not a blocking error"


def test_no_redundancy_warning_for_single_transcriber():
    bp = Blueprint.model_validate(_audio_enhance_data(separate_enhancer=False))
    result = validate(bp)
    assert not [w for w in result.warnings if w.rule == 12]
