"""Saved schema files: the name stays inside schema_dir, the description stays text."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

pytest.importorskip("fitz")

from gaik.software_components.vision_extractor.vision_extractor import (  # noqa: E402
    _load_saved_schema,
    _save_schema_to_python,
)
from gaik.software_modules.audio_to_structured_data.pipeline import (  # noqa: E402
    AudioToStructuredData,
)
from gaik.software_modules.audio_to_structured_data.pipeline import (  # noqa: E402
    _schema_file_stem as audio_stem,
)
from gaik.software_modules.documents_to_structured_data.pipeline import (  # noqa: E402
    DocumentsToStructuredData,
)
from gaik.software_modules.documents_to_structured_data.pipeline import (  # noqa: E402
    _schema_file_stem as documents_stem,
)

BAD_NAMES = ["../outside", "nested/name", "nested\\name", "..", ".", "", "a\x00b"]
GOOD_NAMES = ["invoice", "Purchase Order v2", "meeting-notes_2026", "schema.v1"]


@pytest.mark.parametrize("stem", [audio_stem, documents_stem])
@pytest.mark.parametrize("name", BAD_NAMES)
def test_schema_name_with_a_path_is_rejected(stem, name):
    with pytest.raises(ValueError, match="Invalid schema_name"):
        stem(name)


@pytest.mark.parametrize("stem", [audio_stem, documents_stem])
@pytest.mark.parametrize("name", GOOD_NAMES)
def test_plain_schema_name_is_kept_as_it_is(stem, name):
    assert stem(name) == name


@pytest.mark.parametrize("pipeline", [AudioToStructuredData, DocumentsToStructuredData])
def test_load_and_save_refuse_a_name_outside_schema_dir(pipeline, tmp_path):
    schema_dir = tmp_path / "schemas"
    with pytest.raises(ValueError, match="Invalid schema_name"):
        pipeline.load_schema(None, schema_dir, "../outside")
    with pytest.raises(ValueError, match="Invalid schema_name"):
        pipeline.save_schema(None, BaseModel, None, schema_dir, "../outside")
    assert not schema_dir.exists()
    assert not (tmp_path / "outside.py").exists()


@pytest.mark.parametrize("pipeline", [AudioToStructuredData, DocumentsToStructuredData])
def test_load_returns_none_for_a_plain_name_without_files(pipeline, tmp_path):
    assert pipeline.load_schema(None, tmp_path, "invoice") is None


DESCRIPTIONS = [
    "Fields of one purchase order.",
    'Ends the text early: """ and continues with\nmarker = 1',
    "Backslashes \\ and 'single' and \"double\" quotes",
]


@pytest.mark.parametrize("description", DESCRIPTIONS)
def test_class_description_round_trips_as_text(description, tmp_path):
    class Order(BaseModel):
        number: str = Field(description="Order number")

    Order.__doc__ = description
    path = tmp_path / "schema.py"
    _save_schema_to_python(Order, path)

    loaded = _load_saved_schema(path, "Order")
    assert loaded.__doc__ == description.strip()
    assert list(loaded.model_fields) == ["number"]
    # Nothing in the description became a statement of the saved module.
    assert "marker = 1" not in [line.strip() for line in path.read_text("utf-8").splitlines()]
