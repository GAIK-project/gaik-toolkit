"""The Extractor demo's schema step: a flat schema and one with a nested list."""

import asyncio
from types import SimpleNamespace

from api.routers import extractor
from api.utils.schema_view import structure_of
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_components.extractor.schema import create_extraction_model
from pydantic import BaseModel, Field


def _generate(monkeypatch, schema, requirements):
    class FakeGenerator:
        def __init__(self, *args, **kwargs):
            self.item_requirements = requirements

        def generate_schema(self, user_requirements):
            return schema

    monkeypatch.setattr("gaik.software_components.extractor.SchemaGenerator", FakeGenerator)
    monkeypatch.setattr(extractor, "get_api_config", lambda: {"model": "m"})
    monkeypatch.setattr(extractor, "get_model_options", lambda config: {})
    monkeypatch.setattr(extractor, "load_schema", lambda key, requirements: None)
    extractor._schema_cache.clear()
    task = "Extract the invoice number and the date."
    return asyncio.run(
        extractor.generate_schema(extractor.GenerateSchemaRequest(user_requirements=task))
    )


def test_a_flat_schema_comes_with_its_field_table(monkeypatch):
    requirements = ExtractionRequirements(
        use_case_name="invoice",
        fields=[
            FieldSpec(field_name="invoice_number", field_type="str", description="Number"),
            FieldSpec(
                field_name="invoice_date",
                field_type="date",
                description="Date",
                format="%d/%m/%Y",
                required=False,
            ),
        ],
    )

    response = _generate(monkeypatch, create_extraction_model(requirements), requirements)

    assert response.structure_type == "flat"
    assert [field["name"] for field in response.field_table] == ["invoice_number", "invoice_date"]
    assert response.field_table[1]["format"] == "DD/MM/YYYY"
    assert [field["name"] for field in response.fields] == ["invoice_number", "invoice_date"]
    assert "class " in response.schema_code


def test_a_schema_with_a_nested_list_does_not_need_flat_requirements(monkeypatch):
    class Line(BaseModel):
        name: str | None = Field(default=None, description="Item")

    class Order(BaseModel):
        number: str | None = Field(default=None, description="Order number")
        lines: list[Line] = Field(default_factory=list, description="Lines")

    # Composite requirements have no ``fields``: the table is read from the schema.
    requirements = SimpleNamespace(
        model_dump=lambda mode="json": {
            "parent_requirements": {"fields": [{"field_name": "number", "field_type": "str"}]},
            "children": [{"fields": [{"field_name": "name", "field_type": "str"}]}],
        }
    )

    response = _generate(monkeypatch, Order, requirements)

    assert response.structure_type == "parent_with_nested_list"
    assert response.field_table[1]["type"] == "list of records"
    assert response.field_table[1]["children"][0]["name"] == "name"


def test_the_structure_is_read_from_the_field_table():
    list_only = [{"name": "rows", "type": "list of records"}]
    mixed = [{"name": "a", "type": "text"}, {"name": "rows", "type": "list of records"}]

    assert structure_of(list_only) == "nested_list"
    assert structure_of(mixed) == "parent_with_nested_list"
    assert structure_of([{"name": "a", "type": "text"}]) == "flat"
