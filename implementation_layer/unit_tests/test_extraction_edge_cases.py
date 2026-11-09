"""Extraction edge cases: an empty item list, class names, and Gemini's schema."""

from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
    sanitize_model_name,
)
from pydantic import BaseModel

import pytest


def _requirements(use_case_name: str = "order lines") -> ExtractionRequirements:
    return ExtractionRequirements(
        use_case_name=use_case_name,
        fields=[
            FieldSpec(field_name="name", field_type="str", description="Product name"),
            FieldSpec(field_name="qty", field_type="int", description="Quantity"),
        ],
    )


class _Client:
    """A provider client whose model returns ``answer``."""

    provider = "openai"
    model = "m"
    raw = None

    def __init__(self, answer: BaseModel):
        self.answer = answer

    def chat_parsed(self, **_):
        return self.answer

    def chat(self, *_args, **_kwargs): ...

    def chat_stream(self, *_args, **_kwargs): ...

    def embed(self, *_args, **_kwargs): ...


def _extract(answer: BaseModel, requirements: ExtractionRequirements) -> dict:
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.config = {}
    extractor.model = "m"
    extractor.temperature = 0
    extractor.reasoning_effort = None
    extractor.client = _Client(answer)
    record, _usage = extractor._extract_one("doc", type(answer), requirements, "task")
    return record


def test_a_collection_without_items_gets_no_item_fields_of_its_own():
    requirements = _requirements()
    item = create_extraction_model(requirements)

    class Collection(BaseModel):
        items: list[item]

    assert _extract(Collection(items=[]), requirements) == {"items": []}
    assert _extract(Collection(items=[item(name="bolt", qty=2)]), requirements) == {
        "items": [{"name": "bolt", "qty": 2}]
    }


def test_a_flat_record_still_gets_its_field_policies():
    requirements = _requirements()
    item = create_extraction_model(requirements)

    assert _extract(item(name="bolt", qty=2), requirements) == {"name": "bolt", "qty": 2}


@pytest.mark.parametrize(
    "use_case_name", ["near-miss report", "2024 budget", "COVID-19 tests", "Työmaapäiväkirja"]
)
def test_a_model_name_is_a_python_class_name(use_case_name):
    name = sanitize_model_name(use_case_name, suffix="_Extraction") + "_Extraction"

    assert name.isidentifier()
    assert len(name) <= 64
    assert create_extraction_model(_requirements(use_case_name)).__name__.isidentifier()


@pytest.mark.parametrize("use_case_name", ["near-miss report", "2024 budget"])
def test_a_saved_schema_loads_again_whatever_the_use_case_is_called(tmp_path, use_case_name):
    pytest.importorskip("fitz")
    from gaik.software_components.vision_extractor.vision_extractor import (
        _load_saved_schema,
        _save_schema_to_python,
    )

    model = create_extraction_model(_requirements(use_case_name))
    path = tmp_path / "schema.py"

    _save_schema_to_python(model, path)
    loaded = _load_saved_schema(path, model.__name__)

    assert loaded.model_json_schema()["properties"].keys() == {"name", "qty"}


def test_gemini_keeps_fields_named_like_schema_keywords():
    pytest.importorskip("fitz")
    from gaik.software_components.vision_extractor.vision_extractor import (
        _prepare_google_schema,
    )

    class Book(BaseModel):
        title: str
        pattern: str
        default: str
        maximum: int

    class Shelf(BaseModel):
        title: str
        books: list[Book]

    schema = _prepare_google_schema(Shelf.model_json_schema())

    assert set(schema["properties"]) == {"title", "books"}
    assert schema["properties"]["title"] == {"type": "string"}
    book = schema["properties"]["books"]["items"]
    assert set(book["properties"]) == {"title", "pattern", "default", "maximum"}
    assert set(book["required"]) == set(book["properties"])
    # The keywords themselves are still stripped.
    assert "title" not in schema and "title" not in book
