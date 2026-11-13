"""Extracted fields as a Word file.

``FieldsToDocx.write`` builds one tidy, neutral document: a title, an optional line of
facts, a table of labels and values, an optional evidence column and an optional appendix
with the source text. It uses python-docx only: no model call, no template file, no Pandoc.
"""

from __future__ import annotations

import io
import logging
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Emu, Mm, Pt, RGBColor
except ImportError as exc:
    raise ImportError("FieldsToDocx needs python-docx: pip install 'gaik[fields-to-docx]'") from exc

logger = logging.getLogger(__name__)

# Characters an XML document cannot hold (python-docx raises on them), and DEL.
_UNSAFE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff\ufffe\uffff]")
_BLANK_LINES = re.compile(r"\n[ \t]*\n")
_GREY = RGBColor(0x66, 0x66, 0x66)
_SEPARATOR = "   ·   "
_CORE_TEXT_LIMIT = 255  # python-docx refuses a longer document property
_ROW_SHAPES = (
    "a FieldRow, a (label, value) pair, or a mapping or object with a value and a label or name"
)


@dataclass(frozen=True)
class FieldRow:
    """One row of the field table.

    Attributes:
        label: The text of the first column.
        value: The value; see the README for how each type is written.
        evidence: A verbatim quote from the source that shows the value.
        verdict: A short status word for the evidence, e.g. SourceTracing's verdict.
    """

    label: str
    value: Any = None
    evidence: str | None = None
    verdict: str | None = None


@dataclass
class DocxResult:
    """The Word file ``FieldsToDocx.write`` built.

    Attributes:
        content: The .docx file as bytes.
        path: Where it was written; None when ``write`` got no ``output_path``.
        rows: Number of field rows in the table.
        filled: How many of them have a value.
    """

    content: bytes = field(repr=False)
    path: Path | None
    rows: int
    filled: int

    def save(self, path: str | Path) -> Path:
        """Write the file to ``path`` (a .docx name; parents are created) and return the path."""
        target = _docx_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.content)
        return target


@dataclass(frozen=True)
class _Cells:
    """The texts of one table row, ready to write."""

    label: str
    value: str
    evidence: str  # the quote in quotation marks and the verdict in brackets
    filled: bool  # the row has a value
    quoted: bool  # the row has a quote


def to_rows(
    fields: Any, *, labels: Mapping[str, str] | None = None, trace: Any = None
) -> list[FieldRow]:
    """The rows of the field table for what the caller passed.

    Args:
        fields: One record (a mapping of field name to value), a sequence of rows, or a
            sequence holding exactly one record. A row is a :class:`FieldRow`, a
            ``(label, value)`` tuple, a mapping with ``value`` and ``label`` or ``name``,
            or an object with those attributes.
        labels: Display labels by field name. A name without one is made readable
            (``work_done`` becomes ``Work done``).
        trace: For a record only: a SourceTracing ``TraceReport`` or its ``to_dict()``.
            The first citation of each top-level field gives the row's evidence and verdict.

    Raises:
        ValueError: The input is empty or is none of the shapes above.
    """
    if isinstance(fields, Mapping):
        return _record_rows(fields, labels, trace)
    if isinstance(fields, str | bytes | bytearray) or not isinstance(fields, Sequence):
        raise ValueError(
            f"fields must be a mapping or a sequence of rows, not {type(fields).__name__}"
        )
    items = list(fields)
    if not items:
        raise ValueError("fields is empty: nothing to write")
    records = sum(1 for item in items if isinstance(item, Mapping) and not _is_row(item))
    if records == len(items):
        if records > 1:
            raise ValueError("write() takes one record; call it once per record")
        return _record_rows(items[0], labels, trace)
    if trace is not None:
        raise ValueError("trace goes with a record; a row carries its own evidence and verdict")
    return [_row(item, number, labels) for number, item in enumerate(items, start=1)]


class FieldsToDocx:
    """Write extracted fields to a Word file.

    Args:
        headers: Header texts of the label, value and evidence columns.
        empty_text: What a field without a value shows.
        true_text: What ``True`` shows.
        false_text: What ``False`` shows.
        font_name: Font of the document, headings included.
        font_size: Size of the body text in points.
        label_width_cm: Width of the label column (at most half of the text width).

    Example:
        >>> from gaik.software_components.fields_to_docx import FieldsToDocx
        >>> result = FieldsToDocx().write(
        ...     [("Site", "Hall 3"), ("Work done", "Replaced the valve")],
        ...     "report.docx",
        ...     title="Service report",
        ... )
        >>> result.rows, result.filled
        (2, 2)
    """

    def __init__(
        self,
        *,
        headers: tuple[str, str, str] = ("Field", "Value", "Evidence"),
        empty_text: str = "—",
        true_text: str = "Yes",
        false_text: str = "No",
        font_name: str = "Calibri",
        font_size: float = 11.0,
        label_width_cm: float = 5.5,
    ) -> None:
        if (
            isinstance(headers, str)
            or len(headers) != 3
            or not all(isinstance(header, str) for header in headers)
        ):
            raise ValueError("headers must be three texts: label, value and evidence column")
        if not isinstance(font_name, str) or not font_name.strip():
            raise ValueError("font_name must not be blank")
        if _one_line(font_name) != " ".join(font_name.split()):
            raise ValueError("font_name must not hold control characters")
        if not all(math.isfinite(size) and size > 0 for size in (font_size, label_width_cm)):
            raise ValueError("font_size and label_width_cm must be numbers above zero")
        self.headers = tuple(_one_line(header) for header in headers)
        self.empty_text = _one_line(empty_text)
        self.true_text = _one_line(true_text)
        self.false_text = _one_line(false_text)
        self.font_name = _one_line(font_name)
        self.font_size = float(font_size)
        self.label_width_cm = float(label_width_cm)

    def write(
        self,
        fields: Any,
        output_path: str | Path | None = None,
        *,
        title: str = "Report",
        metadata: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
        labels: Mapping[str, str] | None = None,
        trace: Any = None,
        evidence: bool | None = None,
        appendix: str | Sequence[str] | None = None,
        appendix_title: str = "Appendix: source text",
        footer: str | None = None,
    ) -> DocxResult:
        """Build the Word file, and write it when ``output_path`` is given.

        Args:
            fields: One record, or a sequence of rows; see :func:`to_rows`.
            output_path: A ``.docx`` path. Parent folders are created and an existing
                file is overwritten. None returns the bytes only.
            title: The heading and the title property of the document.
            metadata: Facts for the line under the title, e.g. ``{"Date": "2026-11-12"}``
                or a sequence of ``(label, value)`` tuples.
            labels: Display labels by field name.
            trace: For a record: a SourceTracing ``TraceReport`` or its ``to_dict()``.
            evidence: True shows the evidence column, False hides it, None shows it when
                at least one row has evidence.
            appendix: Source text or transcript after the table. A string is split into
                paragraphs on blank lines; a sequence gives one paragraph per item.
            appendix_title: Heading of the appendix.
            footer: Text of the page footer. No footer when None.

        Returns:
            A :class:`DocxResult` with the bytes, the path, and the row counts.

        Raises:
            ValueError: ``fields`` is empty or has an unknown shape, ``output_path`` does
                not end in ``.docx``, or another argument is not what it should be.
        """
        target = None if output_path is None else _docx_path(output_path)
        if not isinstance(title, str) or not isinstance(appendix_title, str):
            raise ValueError("title and appendix_title must be text")
        rows = [self._render(row) for row in to_rows(fields, labels=labels, trace=trace)]
        facts = self._facts(metadata)
        paragraphs = _appendix_paragraphs(appendix)
        if footer is not None and not isinstance(footer, str):
            raise ValueError("footer must be text")
        footer_text = _one_line(footer or "")
        show_evidence = any(row.quoted for row in rows) if evidence is None else bool(evidence)
        heading = _one_line(title) or "Report"

        document = Document()
        # python-docx's template page is Letter.
        page = document.sections[0]
        page.page_width, page.page_height = Mm(210), Mm(297)
        self._set_fonts(document)
        document.add_heading(heading, level=1)
        if facts:
            line = document.add_paragraph()
            for index, (label, value) in enumerate(facts):
                if index:
                    line.add_run(_SEPARATOR).font.color.rgb = _GREY
                line.add_run(f"{label}: ").bold = True
                line.add_run(value)
        self._add_table(document, rows, show_evidence)
        if paragraphs:
            document.add_heading(_one_line(appendix_title) or "Appendix", level=2)
            for text in paragraphs:
                document.add_paragraph().add_run(text)
        if footer_text:
            paragraph = document.sections[0].footer.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = paragraph.add_run(footer_text)
            run.font.size = Pt(8)
            run.font.color.rgb = _GREY
        _set_properties(document, heading)

        buffer = io.BytesIO()
        document.save(buffer)
        content = buffer.getvalue()
        filled = sum(1 for row in rows if row.filled)
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        logger.info(
            "Word file built: %d rows, %d filled, %d appendix paragraphs, %d bytes",
            len(rows),
            filled,
            len(paragraphs),
            len(content),
        )
        return DocxResult(content=content, path=target, rows=len(rows), filled=filled)

    # values -----------------------------------------------------------------------------

    def _render(self, row: FieldRow) -> _Cells:
        """The texts of one table row."""
        value = self._text(row.value)
        quote = _clean(row.evidence) if row.evidence else ""
        verdict = _one_line(row.verdict) if row.verdict else ""
        parts = [f'"{quote}"' if quote else "", f"({verdict})" if verdict else ""]
        return _Cells(
            label=_one_line(row.label),
            value=value or self.empty_text,
            evidence=" ".join(part for part in parts if part),
            filled=bool(value),
            quoted=bool(quote),
        )

    def _text(self, value: Any) -> str:
        """The value as cell text; an empty string when there is no value."""
        if isinstance(value, Mapping):
            lines = [
                f"{_one_line(str(key))}: {self._inline(inner) or self.empty_text}"
                for key, inner in value.items()
            ]
            return "\n".join(lines)
        if isinstance(value, list | tuple | set | frozenset):
            lines = [self._inline(item) for item in value]
            return "\n".join(line for line in lines if line)
        return self._scalar(value)

    def _inline(self, value: Any) -> str:
        """The value on one line, for an item of a list or a value inside a dict."""
        if isinstance(value, Mapping):
            pairs = [
                f"{_one_line(str(key))}: {self._inline(inner) or self.empty_text}"
                for key, inner in value.items()
            ]
            return "; ".join(pairs)
        if isinstance(value, list | tuple | set | frozenset):
            return ", ".join(text for text in (self._inline(item) for item in value) if text)
        return _one_line(self._scalar(value))

    def _scalar(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return self.true_text if value else self.false_text
        if isinstance(value, str):
            return _clean(value)
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if not math.isfinite(value):
                return ""
            return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
        if isinstance(value, Decimal):
            return format(value, "f") if value.is_finite() else ""
        if isinstance(value, date | time):  # datetime is a date
            return value.isoformat()
        return _clean(str(value))

    def _facts(self, metadata: Any) -> list[tuple[str, str]]:
        """The metadata as (label, one-line value) pairs."""
        if metadata is None:
            return []
        if isinstance(metadata, Mapping):
            pairs = list(metadata.items())
        elif isinstance(metadata, Sequence) and not isinstance(metadata, str | bytes | bytearray):
            pairs = list(metadata)
        else:
            raise ValueError("metadata must be a mapping or a sequence of (label, value) pairs")
        facts = []
        for number, pair in enumerate(pairs, start=1):
            if not (isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], str)):
                raise ValueError(f"metadata item {number} is not a (label, value) pair")
            label = _one_line(pair[0])
            if not label:
                raise ValueError(f"metadata item {number} has no label")
            facts.append((label, self._inline(pair[1]) or self.empty_text))
        return facts

    # document ---------------------------------------------------------------------------

    def _set_fonts(self, document: Any) -> None:
        """One font for the body and the headings; the body size on the Normal style."""
        normal = document.styles["Normal"]
        normal.font.name = self.font_name
        normal.font.size = Pt(self.font_size)
        for name in ("Heading 1", "Heading 2"):
            style = document.styles[name]
            style.font.name = self.font_name
            fonts = style.element.rPr.rFonts
            # The template names a theme font for headings, and a theme font wins over a name.
            for attribute in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                fonts.attrib.pop(qn(attribute), None)

    def _add_table(self, document: Any, rows: list[_Cells], show_evidence: bool) -> None:
        section = document.sections[0]
        usable = (
            (section.page_width or Cm(21))
            - (section.left_margin or Cm(2.5))
            - (section.right_margin or Cm(2.5))
        )
        label_width = min(int(Cm(self.label_width_cm)), usable // 2)
        rest = usable - label_width
        widths = [label_width, rest]
        if show_evidence:
            value_width = rest * 55 // 100
            widths = [label_width, value_width, rest - value_width]

        table = document.add_table(rows=1, cols=len(widths))
        table.style = "Table Grid"
        table.autofit = False
        header = table.rows[0]
        for cell, text in zip(header.cells, self.headers, strict=False):
            cell.paragraphs[0].add_run(text).bold = True
        # Word repeats the header row when the table runs over a page.
        repeat = OxmlElement("w:tblHeader")
        repeat.set(qn("w:val"), "true")
        header._tr.get_or_add_trPr().append(repeat)

        for row in rows:
            cells = table.add_row().cells
            cells[0].paragraphs[0].add_run(row.label).bold = True
            cells[1].paragraphs[0].add_run(row.value)
            if show_evidence and row.evidence:
                cells[2].paragraphs[0].add_run(row.evidence)
        for column, width in zip(table.columns, widths, strict=True):
            column.width = Emu(width)
            for cell in column.cells:
                cell.width = Emu(width)


# helpers --------------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Text that is safe inside a Word file: no control characters, ``\\n`` line ends."""
    return _UNSAFE.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _one_line(text: str) -> str:
    """The cleaned text with every run of whitespace as one space."""
    return " ".join(_clean(text).split())


def _readable(name: str) -> str:
    """``work_done`` as ``Work done``; a name without underscores keeps its casing."""
    text = " ".join(name.replace("_", " ").split())
    return text[:1].upper() + text[1:]


def _docx_path(path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".docx":
        raise ValueError("the output file name must end in .docx")
    return target


def _record_rows(record: Mapping[Any, Any], labels: Mapping[str, str] | None, trace: Any) -> list:
    """One row per field of a record, in the record's order."""
    if not record:
        raise ValueError("the record is empty: nothing to write")
    cited = _citations(trace) if trace is not None else {}
    rows = []
    for key, value in record.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("the field names of a record must be non-blank text")
        label = (labels or {}).get(key) or _readable(key)
        if not isinstance(label, str):
            raise ValueError("labels must map a field name to text")
        quote, verdict = cited.get(key, (None, None))
        rows.append(FieldRow(label=label, value=value, evidence=quote, verdict=verdict))
    return rows


def _citations(trace: Any) -> dict[str, tuple[str | None, str | None]]:
    """Quote and verdict by field path: the first citation of each field."""
    items = trace.get("sources") if isinstance(trace, Mapping) else getattr(trace, "items", None)
    if not isinstance(items, list | tuple):
        raise ValueError("trace must be a SourceTracing TraceReport or its to_dict()")
    cited: dict[str, tuple[str | None, str | None]] = {}
    for item in items:
        name = _get(item, "field")
        if isinstance(name, str) and name not in cited:
            cited[name] = (
                _optional_text(_get(item, "quote")),
                _optional_text(_get(item, "verdict")),
            )
    return cited


def _is_row(item: Mapping[Any, Any]) -> bool:
    """A mapping is a row when it has a value and a label or a name. A record may well have
    a field called ``value``, so that key alone does not make a row."""
    return "value" in item and ("label" in item or "name" in item)


def _row(item: Any, number: int, labels: Mapping[str, str] | None) -> FieldRow:
    """One item of a sequence as a row; ``number`` is its 1-based place, for the error."""
    if isinstance(item, FieldRow):
        label, name = item.label, None
        value, evidence, verdict = item.value, item.evidence, item.verdict
    elif isinstance(item, tuple):
        if len(item) != 2:
            raise ValueError(f"row {number} has {len(item)} items; a pair is (label, value)")
        label, value = item
        name = evidence = verdict = None
    elif isinstance(item, str | bytes | bytearray):
        raise ValueError(f"row {number} is bare text; a row is {_ROW_SHAPES}")
    elif isinstance(item, Mapping):
        if "value" not in item:
            raise ValueError(f"row {number} has no value; a row is {_ROW_SHAPES}")
        label, name = item.get("label"), item.get("name")
        value, evidence, verdict = item["value"], item.get("evidence"), item.get("verdict")
    elif hasattr(item, "value") and (hasattr(item, "label") or hasattr(item, "name")):
        label, name = getattr(item, "label", None), getattr(item, "name", None)
        value = item.value
        evidence, verdict = getattr(item, "evidence", None), getattr(item, "verdict", None)
    else:
        raise ValueError(f"row {number} is a {type(item).__name__}; a row is {_ROW_SHAPES}")

    if label is None or (isinstance(label, str) and not label.strip()):
        # No label of its own: the name, through ``labels`` when it is there.
        if isinstance(name, str) and name.strip():
            label = (labels or {}).get(name) or _readable(name)
        else:
            raise ValueError(f"row {number} has no label")
    if not isinstance(label, str):
        raise ValueError(f"the label of row {number} must be text")
    return FieldRow(
        label=label,
        value=value,
        evidence=_optional_text(evidence),
        verdict=_optional_text(verdict),
    )


def _get(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _appendix_paragraphs(appendix: Any) -> list[str]:
    """The appendix as cleaned, non-empty paragraphs."""
    if appendix is None:
        return []
    if isinstance(appendix, str):
        parts = _BLANK_LINES.split(appendix.replace("\r\n", "\n").replace("\r", "\n"))
    elif isinstance(appendix, Sequence) and not isinstance(appendix, bytes | bytearray):
        parts = list(appendix)
        if not all(isinstance(part, str) for part in parts):
            raise ValueError("the appendix must be text or a sequence of texts")
    else:
        raise ValueError("the appendix must be text or a sequence of texts")
    return [text for text in (_clean(part) for part in parts) if text]


def _set_properties(document: Any, title: str) -> None:
    """The title, and nothing of the template's own author, comment or dates."""
    properties = document.core_properties
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    properties.title = title[:_CORE_TEXT_LIMIT]
    properties.author = ""
    properties.last_modified_by = ""
    properties.comments = ""
    properties.created = now
    properties.modified = now
