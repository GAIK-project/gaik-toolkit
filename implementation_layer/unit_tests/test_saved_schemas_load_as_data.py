"""Saved extraction schemas load as data: rebuilt from JSON, never imported."""

from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest
from gaik.software_components.extractor.saved_schema import (
    SavedSchemaError,
    build_model,
    describe_model,
    load_saved_model,
    rebuild_from_requirements,
)
from gaik.software_components.extractor.schema import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    _create_parent_with_nested_list_model,
    create_extraction_model,
)
from pydantic import BaseModel, ConfigDict, Field, create_model


def _flat_requirements(name: str = "purchase order") -> ExtractionRequirements:
    return ExtractionRequirements(
        use_case_name=name,
        fields=[
            FieldSpec(field_name="number", field_type="str", description='Order "no."'),
            FieldSpec(field_name="code", field_type="str", description="c", pattern=r"^[A-Z]+$"),
            FieldSpec(field_name="quantity", field_type="int", description="q"),
            FieldSpec(field_name="weight", field_type="float", description="w", nullable=True),
            FieldSpec(field_name="paid", field_type="bool", description="p"),
            FieldSpec(field_name="date", field_type="date", description="d"),
            FieldSpec(field_name="tags", field_type="list[str]", description="t"),
            FieldSpec(field_name="extras", field_type="list[dict]", description="e"),
            FieldSpec(
                field_name="note",
                field_type="str",
                description="n",
                required_in_output=False,
                nullable=True,
            ),
            FieldSpec(
                field_name="count",
                field_type="int",
                description="c",
                has_explicit_default=True,
                default="3",
            ),
        ],
    )


def _decimal_requirements() -> ExtractionRequirements:
    return ExtractionRequirements(
        use_case_name="prices",
        fields=[
            FieldSpec(field_name="price", field_type="decimal", description="price"),
            FieldSpec(
                field_name="fee",
                field_type="decimal",
                description="fee",
                has_explicit_default=True,
                default="9.99",
            ),
            FieldSpec(field_name="tax", field_type="decimal", description="tax", nullable=True),
        ],
    )


def _enum_requirements() -> ExtractionRequirements:
    return ExtractionRequirements(
        use_case_name="status",
        fields=[
            FieldSpec(field_name="state", field_type="str", description="s", enum=["open", "done"]),
            FieldSpec(
                field_name="priority",
                field_type="str",
                description="p",
                enum=["low", "high"],
                has_explicit_default=True,
                default="normal",
            ),
            FieldSpec(
                field_name="kind",
                field_type="str",
                description="k",
                enum=["a", "b"],
                nullable=True,
            ),
        ],
    )


def _nested_model() -> type[BaseModel]:
    """The shape parse_nested_requirements builds: one container of items."""
    item = create_extraction_model(_flat_requirements("line item"))
    return create_model(
        "line_item_Collection",
        __config__=ConfigDict(extra="forbid"),
        __doc__="Collection of line item items",
        entries=(list[item], Field(description="Rows of the 'table'")),
    )


def _composite_requirements() -> CompositeExtractionRequirements:
    return CompositeExtractionRequirements(
        parent_requirements=_flat_requirements("invoice"),
        children=[
            ChildRequirements(
                container_name="line_items",
                container_description="Lines",
                requirements=_decimal_requirements(),
            ),
            ChildRequirements(
                container_name="statuses",
                container_description="Statuses",
                requirements=_enum_requirements(),
            ),
        ],
    )


def _composite_model() -> type[BaseModel]:
    req = _composite_requirements()
    return _create_parent_with_nested_list_model(
        parent_requirements=req.parent_requirements, children=req.children
    )


FLAT_SAMPLE = {
    "number": "PO-1",
    "code": "ABC",
    "quantity": "2",
    "paid": True,
    "date": "2026-11-12",
    "tags": ["a"],
    "extras": [{"k": 1}],
}
DECIMAL_SAMPLE = {"price": "12.40 EUR", "tax": "1,234.50"}
ENUM_SAMPLE = {"state": "done", "kind": None}


class Urgency(str, Enum):
    LOW = "low"
    HIGH = "high"


class Ticket(BaseModel):
    """A ticket written the way the Solution Wizard's schema designer writes one."""

    model_config = ConfigDict(extra="forbid")

    urgency: Urgency = Field(description="How urgent")
    previous: Urgency | None = Field(default=Urgency.LOW, description="Earlier urgency")
    history: list[Urgency] = Field(default_factory=list, description="All urgencies")


STRUCTURES = {
    "flat": (lambda: create_extraction_model(_flat_requirements()), [FLAT_SAMPLE, {}]),
    "nested": (_nested_model, [{"entries": [FLAT_SAMPLE, FLAT_SAMPLE]}, {"entries": [{}]}]),
    "parent_with_children": (
        _composite_model,
        [
            {
                **FLAT_SAMPLE,
                "line_items": [DECIMAL_SAMPLE, {"price": "abc1def2"}],
                "statuses": [ENUM_SAMPLE],
            },
            {**FLAT_SAMPLE, "line_items": [], "statuses": [{"state": "closed"}]},
        ],
    ),
    "decimals": (
        lambda: create_extraction_model(_decimal_requirements()),
        [DECIMAL_SAMPLE, {"price": "1 234,56 EUR", "fee": None}],
    ),
    "enums": (
        lambda: create_extraction_model(_enum_requirements()),
        [ENUM_SAMPLE, {"state": "other"}, {"priority": "normal"}],
    ),
    "enum_classes": (
        lambda: Ticket,
        [
            {"urgency": "high", "history": ["low", "high"]},
            {"urgency": "medium"},
            {"urgency": "low", "previous": None},
        ],
    ),
}


def _outcome(model: type[BaseModel], data: dict):
    try:
        return ("ok", model.model_validate(data).model_dump(mode="json"))
    except Exception as exc:  # the same error kinds and locations
        return ("error", sorted(str(e["loc"]) for e in exc.errors()))


@pytest.mark.parametrize("structure", sorted(STRUCTURES))
def test_rebuilt_model_has_the_same_json_schema_and_validates_the_same(structure):
    make, samples = STRUCTURES[structure]
    original = make()

    description = json.loads(json.dumps(describe_model(original)))
    rebuilt = build_model(description)

    assert rebuilt.__name__ == original.__name__
    assert rebuilt.__doc__ == original.__doc__
    assert rebuilt.model_json_schema() == original.model_json_schema()
    for sample in samples:
        assert _outcome(rebuilt, sample) == _outcome(original, sample)


def test_rebuilt_decimal_fields_keep_their_cleanup_and_defaults():
    original = create_extraction_model(_decimal_requirements())
    rebuilt = build_model(json.loads(json.dumps(describe_model(original))))

    assert rebuilt(price="12.40 EUR").price == Decimal("12.40")
    assert rebuilt(price="abc1def2").price is None
    assert rebuilt.model_fields["fee"].annotation is Decimal
    assert rebuilt.model_fields["fee"].default == Decimal("9.99")
    assert "pattern" not in json.dumps(rebuilt.model_json_schema())


def test_nested_models_are_described_before_the_models_using_them():
    names = [m["name"] for m in describe_model(_composite_model())["models"]]
    assert names[-1] == _composite_model().__name__
    assert set(names[:-1]) == {"prices_Extraction", "status_Extraction"}


# --- what cannot be described or rebuilt is refused ---------------------------


def test_a_model_with_constraints_it_cannot_hold_is_not_described():
    class Bounded(BaseModel):
        amount: int = Field(ge=0)

    with pytest.raises(SavedSchemaError):
        describe_model(Bounded)


def _valid_description() -> dict:
    return describe_model(create_extraction_model(_flat_requirements()))


def _with(change) -> dict:
    description = _valid_description()
    change(description)
    return description


INVALID = {
    "unknown type": lambda d: d["models"][0]["fields"][0].update(type={"type": "os.system"}),
    "unknown key": lambda d: d["models"][0]["fields"][0].update(code="print(1)"),
    "other format": lambda d: d.update(format="something-else"),
    "newer version": lambda d: d.update(version=99),
    "private field name": lambda d: d["models"][0]["fields"][0].update(name="_hidden"),
    "model used before it is described": lambda d: d["models"][0]["fields"][0].update(
        type={"type": "model", "name": "Elsewhere"}
    ),
    "missing root": lambda d: d.update(root="Nope"),
    "object default": lambda d: d["models"][0]["fields"][0].update(default={"a": 1}),
}


@pytest.mark.parametrize("case", sorted(INVALID))
def test_an_invalid_description_is_refused(case):
    with pytest.raises(SavedSchemaError):
        build_model(_with(INVALID[case]))


# --- a .py file in the schema folder is never run ----------------------------


def _write_marker_module(path: Path, marker: Path) -> None:
    """A .py file whose only effect, when run, is to create ``marker``."""
    path.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )


def _write_requirements(path: Path, model_name: str, requirements) -> None:
    payload = {"model_name": model_name, "requirements": requirements.model_dump()}
    if isinstance(requirements, CompositeExtractionRequirements):
        payload["requirements_type"] = "parent_with_nested_list"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pipelines():
    pytest.importorskip("fitz")
    from gaik.software_modules.audio_to_structured_data.pipeline import AudioToStructuredData
    from gaik.software_modules.documents_to_structured_data.pipeline import (
        DocumentsToStructuredData,
    )

    return [AudioToStructuredData, DocumentsToStructuredData]


@pytest.mark.parametrize("which", [0, 1])
def test_pipeline_load_does_not_run_the_saved_python_file(which, tmp_path):
    pipeline = object.__new__(_pipelines()[which])
    requirements = _flat_requirements()
    model = create_extraction_model(requirements)
    pipeline.save_schema(model, requirements, tmp_path, "orders")
    assert (tmp_path / "orders_model.json").exists()
    marker = tmp_path / "marker.txt"
    _write_marker_module(tmp_path / "orders.py", marker)

    loaded, loaded_requirements = pipeline.load_schema(tmp_path, "orders")

    assert not marker.exists()
    assert loaded.model_json_schema() == model.model_json_schema()
    assert loaded_requirements == requirements


@pytest.mark.parametrize("which", [0, 1])
def test_pipeline_rebuilds_an_older_flat_folder_from_its_requirements(which, tmp_path):
    pipeline = object.__new__(_pipelines()[which])
    requirements = _flat_requirements()
    model = create_extraction_model(requirements)
    marker = tmp_path / "marker.txt"
    _write_marker_module(tmp_path / "orders.py", marker)
    _write_requirements(tmp_path / "orders_requirements.json", model.__name__, requirements)

    loaded, _ = pipeline.load_schema(tmp_path, "orders")

    assert not marker.exists()
    assert loaded.model_json_schema() == model.model_json_schema()
    # The next load reads the description written now.
    assert (tmp_path / "orders_model.json").exists()


@pytest.mark.parametrize("which", [0, 1])
def test_pipeline_refuses_an_older_nested_folder_instead_of_generating_over_it(which, tmp_path):
    pipeline = object.__new__(_pipelines()[which])
    marker = tmp_path / "marker.txt"
    _write_marker_module(tmp_path / "orders.py", marker)
    _write_requirements(
        tmp_path / "orders_requirements.json",
        "line_item_Collection",
        _flat_requirements("line item"),
    )

    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(SavedSchemaError, match="write_model_file") as refused:
        pipeline.load_schema(tmp_path, "orders")

    assert str(tmp_path) in str(refused.value)
    assert not marker.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def _vision_extractor():
    pytest.importorskip("fitz")
    from gaik.software_components.vision_extractor import vision_extractor

    return vision_extractor


def test_vision_extractor_does_not_run_the_saved_python_file(tmp_path):
    ve = _vision_extractor()
    requirements = _composite_requirements()
    model = _composite_model()
    ve._save_schema_to_python(model, tmp_path / "schema.py")
    ve.save_model_file(model, tmp_path / ve.SCHEMA_MODEL_FILE)
    ve._save_requirements(requirements, model.__name__, tmp_path / "requirements.json")
    marker = tmp_path / "marker.txt"
    _write_marker_module(tmp_path / "schema.py", marker)

    extractor = object.__new__(ve.VisionExtractor)
    loaded, loaded_requirements = extractor._resolve_schema("unused", tmp_path)

    assert not marker.exists()
    assert loaded.model_json_schema() == model.model_json_schema()
    assert loaded_requirements == requirements


def test_vision_extractor_rebuilds_an_older_folder_from_its_requirements(tmp_path):
    ve = _vision_extractor()
    requirements = _composite_requirements()
    model = _composite_model()
    marker = tmp_path / "marker.txt"
    _write_marker_module(tmp_path / "schema.py", marker)
    ve._save_requirements(requirements, model.__name__, tmp_path / "requirements.json")

    extractor = object.__new__(ve.VisionExtractor)
    loaded, _ = extractor._resolve_schema("unused", tmp_path)

    assert not marker.exists()
    assert loaded.model_json_schema() == model.model_json_schema()
    assert (tmp_path / ve.SCHEMA_MODEL_FILE).exists()


def test_a_nested_model_cannot_be_rebuilt_from_requirements_alone(tmp_path):
    requirements = _flat_requirements("line item")
    assert rebuild_from_requirements("line_item_Collection", requirements) is None
    with pytest.raises(SavedSchemaError, match="cannot be rebuilt"):
        load_saved_model(tmp_path / "absent.json", "line_item_Collection", requirements)


def test_requirements_for_another_model_are_not_used_to_rebuild():
    assert rebuild_from_requirements("Other_Extraction", _flat_requirements()) is None
