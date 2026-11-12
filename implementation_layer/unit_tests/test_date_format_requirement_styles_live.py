"""Live checks that a date field's output format survives the whole extraction chain.

The requirement styles here are the ones that went wrong in practice: a bullet that
names the field by its identifier and states the format after a comma (the Solution
Wizard writes requirements this way), and a line that lists several fields where only
one of them has a format. `test_schema_type_overrides.py` covers the same rules
offline on hand-written FieldSpecs; these tests add the model-written requirements and
the extraction itself.

Requires a valid API key (Azure OpenAI or OpenAI) in the environment.
"""

import pytest
from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    create_extraction_model,
    parse_user_requirements,
)

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = pytest.mark.llm


def _date_field(requirements, keyword: str):
    """The date field whose name contains ``keyword``; the model names the fields."""
    matches = [
        field
        for field in requirements.fields
        if keyword in field.field_name and "date" in field.field_name
    ]
    names = [field.field_name for field in requirements.fields]
    assert len(matches) == 1, f"expected one date field containing {keyword!r}: {names}"
    return matches[0]


IDENTIFIER_BULLET_TASK = """
Extract these fields from a purchase order.

- `po_number`: the purchase order number as written.
- `order_date`: the date the order was placed.
- `delivery_date`: the delivery date, formatted `DD/MM/YYYY` (for example `05/03/2027`).
"""

PURCHASE_ORDER = """
Purchase order PO-7741 was placed on 2 August 2026.
Delivery is due on 10 August 2026.
"""


def test_format_after_a_comma_in_an_identifier_bullet_reaches_the_extracted_value():
    requirements = parse_user_requirements(IDENTIFIER_BULLET_TASK)
    delivery = _date_field(requirements, "delivery")
    order = _date_field(requirements, "order")

    assert delivery.field_type == "date"
    assert delivery.format == "%d/%m/%Y"
    # The neighbour named no format, so it stays ISO.
    assert order.format is None

    model = create_extraction_model(requirements)
    results = DataExtractor(config=get_openai_config(use_azure=True)).extract(
        extraction_model=model,
        requirements=requirements,
        user_requirements=IDENTIFIER_BULLET_TASK,
        documents=[PURCHASE_ORDER],
    )

    assert len(results) == 1
    assert results[0][delivery.field_name] == "10/08/2026"
    assert results[0][order.field_name] == "2026-08-02"


LIST_LINE_TASK = """
Extract these fields from a purchase order:
Order date, delivery date (DD/MM/YYYY) and the buyer's name.
"""


def test_first_date_of_a_list_line_does_not_take_the_second_dates_format():
    requirements = parse_user_requirements(LIST_LINE_TASK)

    assert _date_field(requirements, "order").format is None
    assert _date_field(requirements, "delivery").format == "%d/%m/%Y"


ALL_DATES_TASK = """
Extract these fields from an invoice. Use DD.MM.YYYY for all dates.

- Invoice date
- Due date
- Invoice number
"""


def test_all_dates_format_applies_to_every_date_field():
    requirements = parse_user_requirements(ALL_DATES_TASK)

    assert _date_field(requirements, "invoice").format == "%d.%m.%Y"
    assert _date_field(requirements, "due").format == "%d.%m.%Y"
