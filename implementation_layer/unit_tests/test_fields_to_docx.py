"""Tests for the fields-to-Word component: every file is read back with python-docx."""

from __future__ import annotations

import io
import logging
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

docx = pytest.importorskip("docx")

from docx.oxml.ns import qn  # noqa: E402
from gaik.software_components.fields_to_docx import (  # noqa: E402
    DocxResult,
    FieldRow,
    FieldsToDocx,
    to_rows,
)

NOTE = (
    "Service visit at Hall 3 on 12 November 2026.\n"
    "The technician replaced the inlet valve of pump P-204.\n\n"
    "The pump was tested for 30 minutes without leaks."
)


def _open(result: DocxResult) -> Any:
    return docx.Document(io.BytesIO(result.content))


def _table(result: DocxResult) -> list[list[str]]:
    """The cell texts of the field table, header row first."""
    (table,) = _open(result).tables
    return [[cell.text for cell in row.cells] for row in table.rows]


def _value(value: Any, writer: FieldsToDocx | None = None) -> str:
    """What one value looks like in its table cell."""
    return _table((writer or FieldsToDocx()).write([("Field", value)]))[1][1]


# shapes of ``fields`` ---------------------------------------------------------------------


def test_label_value_tuples_give_a_table_in_order() -> None:
    result = FieldsToDocx().write(
        [("Site", "Hall 3"), ("Work done", "Replaced the inlet valve"), ("Follow-up", None)]
    )

    assert _table(result) == [
        ["Field", "Value"],
        ["Site", "Hall 3"],
        ["Work done", "Replaced the inlet valve"],
        ["Follow-up", "—"],
    ]
    assert (result.rows, result.filled, result.path) == (3, 2, None)
    assert result.content[:2] == b"PK"


def test_a_record_uses_labels_and_makes_other_names_readable() -> None:
    record = {"site": "Hall 3", "work_done": "Valve replaced", "PO_number": "PO-7741"}

    result = FieldsToDocx().write(record, labels={"site": "Kohde", "unused": "Not in the record"})

    assert _table(result)[1:] == [
        ["Kohde", "Hall 3"],
        ["Work done", "Valve replaced"],
        ["PO number", "PO-7741"],
    ]


def test_rows_as_dicts_and_as_objects_with_attributes() -> None:
    @dataclass
    class Extracted:  # the shape of gaik.operations.ExtractedField
        name: str
        label: str | None
        value: Any
        evidence: str | None = None
        verdict: str | None = None

    rows = to_rows(
        [
            {"label": "Site", "name": "site", "value": "Hall 3"},
            {"name": "work_done", "value": "Valve replaced", "evidence": "replaced the valve"},
            {"name": "visit_date", "value": date(2026, 11, 12)},
            Extracted("pump", "Pump", "P-204", "pump P-204", "verified"),
            Extracted("minutes", None, 30),
            FieldRow("Leaks", False),
        ],
        labels={"site": "ignored: the row has a label", "work_done": "Work"},
    )

    assert rows == [
        FieldRow("Site", "Hall 3"),
        FieldRow("Work", "Valve replaced", "replaced the valve"),
        FieldRow("Visit date", date(2026, 11, 12)),
        FieldRow("Pump", "P-204", "pump P-204", "verified"),
        FieldRow("Minutes", 30),
        FieldRow("Leaks", False),
    ]


def test_a_list_holding_one_record_is_that_record() -> None:
    assert to_rows([{"site": "Hall 3", "minutes": 30}]) == [
        FieldRow("Site", "Hall 3"),
        FieldRow("Minutes", 30),
    ]
    assert _table(FieldsToDocx().write([{"site": "Hall 3"}]))[1:] == [["Site", "Hall 3"]]


def test_several_records_raise() -> None:
    with pytest.raises(ValueError, match="one record; call it once per record"):
        FieldsToDocx().write([{"site": "Hall 3"}, {"site": "Hall 4"}])


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ([], "empty"),
        ({}, "empty"),
        ([{}], "empty"),
        (None, "not NoneType"),
        ("Site: Hall 3", "not str"),
        (b"Site", "not bytes"),
        (42, "not int"),
        ((item for item in [("Site", "Hall 3")]), "not generator"),
        (["Site", "Hall 3"], "row 1 is bare text"),
        ([("Site", "Hall 3", "extra")], "row 1 has 3 items"),
        ([("Site", "Hall 3"), 7], "row 2 is a int"),
        ([{"label": "Site", "value": "Hall 3"}, {"value": "Hall 4"}], "row 2 has no label"),
        ([{"label": " ", "value": "Hall 3"}], "row 1 has no label"),
        ([{"label": "Site", "value": "Hall 3"}, {"site": "Hall 4"}], "row 2 has no value"),
        ([(7, "Hall 3")], "label of row 1 must be text"),
        ({7: "Hall 3"}, "field names"),
    ],
)
def test_an_unknown_shape_raises_and_names_the_reason(fields: Any, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        FieldsToDocx().write(fields)


@pytest.mark.parametrize(
    "wrapped", [False, True], ids=["the record", "as the extractor returns it"]
)
def test_a_record_with_a_field_called_value_is_a_record(wrapped: bool) -> None:
    record = {"value": 5, "unit": "kg"}

    result = FieldsToDocx().write([record] if wrapped else record)

    assert _table(result)[1:] == [["Value", "5"], ["Unit", "kg"]]


def test_error_messages_do_not_repeat_the_input() -> None:
    with pytest.raises(ValueError) as error:
        FieldsToDocx().write(["PRIVATE-VALUE-NOT-FOR-MESSAGES"])

    assert "PRIVATE" not in str(error.value)


# values -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, "—"),
        ("", "—"),
        ("  \n ", "—"),
        ([], "—"),
        ({}, "—"),
        ([None, ""], "—"),
        (math.nan, "—"),
        (math.inf, "—"),
        (Decimal("NaN"), "—"),
        (True, "Yes"),
        (False, "No"),
        (0, "0"),
        (42, "42"),
        (3.0, "3"),
        (2.5, "2.5"),
        (-0.25, "-0.25"),
        (Decimal("1234.50"), "1234.50"),
        (Decimal("1E+2"), "100"),
        (date(2026, 11, 12), "2026-11-12"),
        (datetime(2026, 11, 12, 10, 3, 44), "2026-11-12T10:03:44"),
        (["valve", "gasket", 2], "valve\ngasket\n2"),
        (("a", None, "b"), "a\nb"),
        (
            [{"part": "valve", "qty": 1}, {"part": "gasket", "qty": None}],
            "part: valve; qty: 1\npart: gasket; qty: —",
        ),
        ({"name": "Pump", "tags": ["a", "b"], "ok": True}, "name: Pump\ntags: a, b\nok: Yes"),
        ("  two\r\nlines\rhere ", "two\nlines\nhere"),
    ],
)
def test_value_rendering(value: Any, text: str) -> None:
    assert _value(value) == text


def test_empty_values_are_not_counted_as_filled() -> None:
    result = FieldsToDocx().write(
        [("a", None), ("b", ""), ("c", []), ("d", {}), ("e", math.nan), ("f", 0), ("g", False)]
    )

    assert (result.rows, result.filled) == (7, 2)


def test_the_texts_of_the_component_can_be_changed() -> None:
    writer = FieldsToDocx(
        headers=("Kenttä", "Arvo", "Lähde"), empty_text="-", true_text="Kyllä", false_text="Ei"
    )

    result = writer.write([FieldRow("Valmis", True, "työ on valmis"), ("Viive", False), ("x", "")])

    assert _table(result) == [
        ["Kenttä", "Arvo", "Lähde"],
        ["Valmis", "Kyllä", '"työ on valmis"'],
        ["Viive", "Ei", ""],
        ["x", "-", ""],
    ]


def test_control_characters_do_not_break_the_save() -> None:
    dirty = "valve\x00 re\x07placed\x0b\x0c\x1f\x7f \ud800ok\ufffe\uffff"

    result = FieldsToDocx().write(
        [FieldRow("La\x01bel\x00", dirty, evidence=f"quote\x08 {dirty}", verdict="che\x02ck")],
        title="Ti\x00tle\x1b",
        metadata={"Da\x03te": "2026\x00-11-12"},
        appendix=f"first\x00 paragraph\n\nsecond\x0c paragraph {dirty}",
        footer="foo\x00ter",
    )
    document = _open(result)

    assert _table(result)[1] == [
        "Label",
        "valve replaced ok",
        '"quote valve replaced ok" (check)',
    ]
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert texts == [
        "Title",
        "Date: 2026-11-12",
        "Appendix: source text",
        "first paragraph",
        "second paragraph valve replaced ok",
    ]
    assert document.sections[0].footer.paragraphs[0].text == "footer"
    assert document.core_properties.title == "Title"


def test_very_long_values_are_kept_whole() -> None:
    long_value = "pitkä arvo " * 5000  # 55 000 characters
    long_word = "x" * 20000

    result = FieldsToDocx().write(
        [("Long", long_value), ("Unbroken", long_word)], appendix=long_value, title="T" * 600
    )
    document = _open(result)

    assert _table(result)[1][1] == long_value.strip()
    assert _table(result)[2][1] == long_word
    assert document.paragraphs[-1].text == long_value.strip()
    # The heading keeps the whole title; the document property has a 255-character limit.
    assert document.paragraphs[0].text == "T" * 600
    assert document.core_properties.title == "T" * 255


def test_non_ascii_text_survives() -> None:
    record = {
        "sää_ja_lämpötila": "Pilvistä, −3 °C, räntää",
        "työ": "Öljynvaihto ja suodattimet",
        "备注": "阀门已更换 ✔ 🙂",
        "arabic": "تم استبدال الصمام",
    }

    result = FieldsToDocx().write(record, title="Työmaapäiväkirja – Ääkköset", appendix="Åbo\n\nЖ")

    assert _table(result)[1:] == [
        ["Sää ja lämpötila", "Pilvistä, −3 °C, räntää"],
        ["Työ", "Öljynvaihto ja suodattimet"],
        ["备注", "阀门已更换 ✔ 🙂"],
        ["Arabic", "تم استبدال الصمام"],
    ]
    document = _open(result)
    assert document.paragraphs[0].text == "Työmaapäiväkirja – Ääkköset"
    assert [paragraph.text for paragraph in document.paragraphs[-2:]] == ["Åbo", "Ж"]


def test_markup_characters_are_text_not_markup() -> None:
    label = '<w:b>Total & "tax"</w:b> ]]> &amp; <!-- x -->'
    value = "<script>alert('1')</script> & <w:br/> {{ jinja }} ${shell}"

    result = FieldsToDocx().write(
        [FieldRow(label, value, evidence="a < b > c & d")],
        title="<h1>Report & more</h1>",
        metadata=[("<Date>", "1 < 2 & 3 > 2")],
        appendix="<p>plain</p>",
        footer="<footer/>",
    )
    document = _open(result)

    assert _table(result)[1] == [label, value, '"a < b > c & d"']
    assert [paragraph.text for paragraph in document.paragraphs] == [
        "<h1>Report & more</h1>",
        "<Date>: 1 < 2 & 3 > 2",
        "Appendix: source text",
        "<p>plain</p>",
    ]
    assert document.sections[0].footer.paragraphs[0].text == "<footer/>"
    # Nothing of it became an element: the table still has one bold run in the label cell.
    cell = document.tables[0].rows[1].cells[0]
    assert [run.bold for run in cell.paragraphs[0].runs] == [True]


# evidence ---------------------------------------------------------------------------------


def test_the_evidence_column_appears_only_when_a_row_has_evidence() -> None:
    plain = [("Site", "Hall 3"), ("Pump", "P-204")]
    cited = [FieldRow("Site", "Hall 3", "visit at Hall 3", "verified"), FieldRow("Pump", "P-204")]
    writer = FieldsToDocx()

    assert _table(writer.write(plain))[0] == ["Field", "Value"]
    assert _table(writer.write(plain, evidence=True)) == [
        ["Field", "Value", "Evidence"],
        ["Site", "Hall 3", ""],
        ["Pump", "P-204", ""],
    ]
    assert _table(writer.write(cited)) == [
        ["Field", "Value", "Evidence"],
        ["Site", "Hall 3", '"visit at Hall 3" (verified)'],
        ["Pump", "P-204", ""],
    ]
    assert _table(writer.write(cited, evidence=False)) == [
        ["Field", "Value"],
        ["Site", "Hall 3"],
        ["Pump", "P-204"],
    ]


def test_a_verdict_alone_does_not_open_the_column_but_shows_in_it() -> None:
    rows = [FieldRow("Site", "Hall 3", verdict="unchecked")]

    assert _table(FieldsToDocx().write(rows))[0] == ["Field", "Value"]
    assert _table(FieldsToDocx().write(rows, evidence=True))[1] == ["Site", "Hall 3", "(unchecked)"]


def test_a_trace_from_source_tracing_fills_quote_and_verdict() -> None:
    from gaik.software_components.source_tracing import SOURCES_FIELD, SourceTracing

    def cite(name: str, quote: str) -> dict:
        return {"field": name, "document": 1, "page": 1, "quote": quote}

    result = {
        "site": "Hall 3",
        "pump": "P-999",
        "test_minutes": 30,
        "leaks": None,
        "parts": [{"name": "inlet valve"}],
        SOURCES_FIELD: {
            "items": [
                cite("site", "Service visit at Hall 3"),
                cite("pump", "the outlet valve of pump P-999"),
                cite("parts[0].name", "replaced the inlet valve"),
                cite("site", "a second citation of the same field"),
            ]
        },
    }
    clean, report = SourceTracing().check_text(result, [NOTE])
    writer = FieldsToDocx()

    expected = [
        ["Field", "Value", "Evidence"],
        ["Site", "Hall 3", '"Service visit at Hall 3" (verified)'],
        ["Pump", "P-999", '"the outlet valve of pump P-999" (check)'],
        ["Test minutes", "30", ""],
        ["Leaks", "—", ""],
        # A citation of a path into the list is not the evidence of the list.
        ["Parts", "name: inlet valve", ""],
    ]
    assert _table(writer.write(clean, trace=report)) == expected
    assert _table(writer.write([clean], trace=report.to_dict())) == expected
    assert _table(writer.write(clean, trace=report, evidence=False))[0] == ["Field", "Value"]
    assert report.items[0].quote in NOTE


def test_a_trace_is_refused_for_rows_and_for_an_unknown_shape() -> None:
    with pytest.raises(ValueError, match="trace goes with a record"):
        FieldsToDocx().write([("Site", "Hall 3")], trace={"sources": []})
    with pytest.raises(ValueError, match="TraceReport"):
        FieldsToDocx().write({"site": "Hall 3"}, trace=["site"])


# the rest of the document -------------------------------------------------------------------


def test_a_plain_document_has_a_title_a_table_and_nothing_else() -> None:
    document = _open(FieldsToDocx().write([("Site", "Hall 3")]))

    assert [(p.style.name, p.text) for p in document.paragraphs] == [("Heading 1", "Report")]
    assert len(document.tables) == 1 and document.tables[0].style.name == "Table Grid"
    assert document.sections[0].footer.is_linked_to_previous  # no footer of its own
    assert document.core_properties.title == "Report"
    assert document.core_properties.author == ""
    assert document.core_properties.comments == ""
    assert document.core_properties.created.year >= 2026


def test_metadata_line_from_a_mapping_and_from_pairs() -> None:
    writer = FieldsToDocx()
    rows = [("Site", "Hall 3")]

    mapped = _open(
        writer.write(rows, metadata={"Date": date(2026, 11, 12), "Urgent": True, "By": ""})
    )
    paired = _open(writer.write(rows, metadata=[("Date", "12.11.2026"), ("Channel", "Call")]))

    line = mapped.paragraphs[1]
    assert line.text == "Date: 2026-11-12   ·   Urgent: Yes   ·   By: —"
    assert [run.text for run in line.runs if run.bold] == ["Date: ", "Urgent: ", "By: "]
    assert paired.paragraphs[1].text == "Date: 12.11.2026   ·   Channel: Call"
    with pytest.raises(ValueError, match="metadata"):
        writer.write(rows, metadata="Date: today")
    with pytest.raises(ValueError, match="metadata item 2"):
        writer.write(rows, metadata=[("Date", "today"), "Channel"])


def test_appendix_from_a_string_and_from_a_list() -> None:
    writer = FieldsToDocx()
    rows = [("Site", "Hall 3")]

    from_text = _open(writer.write(rows, appendix=NOTE, appendix_title="Appendix: transcript"))
    from_list = _open(writer.write(rows, appendix=["Agent: Hello.", "", "Caller: A leak.\nNow."]))
    without = _open(writer.write(rows, appendix="  \n\n "))

    assert [(p.style.name, p.text) for p in from_text.paragraphs[1:]] == [
        ("Heading 2", "Appendix: transcript"),
        (
            "Normal",
            "Service visit at Hall 3 on 12 November 2026.\nThe technician replaced the "
            "inlet valve of pump P-204.",
        ),
        ("Normal", "The pump was tested for 30 minutes without leaks."),
    ]
    assert [p.text for p in from_list.paragraphs[1:]] == [
        "Appendix: source text",
        "Agent: Hello.",
        "Caller: A leak.\nNow.",
    ]
    assert len(without.paragraphs) == 1
    with pytest.raises(ValueError, match="appendix"):
        writer.write(rows, appendix=["text", 7])


def test_footer_only_when_given() -> None:
    document = _open(FieldsToDocx().write([("Site", "Hall 3")], footer="Synthetic test content"))
    paragraph = document.sections[0].footer.paragraphs[0]

    assert paragraph.text == "Synthetic test content"
    assert paragraph.alignment == docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
    assert paragraph.runs[0].font.size.pt == 8


def test_layout_label_column_bold_header_repeats_and_one_font() -> None:
    writer = FieldsToDocx(font_name="Arial", font_size=10, label_width_cm=4)
    document = _open(writer.write([FieldRow("Site", "Hall 3", "at Hall 3")], appendix="Text"))
    table = document.tables[0]
    header, row = table.rows

    assert [cell.paragraphs[0].runs[0].bold for cell in header.cells] == [True, True, True]
    assert [cell.paragraphs[0].runs[0].bold for cell in row.cells] == [True, None, None]
    assert header._tr.trPr.find(qn("w:tblHeader")) is not None
    assert round(row.cells[0].width.cm, 1) == 4.0
    section = document.sections[0]
    usable = section.page_width - section.left_margin - section.right_margin
    assert abs(sum(cell.width for cell in row.cells) - usable) < 2000  # EMU; a twip is 635
    assert document.styles["Normal"].font.name == "Arial"
    assert document.styles["Normal"].font.size.pt == 10
    for name in ("Heading 1", "Heading 2"):
        fonts = document.styles[name].element.rPr.rFonts
        assert document.styles[name].font.name == "Arial"
        assert not [key for key in fonts.attrib if key.endswith("Theme") or "theme" in key]


def test_the_page_is_a4() -> None:
    section = _open(FieldsToDocx().write([("Site", "Hall 3")])).sections[0]
    assert (round(section.page_width.mm), round(section.page_height.mm)) == (210, 297)


def test_the_label_column_is_at_most_half_of_the_text_width() -> None:
    document = _open(FieldsToDocx(label_width_cm=40).write([("Site", "Hall 3")]))
    first, second = document.tables[0].rows[1].cells

    assert abs(first.width - second.width) < 2000


def test_bad_settings_raise() -> None:
    for settings in (
        {"headers": ("Field", "Value")},
        {"headers": "abc"},
        {"font_size": 0},
        {"label_width_cm": -1},
        {"font_name": " "},
        # These passed the constructor and failed in write(), with python-docx's own error.
        {"font_size": float("nan")},
        {"font_size": float("inf")},
        {"label_width_cm": float("inf")},
        {"label_width_cm": float("nan")},
        {"font_name": "Cali\x00bri"},
        {"font_name": "Arial\x1b[0m"},
    ):
        with pytest.raises(ValueError):
            FieldsToDocx(**settings)


# output -------------------------------------------------------------------------------------


def test_output_path_writes_the_same_bytes_and_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "reports" / "2026" / "service report.DOCX"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"an older file")

    result = FieldsToDocx().write([("Site", "Hall 3")], target, title="Service report")
    nested = FieldsToDocx().write([("Site", "Hall 3")], str(tmp_path / "new" / "deep" / "r.docx"))

    assert result.path == target and target.read_bytes() == result.content
    assert docx.Document(str(target)).tables[0].rows[1].cells[1].text == "Hall 3"
    assert nested.path == tmp_path / "new" / "deep" / "r.docx" and nested.path.is_file()


@pytest.mark.parametrize("name", ["report.doc", "report.pdf", "report", "report.docx.txt"])
def test_a_suffix_other_than_docx_raises_and_writes_nothing(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match=r"\.docx"):
        FieldsToDocx().write([("Site", "Hall 3")], tmp_path / name)
    with pytest.raises(ValueError, match=r"\.docx"):
        FieldsToDocx().write([("Site", "Hall 3")]).save(tmp_path / name)

    assert list(tmp_path.iterdir()) == []


def test_bad_fields_write_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FieldsToDocx().write([], tmp_path / "report.docx")

    assert list(tmp_path.iterdir()) == []


def test_docx_result_save(tmp_path: Path) -> None:
    result = FieldsToDocx().write({"site": "Hall 3"})

    saved = result.save(tmp_path / "copies" / "copy.docx")

    assert saved == tmp_path / "copies" / "copy.docx"
    assert saved.read_bytes() == result.content
    assert result.path is None  # save does not change the result
    assert "content" not in repr(result) and "rows=1" in repr(result)


def test_the_log_has_counts_not_content(caplog: pytest.LogCaptureFixture) -> None:
    private = "TEXT-THAT-MUST-NOT-BE-LOGGED"

    with caplog.at_level(logging.DEBUG):
        FieldsToDocx().write(
            [FieldRow(private, private, evidence=private, verdict=private)],
            title=private,
            metadata={private: private},
            appendix=private,
            footer=private,
        )

    assert private not in caplog.text
    assert "1 rows, 1 filled" in caplog.text


def test_a_missing_python_docx_names_the_extra_to_install() -> None:
    code = """
import sys

sys.modules["docx"] = None
try:
    import gaik.software_components.fields_to_docx
except ImportError as exc:
    print(exc)
"""

    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert done.stdout.strip() == (
        "FieldsToDocx needs python-docx: pip install 'gaik[fields-to-docx]'"
    )
