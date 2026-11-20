"""parse_document: the text of a PDF, DOCX or text file, read locally."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from ._runtime import maybe_quiet, need
from .models import ParsedDocument
from .settings import OperationSettings

TEXT_SUFFIXES = (".txt", ".md")

# A DOCX is a ZIP archive, and the parser loads its parts into memory whole. A small file
# can unpack to gigabytes, so the unpacked sizes are checked before anything is read.
MAX_DOCX_UNPACKED_BYTES = 200 * 1024 * 1024
"""Largest total size of the parts of a DOCX."""
MAX_DOCX_MARKUP_BYTES = 50 * 1024 * 1024
"""Largest total size of the parts that pack to under a fifth of their size: the markup.
Pictures are packed already and do not count."""
_MARKUP_RATIO = 5

_PDF_HEADER = b"%PDF-"
_UTF8_MARK = b"\xef\xbb\xbf"

_PAGE_MARK = re.compile(r"^\[Page (\d+)\]\n?", re.MULTILINE)
_UTF16_MARKS = (b"\xff\xfe", b"\xfe\xff")


def parse_document(
    path: str | Path, *, settings: OperationSettings | None = None
) -> ParsedDocument:
    """Read the text of a PDF, DOCX, .txt or .md file. No model call and no OCR.

    The kind is decided from the content, not the name. ``pages`` has one entry per PDF
    page; a DOCX (Markdown with its headings and tables in document order) and a text file
    are one page.

    Raises:
        FileNotFoundError: There is no such file.
        ValueError: The file is of another kind, holds no text (a scanned PDF), or is a
            DOCX that unpacks to more than the parser may load.
        InputLimitError: The file is over the parser's input limits (a ``ValueError``
            whose message names the file and the limit).
        ImportError: The parser's package is not installed.
    """
    settings = settings or OperationSettings()
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError("file not found")
    kind = _kind(file)
    if kind == "pdf":
        with maybe_quiet(settings.quiet):
            pages = _pdf_pages(file)
    elif kind == "docx":
        with maybe_quiet(settings.quiet):
            pages = [_docx_text(file)]
    else:
        pages = [_decode(file.read_bytes()).replace("\r\n", "\n").strip()]
    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError("no text was found in the file; a scanned PDF needs a vision parser")
    return ParsedDocument(text=text, pages=pages, kind=kind)


def _kind(file: Path) -> Literal["pdf", "docx", "text"]:
    """What the file is, from its content. The name only separates text from the unknown."""
    with file.open("rb") as handle:
        head = handle.read(2048)
    if head.removeprefix(_UTF8_MARK).lstrip().startswith(_PDF_HEADER):
        return "pdf"
    if head.startswith(b"PK") and zipfile.is_zipfile(file):
        with zipfile.ZipFile(file) as archive:
            if "word/document.xml" in archive.namelist():
                _check_unpacked_size(archive)
                return "docx"
        raise _unsupported()
    # `Path(".txt").suffix` is empty, so a dot-file or a file without a suffix is not text.
    if file.suffix.lower() in TEXT_SUFFIXES and (
        head.startswith(_UTF16_MARKS) or b"\x00" not in head
    ):
        # Also a note that only mentions the PDF header somewhere in its first lines.
        return "text"
    if _PDF_HEADER in head[:1024]:
        # PDF readers accept a header that is not the first thing in the file.
        return "pdf"
    raise _unsupported()


def _check_unpacked_size(archive: zipfile.ZipFile) -> None:
    """Refuse a DOCX whose parts unpack to more than the parser should load.

    The sizes come from the archive's directory. Unpacking stops at the size written
    there, so a part cannot be larger than it says.
    """
    total = markup = 0
    for part in archive.infolist():
        total += part.file_size
        if part.file_size > _MARKUP_RATIO * part.compress_size:
            markup += part.file_size
    if total > MAX_DOCX_UNPACKED_BYTES or markup > MAX_DOCX_MARKUP_BYTES:
        raise ValueError("the Word file is too large when unpacked")


def _unsupported() -> ValueError:
    return ValueError("unsupported file type: use a PDF, DOCX, .txt or .md file")


def _decode(data: bytes) -> str:
    if data.startswith(_UTF16_MARKS):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Text files from Windows tools are often in the ANSI code page.
        return data.decode("cp1252", errors="replace")


def _split_pages(marked: str, page_count: int) -> list[str] | None:
    """The pages of a text with one ``[Page N]`` line per page.

    None when the marks do not run 1..page_count: a page that holds such a line itself
    makes one mark too many, and then no split can be trusted.
    """
    marks = list(_PAGE_MARK.finditer(marked))
    if [int(mark.group(1)) for mark in marks] != list(range(1, page_count + 1)):
        return None
    ends = [mark.start() for mark in marks[1:]] + [len(marked)]
    return [marked[mark.end() : end].strip() for mark, end in zip(marks, ends, strict=True)]


def _pdf_pages(file: Path) -> list[str]:
    if importlib.util.find_spec("pymupdf") is None:
        raise need("parse_document", "PyMuPDF")
    try:
        import pymupdf

        from gaik.software_components.input_limits import InputLimitError
        from gaik.software_components.parsers import PyMuPDFParser
    except ImportError as error:
        raise need("parse_document", "PyMuPDF") from error

    parser = PyMuPDFParser()
    # The size is checked on the file itself before it is opened, so the message names
    # the caller's file and not the name the parser is given below.
    parser.limits.check_file_size(file)
    with pymupdf.open(file) as document:
        # PyMuPDF picks its handler from the name and the content; the parser gets a
        # .pdf name below, so a file PyMuPDF does not read as a PDF stops here.
        if not document.is_pdf:
            raise ValueError("the content of the file is not a PDF document")
        page_count = document.page_count
    try:
        with _named_as(file, ".pdf") as named:
            marked = parser.parse_pdf(str(named), page_markers=True)
    except InputLimitError:
        # A PDF over a limit is still a PDF; the message names the file only.
        raise
    except ValueError:
        # The parser's own message holds the full path it was given.
        raise ValueError("the content of the file is not a PDF document") from None
    pages = _split_pages(marked, page_count)
    if pages is None:
        # The call the parser makes for each page, without the marks.
        with pymupdf.open(file) as document:
            pages = [str(page.get_text()).strip() for page in document]
    return pages


def _docx_text(file: Path) -> str:
    if importlib.util.find_spec("docx") is None:
        raise need("parse_document", "python-docx")
    try:
        from gaik.software_components.parsers import DocxParser
    except ImportError as error:
        raise need("parse_document", "python-docx") from error
    parser = DocxParser()
    # The limits are checked on the file itself, so a message names the caller's file
    # and not the name the parser is given below.
    parser.limits.check_zip_container(file)
    with _named_as(file, ".docx") as named:
        return parser.parse_docx(str(named), keep_structure=True).strip()


@contextmanager
def _named_as(file: Path, suffix: str) -> Iterator[Path]:
    """``file`` under a name that ends in ``suffix``.

    The kind here comes from the content, and the parsers refuse a file whose
    extension names another type; a file of the right kind under another name is
    handed to them as a link (or a copy) with the matching extension. A message the
    parser raises then names ``document`` with that extension, so the callers check
    the input limits on ``file`` first.
    """
    if file.suffix.lower() == suffix:
        yield file
        return
    with tempfile.TemporaryDirectory() as folder:
        named = Path(folder) / f"document{suffix}"
        try:
            os.symlink(file.resolve(), named)
        except OSError:
            shutil.copyfile(file, named)
        yield named
