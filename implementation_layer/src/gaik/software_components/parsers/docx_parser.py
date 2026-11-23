"""
Python-docx based parser for Word document (.docx) text extraction.

This module uses python-docx to extract text from Word documents without
requiring external APIs or heavy ML models.
"""

import logging
import os
from typing import Any

from .._log_names import error_text, file_tag
from ..file_type import FileTypeMismatchError, check_file_type
from ..input_limits import InputLimits

try:
    from docx import Document
    from docx.oxml import parse_xml
    from docx.oxml.ns import qn
    from docx.table import Table

    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Warning: python-docx not available. Please install: pip install python-docx")

logger = logging.getLogger(__name__)

_HEADING_LEVELS = {"Title": 1, **{f"Heading {n}": n for n in range(1, 7)}}

# Elements that hold paragraphs, table rows, cells or runs that python-docx only reads
# as direct children: content controls (w:sdt), tracked insertions and moves (w:ins,
# w:moveTo), custom XML and smart tags, and simple fields such as a merge field.
# Tracked deletions (w:del, w:moveFrom) stay out, as Word shows the document.
_WRAPPERS = ("w:sdt", "w:ins", "w:moveTo", "w:customXml", "w:smartTag", "w:fldSimple")
_WRAPPER_PROPERTIES = ("w:sdtPr", "w:sdtEndPr", "w:customXmlPr", "w:smartTagPr", "w:fldData")


# Values of an OOXML on/off property that switch it off (CT_OnOff).
_OFF = frozenset({"0", "false", "off"})


def _placeholder_styles(doc) -> set[str]:
    """The ids of the character style Word puts on placeholder text, if it has one.

    Its name is "Placeholder Text" in every language; its id can be localized. Empty
    when the document defines no such style (a writer other than Word, a style removed).
    """
    try:
        return {
            style.style_id
            for style in doc.styles
            if (style.name or "").lower() == "placeholder text" and style.style_id
        }
    except (AttributeError, KeyError, ValueError):
        return set()


def _placeholder_texts(doc) -> dict[str, str]:
    """The text of each placeholder doc part in the document's glossary, by its name."""
    texts: dict[str, str] = {}
    try:
        for part in doc.part.package.iter_parts():
            if not str(part.partname).endswith("/glossary/document.xml"):
                continue
            for doc_part in parse_xml(part.blob).iter(qn("w:docPart")):
                name = doc_part.find(f"{qn('w:docPartPr')}/{qn('w:name')}")
                body = doc_part.find(qn("w:docPartBody"))
                if name is not None and body is not None:
                    texts[name.get(qn("w:val"))] = _text_of(body)
    except Exception:  # A glossary that cannot be read leaves the old rule.
        return {}
    return texts


def _text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(qn("w:t"))).strip()


def _shows_placeholder(sdt) -> bool:
    flag = sdt.find(f"{qn('w:sdtPr')}/{qn('w:showingPlcHdr')}")
    return flag is not None and (flag.get(qn("w:val")) or "1").lower() not in _OFF


def _drop_placeholder_text(
    sdt, content, placeholder_styles: set[str], placeholder_texts: dict[str, str]
) -> None:
    """Remove the runs of a content control that shows its placeholder.

    With a placeholder text style in the document and styled runs in the control, the
    runs in that style go and other text stays: a generator can fill a control and
    leave its flag on. Otherwise the control's text goes, unless the placeholder doc
    part it names has other text, which means the control was filled.
    """
    style = f"{qn('w:rPr')}/{qn('w:rStyle')}"
    runs = list(content.iter(qn("w:r")))
    if placeholder_styles and any(run.find(style) is not None for run in runs):
        doomed = [
            run
            for run in runs
            if run.find(style) is not None
            and run.find(style).get(qn("w:val")) in placeholder_styles
        ]
    else:
        doc_part = sdt.find(f"{qn('w:sdtPr')}/{qn('w:placeholder')}/{qn('w:docPart')}")
        expected = None if doc_part is None else placeholder_texts.get(doc_part.get(qn("w:val")))
        doomed = runs if expected is None or _text_of(content) == expected else []
    for run in doomed:
        run.getparent().remove(run)


def _unwrap_content(
    body, placeholder_styles: set[str], placeholder_texts: dict[str, str] | None = None
) -> None:
    """Put the content of each wrapper element (see ``_WRAPPERS``) in its place.

    A content control showing its placeholder ("Click here to enter text") holds no
    value: its placeholder text is dropped (see :func:`_drop_placeholder_text`), and
    its paragraphs, rows and cells stay, so the table columns do not shift.
    """
    properties = {qn(tag) for tag in _WRAPPER_PROPERTIES}
    for element in body.xpath(" | ".join(f".//{tag}" for tag in _WRAPPERS)):
        parent = element.getparent()
        if parent is None:
            continue
        if element.tag == qn("w:sdt"):
            content = element.find(qn("w:sdtContent"))
            if content is not None and _shows_placeholder(element):
                _drop_placeholder_text(
                    element, content, placeholder_styles, placeholder_texts or {}
                )
            # Read after the drop: in an inline control the dropped runs are direct
            # children of w:sdtContent, and an earlier copy would put them back.
            children = [] if content is None else list(content)
        else:
            children = [child for child in element if child.tag not in properties]
        index = parent.index(element)
        parent[index : index + 1] = children


class DocxParser:
    """
    A Word document parser using python-docx library for text extraction.

    Features:
    - Fast local DOCX parsing without external APIs
    - Extract text from paragraphs and tables, including the text in content
      controls and tracked insertions (not tracked deletions); ``keep_structure``
      keeps document order, the other modes give the paragraphs, then the tables
    - Simple text extraction or structured output with formatting info
    - Support for Word 2007+ documents (.docx); a Word 97-2003 ``.doc`` file is
      refused with the fix (save it as .docx)
    - Refuses a file over its input limits (size, unpacked size) with
      ``InputLimitError`` before reading it
    """

    def __init__(self, *, limits: InputLimits | None = None):
        """
        Initialize the DocxParser.

        Args:
            limits: Size limits checked before parsing; defaults to
                :class:`~gaik.software_components.input_limits.InputLimits`.

        Raises:
            ImportError: If python-docx is not installed
        """
        if not DOCX_AVAILABLE:
            raise ImportError(
                "python-docx is not available. Install it with: pip install python-docx"
            )

        self.limits = limits or InputLimits()
        # A Word 97-2003 .doc is not read; a DOCX saved under that name still is.
        self.supported_extensions = [".docx"]

    def parse_docx(
        self, file_path: str, use_markdown: bool = True, keep_structure: bool = False
    ) -> str:
        """
        Parse DOCX file and extract text content.

        Args:
            file_path: Path to the DOCX file
            use_markdown: If True, returns simple text.
                If False, returns structured text with formatting
            keep_structure: If True, returns Markdown in document order: heading styles
                as ``#`` headings, paragraphs, and tables as Markdown tables

        Returns:
            Extracted text content as string

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If keep_structure is used with structured text, or the
                file's content is not a DOCX
            FileTypeMismatchError: If the content is not a DOCX, or not the type
                the file's extension says (a ``ValueError``). For a Word 97-2003
                document (.doc), the message says to save it as .docx.
            InputLimitError: If the file is over ``max_file_bytes``, or unpacks
                to more than ten times that
            Exception: If DOCX parsing fails
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        if keep_structure and not use_markdown:
            raise ValueError("keep_structure needs use_markdown=True")
        # A DOCX is a ZIP container holding word/document.xml; python-docx finds
        # the container with zipfile, and so does the content check.
        # The size comes first: the content check reads the archive's directory.
        self.limits.check_file_size(file_path)
        try:
            check_file_type(file_path, {"docx"})
        except FileTypeMismatchError as exc:
            if exc.detected != "ole":
                raise
            raise FileTypeMismatchError(
                f"{exc} DocxParser reads .docx only: open the file in Word or "
                "LibreOffice and save it as .docx.",
                file_name=exc.file_name,
                extension=exc.extension,
                detected=exc.detected,
                expected=exc.expected,
            ) from None
        self.limits.check_zip_container(file_path)

        try:
            doc = Document(file_path)
            _unwrap_content(doc.element.body, _placeholder_styles(doc), _placeholder_texts(doc))

            if keep_structure:
                text_content = self._extract_markdown_docx(doc)
            elif use_markdown:
                # Simple text extraction
                text_content = ""

                # Extract text from paragraphs
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        text_content += paragraph.text + "\n"

                # Extract text from tables
                for table in doc.tables:
                    for row in table.rows:
                        row_text = []
                        for cell in row.cells:
                            if cell.text.strip():
                                row_text.append(cell.text.strip())
                        if row_text:
                            text_content += " | ".join(row_text) + "\n"
            else:
                # Structured extraction preserving layout
                text_content = self._extract_structured_docx(doc)

            return text_content.strip()

        except Exception as e:
            logger.error("Error parsing DOCX %s: %s", file_tag(file_path), error_text(e, file_path))
            raise

    def parse_document(self, file_path: str, use_markdown: bool = True) -> dict[str, Any]:
        """
        Parse a Word document and return its content with metadata.

        Args:
            file_path: Path to the DOCX file
            use_markdown: If True, returns simple text. If False, returns structured text

        Returns:
            Dictionary containing:
                - file_path: Original file path
                - file_name: File name
                - file_extension: File extension (.docx)
                - text_content: Parsed document content
                - content_length: Length of parsed content
                - word_count: Number of words in content
                - parsing_method: 'docx'
                - format_used: 'markdown' or 'structured'

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file is not a DOCX; a Word 97-2003 .doc is refused
                with ``FileTypeMismatchError`` saying to save it as .docx
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_extension = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)

        # A .doc goes on to parse_docx, which reads a DOCX saved under that name and
        # refuses a Word 97-2003 document with the fix.
        if file_extension not in self.supported_extensions and file_extension != ".doc":
            raise ValueError(
                f"Unsupported file type: {file_extension}. Only DOCX files are supported."
            )

        format_type = "markdown" if use_markdown else "structured"
        logger.info("Parsing document: %s (format: %s)", file_tag(file_path), format_type)

        # Extract text
        text_content = self.parse_docx(file_path, use_markdown)

        if not text_content:
            logger.warning("No text content extracted from %s", file_tag(file_path))

        return {
            "file_path": file_path,
            "file_name": file_name,
            "file_extension": file_extension,
            "text_content": text_content,
            "content_length": len(text_content),
            "word_count": len(text_content.split()) if text_content else 0,
            "parsing_method": "docx",
            "format_used": format_type,
        }

    def is_supported_file(self, file_path: str) -> bool:
        """Check if file format is supported (.docx)."""
        extension = os.path.splitext(file_path)[1].lower()
        return extension in self.supported_extensions

    def _extract_markdown_docx(self, doc) -> str:
        """Walk the body in order: headings, paragraphs and tables as Markdown."""
        blocks = []
        for item in doc.iter_inner_content():
            if isinstance(item, Table):
                rows = [
                    [" ".join(c.text.split()).replace("|", "\\|") for c in row.cells]
                    for row in item.rows
                ]
                if rows:
                    header, *body = rows
                    lines = [header, ["---"] * len(header), *body]
                    blocks.append("\n".join("| " + " | ".join(r) + " |" for r in lines))
            elif text := item.text.strip():
                level = _HEADING_LEVELS.get(item.style.name if item.style else "")
                blocks.append(f"{'#' * level} {text}" if level else text)
        return "\n\n".join(blocks)

    def _extract_structured_docx(self, doc) -> str:
        """
        Extract text from DOCX preserving structure and formatting information.

        Args:
            doc: python-docx Document object

        Returns:
            Structured text with formatting markers
        """
        text_parts = []

        # Extract paragraphs with formatting info
        for i, paragraph in enumerate(doc.paragraphs):
            if paragraph.text.strip():
                # Add paragraph structure info
                text_parts.append(f"[PARAGRAPH {i + 1}] {paragraph.text}")

                # Add formatting information if available
                if paragraph.style:
                    text_parts.append(f"[STYLE: {paragraph.style.name}]")

        # Extract tables with structure preservation
        for table_idx, table in enumerate(doc.tables):
            text_parts.append(f"\n=== TABLE {table_idx + 1} ===")

            for row_idx, row in enumerate(table.rows):
                row_data = []
                for cell_idx, cell in enumerate(row.cells):
                    if cell.text.strip():
                        row_data.append(f"[C{cell_idx + 1}] {cell.text.strip()}")

                if row_data:
                    text_parts.append(f"[ROW {row_idx + 1}] {' | '.join(row_data)}")

        return "\n".join(text_parts)


def parse_docx(
    file_path: str, use_markdown: bool = True, output_path: str = None
) -> dict[str, Any]:
    """
    Convenience function to parse a Word document with minimal setup.

    This function provides a simple interface to parse DOCX files using python-docx.
    Fast local parsing without external APIs or ML models.

    Args:
        file_path: Path to the DOCX file
        use_markdown: Return simple text (True) or structured text with formatting (False)
        output_path: Optional path to save the parsed content

    Returns:
        Dictionary with parsed document content and metadata

    Raises:
        ImportError: If python-docx is not installed
        FileNotFoundError: If file does not exist
        ValueError: If file is not a DOCX

    Example:
        >>> from docx_parser import parse_docx
        >>> result = parse_docx("document.docx")
        >>> print(result['text_content'])
        >>>
        >>> # Save to file
        >>> result = parse_docx("document.docx", output_path="output.txt")
        >>>
        >>> # Get structured output with formatting
        >>> result = parse_docx("document.docx", use_markdown=False)
    """
    # Initialize parser
    parser = DocxParser()

    # Parse document
    result = parser.parse_document(file_path, use_markdown=use_markdown)

    # Save to file if output path provided
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["text_content"])
        logger.info("Parsed content saved to %s", file_tag(output_path))

    return result
