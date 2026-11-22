"""Deterministic guards for LLM-generated field metadata."""

import pytest
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    _apply_type_overrides,
    normalize_extracted_data,
)


def _requirements(*fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="test", fields=list(fields))


def test_invalid_llm_date_format_is_cleared_and_normalizes_to_iso():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order Date",
            format="date",
        )
    )

    _apply_type_overrides(requirements, original_text="- Order Date")

    assert requirements.fields[0].format is None
    assert normalize_extracted_data({"order_date": "October 12, 2025"}, requirements) == {
        "order_date": "2025-10-12"
    }


def test_normalizer_rejects_invalid_format_even_without_schema_cleanup():
    requirements = _requirements(
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="Delivery Date",
            format="lowercase_with_underscores",
        )
    )

    assert normalize_extracted_data({"delivery_date": "December 01, 2025"}, requirements) == {
        "delivery_date": "2025-12-01"
    }


def test_date_format_is_scoped_to_its_own_field():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order Date",
            format="date",
        ),
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="Delivery Date",
            format="lowercase_with_underscores",
        ),
    )
    task = """
    - Order Date
    - Delivery Date (Format: DD/MM/YYYY).
    """

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


def test_explicit_global_date_format_applies_to_every_date():
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order Date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery Date"),
    )
    task = """
    Use DD.MM.YYYY for all dates.
    - Order Date
    - Delivery Date
    """

    _apply_type_overrides(requirements, original_text=task)

    assert [field.format for field in requirements.fields] == ["%d.%m.%Y", "%d.%m.%Y"]


@pytest.mark.parametrize(
    ("task_line", "value", "expected"),
    [
        # Issue #141 item 1: 7 March written month first stays as written.
        ("- Invoice date (MM/DD/YYYY)", "03/07/2024", "03/07/2024"),
        ("- Invoice date (MM/DD/YYYY)", "3/7/2024", "03/07/2024"),
        ("- Invoice date (MM-DD-YYYY)", "03-07-2024", "03-07-2024"),
        # A day above 12 was already read month first; it still is.
        ("- Invoice date (MM/DD/YYYY)", "03/25/2024", "03/25/2024"),
        # A value written day first is still converted to the field's format.
        ("- Invoice date (MM/DD/YYYY)", "25/03/2024", "03/25/2024"),
        ("- Invoice date (MM/DD/YYYY)", "2024-03-07", "03/07/2024"),
        # Day-first fields keep reading a day-first value day first.
        ("- Invoice date (DD/MM/YYYY)", "03/07/2024", "03/07/2024"),
        ("- Invoice date (DD.MM.YYYY)", "2024-07-03", "03.07.2024"),
    ],
)
def test_a_date_already_in_the_fields_own_format_is_read_in_that_format(task_line, value, expected):
    requirements = _requirements(
        FieldSpec(field_name="invoice_date", field_type="date", description="Invoice date")
    )

    _apply_type_overrides(requirements, original_text=task_line)

    assert normalize_extracted_data({"invoice_date": value}, requirements) == {
        "invoice_date": expected
    }


def test_parse_date_tries_the_output_format_first():
    from gaik.software_components.extractor.schema import parse_date

    assert parse_date("03/07/2024", "%m/%d/%Y") == "03/07/2024"
    assert parse_date("03/07/2024", "%d/%m/%Y") == "03/07/2024"
    # Without a format of its own, a slash date is still read day first, as before.
    assert parse_date("03/07/2024") == "2024-07-03"
    assert parse_date("not a date", "%m/%d/%Y") == "not a date"


def test_date_preserve_instruction_keeps_string_representation():
    requirements = _requirements(
        FieldSpec(
            field_name="drawing_date",
            field_type="date",
            description="Drawing Date",
            format="date",
        )
    )

    _apply_type_overrides(
        requirements,
        original_text="- Drawing Date (preserve format in string)",
    )

    field = requirements.fields[0]
    assert field.field_type == "str"
    assert field.format is None
    assert normalize_extracted_data({"drawing_date": "12 OCT 25"}, requirements) == {
        "drawing_date": "12 OCT 25"
    }


def test_plain_quantity_is_repaired_to_integer():
    requirements = _requirements(
        FieldSpec(field_name="quantity", field_type="str", description="Quantity")
    )

    _apply_type_overrides(requirements, original_text="- Quantity")

    assert requirements.fields[0].field_type == "int"


def test_unit_bearing_quantity_remains_string():
    requirements = _requirements(
        FieldSpec(field_name="quantity", field_type="str", description="Quantity")
    )

    _apply_type_overrides(
        requirements,
        original_text="- Quantity (text string including the unit, e.g. '4.200 kg')",
    )

    assert requirements.fields[0].field_type == "str"


def test_unrequested_pattern_and_non_date_format_are_cleared():
    requirements = _requirements(
        FieldSpec(
            field_name="buyer",
            field_type="str",
            description="Buyer",
            pattern="^.*$",
            format="string",
        )
    )

    _apply_type_overrides(requirements, original_text="- Buyer")

    field = requirements.fields[0]
    assert field.pattern is None
    assert field.format is None


def test_format_after_a_comma_in_the_fields_own_bullet_is_kept():
    requirements = _requirements(
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="The delivery date, formatted DD/MM/YYYY (for example 05/03/2027).",
        )
    )
    task = (
        "- `po_number`: the purchase order number as written.\n"
        "- `delivery_date`: the delivery date, formatted `DD/MM/YYYY` (for example "
        "`05/03/2027`). Convert from another written form only when day, month and year "
        "are all stated.\n"
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"
    assert normalize_extracted_data({"delivery_date": "10/08/2026"}, requirements) == {
        "delivery_date": "10/08/2026"
    }


def test_snake_case_heading_and_its_paragraph_carry_the_format():
    requirements = _requirements(
        FieldSpec(
            field_name="observation_date",
            field_type="date",
            description="Date the fault was observed, as DD/MM/YYYY (example: 29/09/2026).",
        )
    )
    task = (
        "### observation_date (optional)\n"
        "Date the fault was observed, as `DD/MM/YYYY` (example: `29/09/2026`).\n"
        "\n"
        "### observation_time (optional)\n"
        "Time the fault was observed, as HH:MM.\n"
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"
    assert normalize_extracted_data({"observation_date": "26/07/2026"}, requirements) == {
        "observation_date": "26/07/2026"
    }


def test_description_format_is_the_fallback_when_the_task_text_has_none():
    requirements = _requirements(
        FieldSpec(
            field_name="invoice_date",
            field_type="date",
            description="Invoice date, written as pp.kk.vvvv.",
        )
    )

    _apply_type_overrides(
        requirements, original_text="Extract the invoice number and the invoice date."
    )

    assert requirements.fields[0].format == "%d.%m.%Y"
    assert normalize_extracted_data({"invoice_date": "2026-08-10"}, requirements) == {
        "invoice_date": "10.08.2026"
    }


def test_prose_line_still_scopes_a_format_to_its_own_field():
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )
    task = "Extract the order date, the delivery date (DD/MM/YYYY) and the total.\n"

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


@pytest.mark.parametrize(
    "task",
    [
        "Order date, delivery date (DD/MM/YYYY) and the total.\n",
        "- Order date, delivery date (DD/MM/YYYY), total amount\n",
        "1. Order date, delivery date (DD/MM/YYYY)\n",
        "- `order_date`, `delivery_date` (DD/MM/YYYY)\n",
    ],
)
def test_first_field_of_a_line_that_lists_several_does_not_take_a_neighbours_format(task):
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


@pytest.mark.parametrize(
    "task",
    [
        "- **Delivery date** \u2013 when the goods arrive, written DD/MM/YYYY\n",
        "- `delivery_date` (date): when the goods arrive, written DD/MM/YYYY\n",
        "Delivery date = arrival of the goods, written DD/MM/YYYY\n",
    ],
)
def test_field_that_heads_its_own_line_keeps_the_format_after_a_comma(task):
    requirements = _requirements(
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date")
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"


def test_all_dates_format_in_the_task_wins_over_a_format_in_the_description():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order date, printed on the form as DD/MM/YYYY",
        ),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )
    task = """
    Use YYYY-MM-DD for all dates.
    - Order Date
    - Delivery Date (DD.MM.YYYY)
    """

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format == "%Y-%m-%d"
    # The field's own line still wins over the all-dates format.
    assert by_name["delivery_date"].format == "%d.%m.%Y"


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("candidate_name", "Name of the candidate"),
        ("update_notes", "Notes about the change"),
        ("validated_by", "Who checked the entry"),
        ("mandatory", "Whether the item is required"),
        ("metadata", "Free-form key and value pairs"),
        ("database_name", "Name of the system"),
        ("journal", "Name of the publication"),
        ("notes", "Any remarks; keep the candidate's wording"),
        ("journey_id", "Identifier of the trip"),
    ],
)
def test_date_keyword_inside_another_word_does_not_make_a_field_a_date(name, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description=description)
    )

    _apply_type_overrides(requirements, original_text=f"- {name.replace('_', ' ')}")

    assert requirements.fields[0].field_type == "str"
    # A value that happens to parse as a date is left as written.
    assert normalize_extracted_data({name: "10/08/2026"}, requirements) == {name: "10/08/2026"}


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("order_date", "Order date"),
        ("date", "When it happened"),
        ("paivamaara", "Merkinnän päivä"),
        ("toimituspaivamaara", "Toimitus"),
        ("lieferdatum", "Lieferung"),
        ("fecha_de_entrega", "Entrega"),
        ("data_di_consegna", "Consegna"),
        ("teslim_tarihi", "Teslim"),
        ("issued", "Date of issue"),
        ("laadittu", "Asiakirjan päivämäärä"),
    ],
)
def test_date_keyword_as_a_word_still_makes_a_field_a_date(name, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description=description)
    )

    _apply_type_overrides(requirements, original_text="")

    assert requirements.fields[0].field_type == "date"


def test_field_that_only_looks_like_a_date_keeps_its_parsed_type():
    requirements = _requirements(
        FieldSpec(field_name="mandatory", field_type="bool", description="Whether it is required"),
        FieldSpec(field_name="update_count", field_type="int", description="Number of changes"),
    )

    _apply_type_overrides(requirements, original_text="- Mandatory\n- Update count")

    assert [field.field_type for field in requirements.fields] == ["bool", "int"]


@pytest.mark.parametrize(
    ("name", "task_line", "expected_format"),
    [
        ("deadline", "- Deadline (DD/MM/YYYY)", "%d/%m/%Y"),
        ("valid_until", "- Valid until: the last day of validity, as DD.MM.YYYY", "%d.%m.%Y"),
        ("expiry", "- Expiry (DD/MM/YYYY)", "%d/%m/%Y"),
        ("dob", "Use DD.MM.YYYY for all dates.\n- DOB", "%d.%m.%Y"),
    ],
)
def test_field_the_model_typed_as_a_date_gets_its_format_without_a_date_word_in_its_name(
    name, task_line, expected_format
):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="date", description="When it applies")
    )

    _apply_type_overrides(requirements, original_text=task_line)

    field = requirements.fields[0]
    assert field.field_type == "date"
    assert field.format == expected_format


def test_field_the_model_typed_as_a_date_follows_a_keep_as_text_instruction():
    requirements = _requirements(
        FieldSpec(field_name="deadline", field_type="date", description="When it is due")
    )

    _apply_type_overrides(requirements, original_text="- Deadline (preserve format in string)")

    field = requirements.fields[0]
    assert field.field_type == "str"
    assert normalize_extracted_data({"deadline": "12 OCT 25"}, requirements) == {
        "deadline": "12 OCT 25"
    }


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("remarks", "Free text; the data is copied as written"),
        ("key_dates", "Milestones mentioned in the text"),
    ],
)
def test_data_inside_a_description_and_a_plural_do_not_make_a_field_a_date(name, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description=description)
    )

    _apply_type_overrides(requirements, original_text="")

    assert requirements.fields[0].field_type == "str"


@pytest.mark.parametrize(
    ("name", "task_line", "expected_format"),
    [
        # FieldSpec lowercases a camelCase name without splitting it.
        ("dueDate", "- dueDate (DD.MM.YYYY)", "%d.%m.%Y"),
        ("invoiceDate", "- invoiceDate", None),
        ("dateOfBirth", "- dateOfBirth", None),
        ("birthdate", "- Birthdate (DD/MM/YYYY)", "%d/%m/%Y"),
        ("leveringsdato", "- Leveringsdato", None),
        ("fechaEntrega", "- fechaEntrega", None),
    ],
)
def test_run_together_date_name_the_model_typed_as_text_is_still_a_date(
    name, task_line, expected_format
):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description="See the task")
    )

    _apply_type_overrides(requirements, original_text=task_line)

    field = requirements.fields[0]
    assert field.field_type == "date"
    assert field.format == expected_format


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("consegna", "Data di consegna dell'ordine"),
        ("entrega", "Data de entrega do pedido"),
        ("urodzenie", "Data urodzenia"),
        ("levering", "Dato for levering"),
        ("livraison", "Jour de livraison"),
    ],
)
def test_ambiguous_keyword_that_opens_a_description_makes_a_field_a_date(name, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description=description)
    )

    _apply_type_overrides(requirements, original_text="")

    assert requirements.fields[0].field_type == "date"


# Issue #106: the date keyword fallback replaced types the model got right.
@pytest.mark.parametrize(
    ("name", "parsed_type", "description"),
    [
        ("data_quality", "float", "Score from 0 to 1"),
        ("raw_data", "str", "The raw values"),
        ("date_count", "int", "Number of dates"),
        ("date_entries", "list[dict]", "Rows"),
        ("history", "str", "Tarihsel bilgi"),
        ("invoice_number", "str", "Number printed next to the invoice date"),
        # More of the same kinds.
        ("delivery_dates", "list[str]", "Every delivery date"),
        ("is_dated", "bool", "Whether the letter carries a date"),
        ("master_data", "str", "Customer master data"),
        ("tarihce", "str", "Tarihçe"),
        ("order_id", "str", "Id written beside the order date"),
        ("contract_reference", "str", "Reference shown with the signing date"),
    ],
)
def test_the_keyword_fallback_keeps_a_type_the_model_got_right(name, parsed_type, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type=parsed_type, description=description)
    )

    _apply_type_overrides(requirements, original_text=f"- {name.replace('_', ' ')}")

    field = requirements.fields[0]
    assert field.field_type == parsed_type
    assert field.format is None


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("data_di_consegna", "Consegna"),
        ("teslim_tarihi", "Teslim"),
        ("issued", "Date of issue"),
        ("data", "When it was recorded"),
        ("dogum", "Doğum tarihi"),
        ("tarih", "Belge"),
        # A date word in the name counts whatever else the name holds.
        ("date_code", "Code printed on the label"),
    ],
)
def test_the_keyword_fallback_still_finds_these_dates(name, description):
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description=description)
    )

    _apply_type_overrides(requirements, original_text="")

    assert requirements.fields[0].field_type == "date"


@pytest.mark.parametrize("name", ["date_count", "delivery_date_count", "data_quantity"])
def test_a_count_named_after_dates_typed_as_text_gets_the_count_repair(name):
    # Before, the date keyword won and the integer repair for _count names was skipped.
    requirements = _requirements(
        FieldSpec(field_name=name, field_type="str", description="How many dates")
    )

    _apply_type_overrides(requirements, original_text=f"- {name.replace('_', ' ')}")

    assert requirements.fields[0].field_type == "int"


def test_a_model_typed_date_is_a_date_whatever_its_name():
    requirements = _requirements(
        FieldSpec(field_name="invoice_number", field_type="date", description="Issue date")
    )

    _apply_type_overrides(requirements, original_text="- Invoice number (DD.MM.YYYY)")

    assert requirements.fields[0].field_type == "date"
    assert requirements.fields[0].format == "%d.%m.%Y"


# Guards for #96 and #97, whose changes are not in this release: what main does
# today with these tasks, and what a later fix there must keep. They come from the
# reviews of PR #204 and PR #317.
@pytest.mark.parametrize(
    "rule",
    [
        "- Preserve original wording of the notes.",
        "Dates may appear in several formats; keep the amounts unchanged.",
        "Retain the line item descriptions as written.",
        "Keep the original language for free-text fields.",
        "Keep the notes as written and convert dates to ISO.",
        "Do not keep dates as written; use ISO.",
        "Don't preserve the dates.",
        "Keep the notes verbatim, dates in ISO.",
        "Keep the dates in DD.MM.YYYY format.",
        "Keep dates in ISO format.",
        "Never return dates as text.",
        "Leave dates empty if they are missing.",
        "Leave the date fields null when they are missing.",
        "Keep all dates in one consistent format.",
        "Keep dates consistent across records.",
        "There is no need to keep dates as written - convert them to YYYY-MM-DD.",
        "You don't have to keep the dates as written; convert them to DD.MM.YYYY.",
        "Retain dates only if they are explicitly stated.",
        "Keep track of the due dates; they matter.",
        "It is not required to keep dates as written.",
        "You needn't keep the dates unchanged.",
        "Keep dates as written, but convert them to ISO.",
        "Maintain dates in chronological order.",
        "Keep all dates and quote the remarks exactly as written.",
        "Preserve the chronological order of dates.",
    ],
)
def test_a_sentence_that_is_no_rule_to_keep_dates_as_written_leaves_them_dates(rule):
    requirements = _requirements(
        FieldSpec(field_name="invoice_date", field_type="date", description="Invoice date"),
        FieldSpec(field_name="due_date", field_type="date", description="Due date"),
        FieldSpec(field_name="revision_date", field_type="date", description="Revision date"),
    )
    task = f"Extract the invoice date, the due date and the revision date.\n{rule}\n"

    _apply_type_overrides(requirements, original_text=task)

    assert [field.field_type for field in requirements.fields] == ["date", "date", "date"]


@pytest.mark.parametrize(
    ("task", "fields", "expected"),
    [
        # A later sentence on a field's own line stays its own, and a generic
        # "date" field does not take it from inside that line.
        (
            "- Document date: top right corner\n"
            "- Delivery date: when the goods arrive. Write the date as DD.MM.YYYY.",
            [("date", "date"), ("delivery_date", "date")],
            {"date": None, "delivery_date": "%d.%m.%Y"},
        ),
        (
            "- File format: PDF or Word\n"
            "- Delivery date: when the goods arrive. Use the format DD.MM.YYYY.",
            [("format", "str"), ("delivery_date", "date")],
            {"format": None, "delivery_date": "%d.%m.%Y"},
        ),
        (
            "- Due date: payment deadline. Write the due date as DD.MM.YYYY, not like "
            "the invoice date.\n- Invoice date",
            [("due_date", "date"), ("invoice_date", "date")],
            {"due_date": "%d.%m.%Y", "invoice_date": None},
        ),
    ],
)
def test_a_later_sentence_on_a_fields_own_line_stays_with_that_field(task, fields, expected):
    requirements = _requirements(
        *[FieldSpec(field_name=n, field_type=t, description=n) for n, t in fields]
    )

    _apply_type_overrides(requirements, original_text=task)

    assert {f.field_name: f.format for f in requirements.fields} == expected


def test_a_field_on_a_prose_line_does_not_take_its_neighbours_format():
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order date"),
        FieldSpec(
            field_name="delivery_date", field_type="date", description="Delivery date in DD.MM.YYYY"
        ),
    )
    task = "Extract the order date as YYYY-MM-DD and the delivery date as DD.MM.YYYY."

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format == "%Y-%m-%d"
    assert by_name["delivery_date"].format == "%d.%m.%Y"
