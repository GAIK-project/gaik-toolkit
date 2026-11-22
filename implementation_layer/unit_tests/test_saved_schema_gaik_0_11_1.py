"""A schema folder saved by gaik 0.11.1 still extracts as it did (review of #317).

``fixtures/schema_folder_gaik_0_11_1`` was written with gaik v0.11.1's own code
(``VisionExtractor``'s ``_save_schema_to_python``, ``save_model_file`` and
``_save_requirements``); only its ``schema.py``, which loading never reads, was
reformatted by ruff. 0.11.1 saved a number field with choices as a ``Literal`` of
texts (``Literal['', '1', ..., '5']``) and a ``list[str]`` field with choices as one
``Literal``. A choice must stay in the type the model in use gives it: never a
number where that model is text. Offline: the model call is replaced by a canned
answer.
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from typing import Literal, Optional
from unittest import mock

import pytest
from gaik.software_components.extractor import DataExtractor
from gaik.software_components.extractor.saved_schema import load_saved_model
from gaik.software_components.vision_extractor import VisionExtractor
from gaik.software_components.vision_extractor.vision_extractor import (
    SCHEMA_MODEL_FILE,
    _load_saved_requirements,
)

FIXTURE = Path(__file__).parent / "fixtures" / "schema_folder_gaik_0_11_1"


@pytest.fixture
def folder(tmp_path) -> Path:
    copy = tmp_path / "schema"
    shutil.copytree(FIXTURE, copy)
    return copy


def _loaded(folder: Path):
    name, requirements = _load_saved_requirements(folder / "requirements.json")
    return load_saved_model(folder / SCHEMA_MODEL_FILE, name, requirements), requirements


def test_the_folder_loads_the_model_0_11_1_saved(folder):
    model, requirements = _loaded(folder)

    fields = model.model_fields
    assert fields["rating"].annotation == Optional[Literal["", "1", "2", "3", "4", "5"]]
    assert fields["moisture_level"].annotation == Optional[Literal["", "0.5", "1"]]
    assert fields["hazard_types"].annotation == Literal["", "fire", "chemical", "electrical"]
    by_name = {f.field_name: f for f in requirements.fields}
    assert by_name["rating"].field_type == "int"
    assert by_name["rating"].enum == ["1", "2", "3", "4", "5"]


def _vision_extract(folder: Path, answer: dict, monkeypatch) -> dict:
    extractor = VisionExtractor(api_config={"api_key": "unused", "model": "test-model"})
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (dict(answer), None))
    monkeypatch.setattr(extractor, "_check_input_limits", lambda paths: None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = extractor.extract(
            file_paths=["survey.png"], user_requirements="survey", schema_dir=folder
        ).data
    # The folder has its model file, so the saved model is used, not a rebuild.
    assert not [w for w in caught if "Rebuilt saved schema" in str(w.message)]
    return data


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        # What a provider answers to 0.11.1's schema: the choices as texts.
        (
            {"rating": "4", "moisture_level": "0.5", "hazard_types": "fire", "inspector": "A"},
            {"rating": "4", "moisture_level": "0.5", "hazard_types": "fire", "inspector": "A"},
        ),
        # Numbers, as a provider that drops the enum may answer, become the texts.
        (
            {"rating": 4, "moisture_level": 1, "hazard_types": ["chemical"], "inspector": "A"},
            {"rating": "4", "moisture_level": "1", "hazard_types": "chemical", "inspector": "A"},
        ),
        # A value that is no choice gets the fallback, as on 0.11.1.
        (
            {"rating": "9", "moisture_level": None, "hazard_types": [], "inspector": "A"},
            {"rating": None, "moisture_level": None, "hazard_types": "", "inspector": "A"},
        ),
    ],
)
def test_vision_extractor_keeps_the_saved_models_types(folder, monkeypatch, answer, expected):
    assert _vision_extract(folder, answer, monkeypatch) == expected


def test_data_extractor_returns_what_the_saved_model_gives(folder):
    model, requirements = _loaded(folder)
    parsed = model.model_validate(
        {"rating": "4", "moisture_level": "0.5", "hazard_types": "fire", "inspector": "A"}
    )
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.config = {"model": "test-model"}
    extractor.client = object()
    extractor.model = "test-model"
    extractor.temperature = 0.0
    extractor.reasoning_effort = None
    message = type("M", (), {"parsed": parsed})()
    resp = type("R", (), {"choices": [type("C", (), {"message": message})()], "usage": None})()
    with mock.patch("gaik.software_components.extractor.extractor._parse_with", return_value=resp):
        result, _ = extractor._extract_one(
            doc="d", extraction_model=model, requirements=requirements, user_requirements="u"
        )

    # As on 0.11.1: the rating stays the text the saved model gives, not 4.
    assert result == {
        "rating": "4",
        "moisture_level": "0.5",
        "hazard_types": ["fire"],
        "inspector": "A",
    }
