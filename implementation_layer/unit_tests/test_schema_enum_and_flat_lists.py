"""Offline regression tests for #141 items 1-4: US dates, enums on list and number
fields, and a flat record's own ``list[dict]`` field."""

import json
from decimal import Decimal

import pytest
from gaik.software_components.extractor import schema
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    StructureAnalysis,
    _holds_items,
    apply_field_policies,
    create_extraction_model,
    normalize_extracted_data,
    parse_date,
    parse_nested_requirements,
)
from gaik.software_components.vision_extractor.vision_extractor import VisionExtractor
from pydantic import BaseModel, ValidationError


def _requirements(*fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="case", fields=list(fields))


# Item 1 --------------------------------------------------------------------


def test_us_date_keeps_day_and_month_in_its_own_format():
    assert parse_date("03/07/2024", "%m/%d/%Y") == "03/07/2024"
    assert parse_date("03/17/2024", "%m/%d/%Y") == "03/17/2024"


def test_normalize_keeps_a_us_date_with_day_at_most_twelve():
    requirements = _requirements(
        FieldSpec(field_name="due", field_type="date", description="Due", format="%m/%d/%Y")
    )

    assert normalize_extracted_data({"due": "03/07/2024"}, requirements) == {"due": "03/07/2024"}


def test_iso_output_still_reads_a_day_first_date():
    assert parse_date("25/04/2024") == "2024-04-25"


# Item 2 --------------------------------------------------------------------


def _enum_fields():
    return _requirements(
        FieldSpec(
            field_name="hazard_types",
            field_type="list[str]",
            description="Hazards",
            enum=["fire", "chemical", "electrical"],
        ),
        FieldSpec(
            field_name="rating",
            field_type="int",
            description="Rating",
            enum=["1", "2", "3", "4", "5"],
        ),
        FieldSpec(field_name="score", field_type="float", description="Score", enum=["0.5", "1.0"]),
    )


def test_enum_on_list_and_number_fields_keeps_their_type():
    model = create_extraction_model(_enum_fields())

    parsed = model.model_validate({"hazard_types": ["fire", "chemical"], "rating": 3, "score": 0.5})

    assert parsed.hazard_types == ["fire", "chemical"]
    assert parsed.rating == 3
    properties = model.model_json_schema()["properties"]
    assert properties["hazard_types"]["type"] == "array"
    assert set(properties["hazard_types"]["items"]["enum"]) == {"fire", "chemical", "electrical"}
    rating_enum = next(
        option["enum"] for option in properties["rating"]["anyOf"] if "enum" in option
    )
    assert rating_enum == [1, 2, 3, 4, 5]


def test_enum_on_list_and_number_fields_still_rejects_other_values():
    model = create_extraction_model(_enum_fields())

    with pytest.raises(ValidationError):
        model.model_validate({"hazard_types": ["flood"], "rating": 3, "score": 0.5})
    with pytest.raises(ValidationError):
        model.model_validate({"hazard_types": [], "rating": 9, "score": 0.5})


def test_field_policies_keep_correct_list_and_number_answers():
    data = {"hazard_types": ["fire", "chemical"], "rating": 3, "score": 1.0}

    assert apply_field_policies(data, _enum_fields()) == data


def test_field_policies_drop_only_values_outside_the_enum():
    data = {"hazard_types": ["fire", "flood"], "rating": 9, "score": 0.7}

    assert apply_field_policies(data, _enum_fields()) == {
        "hazard_types": ["fire"],
        "rating": None,
        "score": None,
    }


def test_a_decimal_enum_is_read_with_the_decimal_cleaner():
    price = FieldSpec(
        field_name="price", field_type="decimal", description="Price", enum=["10.00", "20.00"]
    )
    priced = _requirements(price)

    assert apply_field_policies({"price": "10.00 EUR"}, priced) == {"price": "10.00 EUR"}
    assert create_extraction_model(priced).model_validate({"price": "10.00 EUR"}).price == Decimal(
        "10.00"
    )
    assert apply_field_policies({"price": "30.00 EUR"}, priced) == {"price": None}


def test_a_decimal_enum_written_with_a_currency_still_limits_the_value():
    price = FieldSpec(
        field_name="price",
        field_type="decimal",
        description="Price",
        enum=["10.00 EUR", "20.00 EUR"],
    )

    assert apply_field_policies({"price": "99.00"}, _requirements(price)) == {"price": None}
    assert apply_field_policies({"price": "20.00"}, _requirements(price)) == {"price": "20.00"}


# Item 3 --------------------------------------------------------------------


def _invoice():
    return _requirements(
        FieldSpec(field_name="invoice_number", field_type="str", description="Number"),
        FieldSpec(field_name="total", field_type="float", description="Total"),
        FieldSpec(field_name="line_items", field_type="list[dict]", description="Rows"),
    )


def test_a_flat_records_own_list_of_dicts_is_not_an_item_container():
    assert not _holds_items("line_items", [{"product": "Bolt", "qty": 3}], _invoice())


def test_a_container_of_items_is_still_recognised():
    item = _requirements(FieldSpec(field_name="product", field_type="str", description="P"))

    assert _holds_items("records", [{"product": "Bolt"}], item)
    assert _holds_items("records", [], item)


def _dated_invoice():
    return _requirements(
        FieldSpec(field_name="date", field_type="date", description="Date", format="%d.%m.%Y"),
        FieldSpec(field_name="tags", field_type="list[str]", description="Tags"),
        FieldSpec(field_name="line_items", field_type="list[dict]", description="Rows"),
    )


_DATED_ROWS = [{"date": "2024-07-03", "tags": "a, b"}]


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


def test_data_extractor_leaves_a_flat_records_own_rows_alone():
    requirements = _dated_invoice()
    model = create_extraction_model(requirements)
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.config, extractor.model = {}, "m"
    extractor.temperature, extractor.reasoning_effort = 0, None
    extractor.client = _Client(model(date="03.07.2024", tags=["x"], line_items=_DATED_ROWS))

    record, _usage = extractor._extract_one("doc", model, requirements, "task")

    assert record == {"date": "03.07.2024", "tags": ["x"], "line_items": _DATED_ROWS}


def test_vision_extractor_leaves_a_flat_records_own_rows_alone():
    raw = {"date": "03.07.2024", "tags": "x, y", "line_items": [dict(_DATED_ROWS[0])]}

    record = VisionExtractor._post_process(None, raw, _dated_invoice())

    assert record == {"date": "03.07.2024", "tags": ["x", "y"], "line_items": _DATED_ROWS}


# Item 4 --------------------------------------------------------------------


def _analysis(structure_type: str) -> StructureAnalysis:
    return StructureAnalysis(
        structure_type=structure_type,
        parent_container_name="",
        parent_description="",
        item_description="",
        reasoning="stub",
    )


def test_flat_parse_with_a_list_of_dicts_becomes_parent_with_children(monkeypatch):
    calls = []

    def fake_parse(task, *, parse_mode="normal", **_kwargs):
        calls.append(parse_mode)
        if parse_mode == "repeated_item":
            return _requirements(
                FieldSpec(field_name="product", field_type="str", description="Product"),
                FieldSpec(field_name="qty", field_type="int", description="Quantity"),
            )
        if task.startswith("From the requirements below, parse only the once-per-document"):
            return _requirements(
                FieldSpec(field_name="invoice_number", field_type="str", description="Number")
            )
        return _invoice()

    monkeypatch.setattr(schema, "detect_structure_type", lambda *a, **k: _analysis("flat"))
    monkeypatch.setattr(schema, "parse_user_requirements", fake_parse)

    model, requirements, analysis = parse_nested_requirements(
        "Invoice number, total and line items", client=object(), model="stub"
    )

    assert isinstance(requirements, CompositeExtractionRequirements)
    assert analysis.structure_type == "parent_with_nested_list"
    assert [c.container_name for c in requirements.children] == ["line_items"]
    assert 'additionalProperties": true' not in json.dumps(model.model_json_schema())
    assert calls == ["normal", "normal", "repeated_item"]


def test_a_collection_without_item_fields_reports_a_flat_structure(monkeypatch):
    def fake_parse(task, *, parse_mode="normal", **_kwargs):
        if parse_mode == "repeated_item":
            return _requirements()
        title = FieldSpec(field_name="title", field_type="str", description="Title")
        if task.startswith("From the requirements below, parse only the once-per-document"):
            return _requirements(title)
        notes = FieldSpec(field_name="notes", field_type="list[dict]", description="Notes")
        return _requirements(title, notes)

    monkeypatch.setattr(schema, "detect_structure_type", lambda *a, **k: _analysis("flat"))
    monkeypatch.setattr(schema, "parse_user_requirements", fake_parse)

    _model, requirements, analysis = parse_nested_requirements(
        "Title and notes", client=object(), model="stub"
    )

    assert isinstance(requirements, ExtractionRequirements)
    assert [(f.field_name, f.field_type) for f in requirements.fields] == [
        ("title", "str"),
        ("notes", "list[str]"),
    ]
    assert analysis.structure_type == "flat"
