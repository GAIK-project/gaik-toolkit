"""Tests for Pydantic blueprint models (WP1)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import (
    Artifact,
    ArtifactSource,
    Blueprint,
    UseCase,
)

EXAMPLES = Path(__file__).parent.parent / "examples"


# ---------------------------------------------------------------------------
# Example blueprints load and validate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", [
    "incident_reporting_blueprint.json",
    "document_extraction_blueprint.json",
    "rag_workflow_blueprint.json",
])
def test_example_blueprints_load(filename):
    path = EXAMPLES / filename
    bp = Blueprint.from_file(path)
    assert bp.blueprint_version == "1.0"
    assert bp.use_case.id


# ---------------------------------------------------------------------------
# Artifact conditional rules
# ---------------------------------------------------------------------------

def test_generated_artifact_requires_produced_by():
    with pytest.raises(Exception):
        Artifact(
            type="text",
            source=ArtifactSource.GENERATED,
            optional=False,
            # produced_by intentionally missing
        )


def test_user_upload_artifact_must_not_have_produced_by():
    with pytest.raises(Exception):
        Artifact(
            type="audio",
            source=ArtifactSource.USER_UPLOAD,
            optional=False,
            produced_by="some_step",  # must be absent for user_upload
        )


def test_valid_generated_artifact():
    art = Artifact(
        type="text",
        source=ArtifactSource.GENERATED,
        optional=False,
        produced_by="transcribe_audio",
    )
    assert art.produced_by == "transcribe_audio"
    assert art.final_output is False


def test_optional_field_required():
    """optional has no default -- must be supplied explicitly."""
    with pytest.raises(Exception):
        Artifact(
            type="audio",
            source=ArtifactSource.USER_UPLOAD,
            # optional intentionally missing
        )


# ---------------------------------------------------------------------------
# Round-trip serialisation
# ---------------------------------------------------------------------------

def test_blueprint_round_trip(tmp_path):
    path = EXAMPLES / "incident_reporting_blueprint.json"
    bp = Blueprint.from_file(path)
    out = tmp_path / "round_trip.json"
    bp.to_file(out)
    bp2 = Blueprint.from_file(out)
    assert bp.use_case.id == bp2.use_case.id
    assert len(bp.workflow.steps) == len(bp2.workflow.steps)


# ---------------------------------------------------------------------------
# JSON Schema export
# ---------------------------------------------------------------------------

def test_export_json_schema(tmp_path):
    schema_path = tmp_path / "blueprint.schema.json"
    Blueprint.export_json_schema(schema_path)
    schema = json.loads(schema_path.read_text())
    assert schema.get("title") == "Blueprint"
    assert "properties" in schema
