"""Generated parent/child schemas must reload through the actual PoC pipelines."""

import importlib.util
import json
from pathlib import Path

import pytest
from gaik.software_components.extractor import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.extractor.schema import _create_parent_with_nested_list_model
from gaik.software_modules.audio_to_structured_data import AudioToStructuredData
from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData


@pytest.mark.parametrize("pipeline_class", [DocumentsToStructuredData, AudioToStructuredData])
@pytest.mark.parametrize("explicit_type", [True, False])
def test_generated_composite_schema_reloads(pipeline_class, explicit_type, tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "generate_schema.py"
    spec = importlib.util.spec_from_file_location("_composite_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    parent = ExtractionRequirements(
        use_case_name="invoice",
        fields=[FieldSpec(field_name="invoice_id", field_type="str", description="Invoice ID")],
    )
    child = ChildRequirements(
        container_name="lines",
        container_description="Invoice lines",
        requirements=ExtractionRequirements(
            use_case_name="invoice_line",
            fields=[FieldSpec(field_name="amount", field_type="decimal", description="Amount")],
        ),
    )
    requirements = CompositeExtractionRequirements(parent_requirements=parent, children=[child])
    model = _create_parent_with_nested_list_model(parent_requirements=parent, children=[child])
    (tmp_path / "output_schema.py").write_text(
        cli._schema_to_py(model, "Invoice"), encoding="utf-8"
    )
    payload = cli._requirements_to_json(model, requirements)
    if not explicit_type:
        payload.pop("requirements_type")
    (tmp_path / "output_schema_requirements.json").write_text(json.dumps(payload), encoding="utf-8")

    # Loading is independent of providers and must not initialize a remote client.
    pipeline = object.__new__(pipeline_class)
    loaded_schema, loaded_requirements = pipeline.load_schema(tmp_path, "output_schema")
    assert loaded_requirements == requirements
    invoice = loaded_schema.model_validate(
        {"invoice_id": "GAIK-42", "lines": [{"amount": "12.40 EUR"}]}
    )
    assert str(invoice.lines[0].amount) == "12.40"
    assert invoice.invoice_id == "GAIK-42"
