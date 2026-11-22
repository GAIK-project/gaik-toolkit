"""DocxParser keeps the text in content controls, tracked insertions and simple fields.

python-docx reads paragraphs, tables, rows, cells and runs only as direct children, so
text inside a content control (``w:sdt``) or a tracked insertion (``w:ins``) was missing
in every output mode. The files are built with python-docx and raw WordprocessingML.
"""

from __future__ import annotations

import pytest

pytest.importorskip("docx")

from docx import Document  # noqa: E402
from docx.oxml import parse_xml  # noqa: E402
from docx.oxml.ns import nsdecls  # noqa: E402
from gaik.software_components.parsers.docx_parser import DocxParser  # noqa: E402

W = nsdecls("w")


def _run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def _paragraph(*inner: str) -> str:
    return f"<w:p {W}>{''.join(inner)}</w:p>"


def _sdt(content: str, *, placeholder: bool = False, ns: bool = False) -> str:
    properties = "<w:sdtPr><w:alias w:val='Field'/>"
    properties += "<w:showingPlcHdr/></w:sdtPr>" if placeholder else "</w:sdtPr>"
    return f"<w:sdt {W if ns else ''}>{properties}<w:sdtContent>{content}</w:sdtContent></w:sdt>"


def _form(path):
    """A contract-like form: every value is in a content control or a tracked change."""
    document = Document()
    document.add_paragraph("Order form", style="Heading 1")
    body = document.element.body
    anchor = document.add_paragraph("Intro")._p

    elements = [
        # A block content control around a paragraph.
        _sdt(_paragraph(_run("Customer: Acme Oy")), ns=True),
        # An inline content control inside a paragraph.
        _paragraph(_run("Price: "), _sdt(_run("1 490 EUR")), _run(" incl. VAT")),
        # A tracked insertion next to a tracked deletion.
        _paragraph(
            _run("Signed by "),
            "<w:ins w:id='1' w:author='A' w:date='2026-01-01T00:00:00Z'>"
            + _run("Jane Doe")
            + "</w:ins>",
            "<w:del w:id='2' w:author='A' w:date='2026-01-01T00:00:00Z'>"
            "<w:r><w:delText>John Roe</w:delText></w:r></w:del>",
        ),
        # A merge field whose result Word shows.
        _paragraph(
            _run("Ref: "),
            "<w:fldSimple w:instr=' MERGEFIELD Ref '>" + _run("PO-7") + "</w:fldSimple>",
        ),
        # A content control showing its placeholder is an empty field.
        _sdt(_paragraph(_run("Click or tap here to enter text.")), placeholder=True, ns=True),
        # Content controls nested in one another.
        _sdt(_sdt(_paragraph(_run("Nested value")), ns=True), ns=True),
    ]
    for xml in elements:
        element = parse_xml(xml)
        anchor.addnext(element)
        anchor = element

    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Item"
    table.rows[0].cells[1].text = "Qty"
    # A repeating-section row inside a content control, and a cell inside one.
    row = parse_xml(
        _sdt(
            "<w:tr>"
            f"<w:tc><w:p>{_run('Widget')}</w:p></w:tc>"
            f"<w:tc>{_sdt('<w:p>' + _run('12') + '</w:p>')}</w:tc>"
            "</w:tr>",
            ns=True,
        )
    )
    table._tbl.append(row)
    document.add_paragraph("Outro")
    assert body.xpath(".//w:sdt")
    document.save(path)
    return path


EXPECTED_ORDER = [
    "Intro",
    "Customer: Acme Oy",
    "Price: 1 490 EUR incl. VAT",
    "Signed by Jane Doe",
    "Ref: PO-7",
    "Nested value",
    "Outro",
]


def _in_order(text: str, parts: list[str]) -> bool:
    at = -1
    for part in parts:
        found = text.find(part, at + 1)
        if found <= at:
            return False
        at = found
    return True


@pytest.mark.parametrize(
    "options",
    [{}, {"keep_structure": True}, {"use_markdown": False}],
    ids=["simple", "keep_structure", "structured"],
)
def test_content_controls_and_tracked_insertions_are_kept_in_order(tmp_path, options):
    path = _form(tmp_path / "form.docx")

    text = DocxParser().parse_docx(str(path), **options)

    assert _in_order(text, EXPECTED_ORDER), text
    assert "Widget" in text and "12" in text
    # Deleted text and an unfilled field's placeholder are not content.
    assert "John Roe" not in text
    assert "Click or tap" not in text


def test_keep_structure_puts_a_content_control_row_in_its_table(tmp_path):
    path = _form(tmp_path / "form.docx")

    text = DocxParser().parse_docx(str(path), keep_structure=True)

    assert "| Item | Qty |\n| --- | --- |\n| Widget | 12 |" in text
    assert text.startswith("# Order form\n\nIntro\n\nCustomer: Acme Oy")
    assert text.endswith("| Widget | 12 |\n\nOutro")
