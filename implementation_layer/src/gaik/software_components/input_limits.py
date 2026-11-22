"""Input limits that components check before they parse a file or call a model.

Every page of a PDF, every image and every minute of a recording can become a
model call, and a large or crafted file can take a parser's memory and time.
The parsers, extractors, transcribers and the tabular agent therefore check a
file's size, page count, rows, image pixels or duration first, and refuse a
file that is over a limit with :class:`InputLimitError` before any parsing or
model call starts.

The defaults are generous enough for ordinary business documents and
recordings. The page limit applies where every page becomes a model call (the
vision parsers and extractor); a parser that reads the pages locally (PyMuPDF,
Docling, the RAG text parser) defaults to :meth:`InputLimits.local_parsing`,
which has none. A recording is limited by its length, not its size: the size of
a video says little about its audio.

Pass an :class:`InputLimits` to a component to change them; a field set to
``None`` switches that limit off::

    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.parsers import VisionParser

    parser = VisionParser(config, limits=InputLimits(max_pages=50))
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import warnings
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_IMAGE_PIXELS",
    "DEFAULT_MAX_IMAGES",
    "DEFAULT_MAX_MEDIA_BYTES",
    "DEFAULT_MAX_MEDIA_SECONDS",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_MAX_TABLE_ROWS",
    "InputLimitError",
    "InputLimits",
    "count_table_rows",
    "docling_limits",
    "image_size",
    "pdf_page_count",
    "probe_media_seconds",
]

MIB = 1024 * 1024

DEFAULT_MAX_FILE_BYTES = 100 * MIB
"""Largest document, spreadsheet or image file: 100 MiB."""

DEFAULT_MAX_PAGES = 500
"""Most pages in one PDF sent page by page to a model (or, for the vision extractor,
in one call). Parsers that read pages locally have no page limit by default."""

DEFAULT_MAX_TABLE_ROWS = 1_000_000
"""Most rows read from one sheet or CSV file."""

DEFAULT_MAX_IMAGE_PIXELS = 89_478_485
"""Most pixels in one image or rendered page; the same value as Pillow's default."""

DEFAULT_MAX_IMAGES = 500
"""Most embedded images described with a vision model for one document."""

DEFAULT_MAX_MEDIA_BYTES = None
"""Largest audio or video file: no limit by default. ``max_media_seconds`` bounds a
recording's calls, and the size of a video says little about its audio."""

DEFAULT_MAX_MEDIA_SECONDS = 6 * 60 * 60
"""Longest recording: 6 hours."""

# A DOCX or XLSX is a ZIP archive. Its unpacked content may be this many times
# ``max_file_bytes``; real documents compress far less than that.
UNPACKED_SIZE_FACTOR = 10

_ZIP_SUFFIXES = frozenset({".docx", ".xlsx", ".xlsm", ".pptx"})
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"})

# ffprobe reads only the container header; a minute is far more than it needs.
PROBE_TIMEOUT_SECONDS = 60

# How a text file starts when ffmpeg would follow the file names or addresses
# written in it: an HLS playlist and an ffconcat list. A DASH manifest is XML
# with an <MPD> element.
_MEDIA_LIST_STARTS = (b"#EXTM3U", b"ffconcat version")
# XML manifests ffmpeg follows (DASH, IMF), matched in any case within the first
# 64 KiB, more than ffmpeg's own probe reads before it decides; and an SDP session
# description, which names network streams.
_MEDIA_LIST_HEAD_BYTES = 64 * 1024
_MEDIA_LIST_XML = (b"<mpd", b"<compositionplaylist", b"<assetmap")
# A line is everything up to its newline, a carriage return included, so each
# line matches in one way only and the match takes linear time in the head.
_SDP = re.compile(rb"\Av=0\r?\n(?:[^\n]*\n)*?m=", re.IGNORECASE)


def media_input_args(path: str | Path) -> list[str]:
    """ffmpeg or ffprobe arguments that open ``path`` as a local file and nothing else.

    The path is made absolute, so a name such as ``http:...`` or ``concat:...``
    is read as a file and not as a protocol, and only the ``file`` protocol is
    allowed, whatever the installed ffmpeg allows by default.
    """
    return ["-protocol_whitelist", "file", "-i", str(Path(path).absolute())]


def check_not_media_list(path: str | Path) -> None:
    """Refuse a playlist, file list or manifest given in place of a recording.

    ffmpeg reads such a file by opening the files it names, so a recording
    slot would read other files than the one given. The check reads the start
    of the file, so it holds whatever the file's extension and the installed
    ffmpeg version.

    Raises:
        ValueError: If the file starts like an HLS playlist, an ffconcat list,
            a DASH or IMF manifest or an SDP session description.
    """
    path = Path(path)
    try:
        with path.open("rb") as handle:
            head = handle.read(_MEDIA_LIST_HEAD_BYTES)
    except OSError:
        return  # the caller reports a file it cannot read
    head = head.removeprefix(b"\xef\xbb\xbf").lstrip()
    lowered = head.lower()
    is_list = (
        head.startswith(_MEDIA_LIST_STARTS)
        or (head.startswith(b"<") and any(tag in lowered for tag in _MEDIA_LIST_XML))
        or _SDP.match(head) is not None
    )
    if is_list:
        raise ValueError(
            f"{path.name} is a playlist or file list, not a recording; give the "
            "audio or video file itself."
        )


class InputLimitError(ValueError):
    """A file is over one of the :class:`InputLimits` and was not processed.

    It is a :class:`ValueError`, so code that already catches ``ValueError``
    for a file it cannot use keeps working.

    Attributes:
        limit: The name of the :class:`InputLimits` field that was exceeded.
        actual: The file's value (bytes, pages, rows, pixels, images or seconds).
        maximum: The limit it exceeded.
    """

    def __init__(self, message: str, *, limit: str, actual: float, maximum: float) -> None:
        super().__init__(message)
        self.limit = limit
        self.actual = actual
        self.maximum = maximum


def _mib(value: float) -> str:
    if value < 1024:
        return f"{int(value)} bytes"
    if value < MIB:
        return f"{value / 1024:.1f} KiB"
    return f"{value / MIB:.1f} MiB"


def _hms(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


@dataclass(frozen=True)
class InputLimits:
    """Limits a component checks before it parses a file or calls a model.

    Each field is a maximum; ``None`` switches that limit off.

    Attributes:
        max_file_bytes: Size of a document, spreadsheet or image file. A DOCX or
            XLSX may also unpack to at most ten times this size.
        max_pages: Pages in a PDF. The vision extractor counts every PDF page and
            image file of one call together. A parser that reads the pages locally
            defaults to :meth:`local_parsing`, without this limit.
        max_table_rows: Data rows in one sheet or CSV file; the header row and
            blank rows do not count.
        max_image_pixels: Pixels (width x height) of an image file, an embedded
            image or a PDF page rendered for a vision model.
        max_images: Embedded images of one document that are sent to a vision
            model for a description.
        max_media_bytes: Size of an audio or video file; off by default.
        max_media_seconds: Duration of an audio or video file.
    """

    max_file_bytes: int | None = DEFAULT_MAX_FILE_BYTES
    max_pages: int | None = DEFAULT_MAX_PAGES
    max_table_rows: int | None = DEFAULT_MAX_TABLE_ROWS
    max_image_pixels: int | None = DEFAULT_MAX_IMAGE_PIXELS
    max_images: int | None = DEFAULT_MAX_IMAGES
    max_media_bytes: int | None = DEFAULT_MAX_MEDIA_BYTES
    max_media_seconds: float | None = DEFAULT_MAX_MEDIA_SECONDS

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or value <= 0):
                raise ValueError(f"InputLimits.{name} must be a positive number or None")

    @classmethod
    def unlimited(cls) -> InputLimits:
        """Limits with every check switched off."""
        return cls(**dict.fromkeys(cls.__dataclass_fields__))

    @classmethod
    def local_parsing(cls) -> InputLimits:
        """The defaults without the page limit, for a parser that reads pages locally.

        PyMuPDF, Docling and the RAG text parser read a long manual without a model
        call per page, so its page count is not limited; its size still is. These
        are their defaults.
        """
        return cls(max_pages=None)

    # -- single checks ---------------------------------------------------------

    def check_file_size(self, path: str | Path) -> int:
        """Refuse a document, spreadsheet or image larger than ``max_file_bytes``.

        Returns the file's size in bytes.
        """
        path = Path(path)
        size = path.stat().st_size
        if self.max_file_bytes is not None and size > self.max_file_bytes:
            raise InputLimitError(
                f"{path.name} is {_mib(size)}, more than the {_mib(self.max_file_bytes)} "
                "allowed (InputLimits.max_file_bytes).",
                limit="max_file_bytes",
                actual=size,
                maximum=self.max_file_bytes,
            )
        return size

    def check_pages(self, pages: int, name: str) -> None:
        """Refuse more than ``max_pages`` pages."""
        if self.max_pages is not None and pages > self.max_pages:
            raise InputLimitError(
                f"{name} has {pages} pages, more than the {self.max_pages} allowed "
                "(InputLimits.max_pages).",
                limit="max_pages",
                actual=pages,
                maximum=self.max_pages,
            )

    def check_table_rows(self, rows: int, name: str) -> None:
        """Refuse more than ``max_table_rows`` data rows (header and blank rows not counted)."""
        if self.max_table_rows is not None and rows > self.max_table_rows:
            raise InputLimitError(
                f"{name} has more than the {self.max_table_rows} rows allowed "
                "(InputLimits.max_table_rows).",
                limit="max_table_rows",
                actual=rows,
                maximum=self.max_table_rows,
            )

    def check_image_pixels(self, width: float, height: float, name: str) -> None:
        """Refuse an image or rendered page of more than ``max_image_pixels`` pixels."""
        pixels = int(width) * int(height)
        if self.max_image_pixels is not None and pixels > self.max_image_pixels:
            raise InputLimitError(
                f"{name} is {int(width)} x {int(height)} pixels, more than the "
                f"{self.max_image_pixels} pixels allowed (InputLimits.max_image_pixels).",
                limit="max_image_pixels",
                actual=pixels,
                maximum=self.max_image_pixels,
            )

    def check_images(self, images: int, name: str) -> None:
        """Refuse more than ``max_images`` images for vision descriptions."""
        if self.max_images is not None and images > self.max_images:
            raise InputLimitError(
                f"{name} has {images} images to describe, more than the {self.max_images} "
                "allowed (InputLimits.max_images).",
                limit="max_images",
                actual=images,
                maximum=self.max_images,
            )

    def check_images_to_describe(self, sizes: Sequence[tuple[int, int] | None], name: str) -> None:
        """Refuse more than ``max_images`` images, or one over ``max_image_pixels``.

        ``sizes`` holds the ``(width, height)`` of each image a component is about
        to send to a vision model, or ``None`` where the size is unknown.
        """
        self.check_images(len(sizes), name)
        for number, size in enumerate(sizes, start=1):
            if size is not None:
                self.check_image_pixels(size[0], size[1], f"{name}, image {number}")

    def check_media_size(self, path: str | Path) -> int:
        """Refuse an audio or video file larger than ``max_media_bytes``.

        Returns the file's size in bytes.
        """
        path = Path(path)
        size = path.stat().st_size
        if self.max_media_bytes is not None and size > self.max_media_bytes:
            raise InputLimitError(
                f"{path.name} is {_mib(size)}, more than the {_mib(self.max_media_bytes)} "
                "allowed (InputLimits.max_media_bytes).",
                limit="max_media_bytes",
                actual=size,
                maximum=self.max_media_bytes,
            )
        return size

    def check_media_seconds(self, seconds: float, name: str) -> None:
        """Refuse a recording longer than ``max_media_seconds``."""
        if self.max_media_seconds is not None and seconds > self.max_media_seconds:
            raise InputLimitError(
                f"{name} lasts {_hms(seconds)}, longer than the "
                f"{_hms(self.max_media_seconds)} allowed (InputLimits.max_media_seconds).",
                limit="max_media_seconds",
                actual=seconds,
                maximum=self.max_media_seconds,
            )

    # -- file checks -------------------------------------------------------------

    def check_zip_container(self, path: str | Path) -> None:
        """Refuse a DOCX/XLSX over ``max_file_bytes`` or one that unpacks to much more.

        A file that is not a ZIP archive is left to the parser, which reports it.
        """
        path = Path(path)
        self.check_file_size(path)
        if self.max_file_bytes is None or not zipfile.is_zipfile(path):
            return
        with zipfile.ZipFile(path) as archive:
            unpacked = sum(info.file_size for info in archive.infolist())
        maximum = self.max_file_bytes * UNPACKED_SIZE_FACTOR
        if unpacked > maximum:
            raise InputLimitError(
                f"{path.name} unpacks to {_mib(unpacked)}, more than the {_mib(maximum)} "
                f"allowed ({UNPACKED_SIZE_FACTOR} x InputLimits.max_file_bytes).",
                limit="max_file_bytes",
                actual=unpacked,
                maximum=maximum,
            )

    def check_pdf(self, path: str | Path, *, require_count: bool = False) -> int | None:
        """Refuse a PDF over ``max_file_bytes`` or ``max_pages``.

        Returns the page count, or ``None`` when no installed library can count
        the pages (the size is still checked). With ``require_count`` such a PDF
        is refused too while ``max_pages`` is set: use it where the whole file
        goes to a model without being opened first.
        """
        path = Path(path)
        self.check_file_size(path)
        pages = pdf_page_count(path)
        if pages is not None:
            self.check_pages(pages, path.name)
        elif require_count and self.max_pages is not None:
            raise InputLimitError(
                f"The pages of {path.name} cannot be counted, so it cannot be checked "
                "against InputLimits.max_pages.",
                limit="max_pages",
                actual=float("inf"),
                maximum=self.max_pages,
            )
        return pages

    def check_image_file(self, path: str | Path) -> None:
        """Refuse an image file over ``max_file_bytes`` or ``max_image_pixels``.

        The pixel count is read from the image header with Pillow, without
        decoding the image; without Pillow only the size is checked.
        """
        path = Path(path)
        self.check_file_size(path)
        if self.max_image_pixels is None:
            return
        size = _image_header_size(path)
        if size == _TOO_LARGE_FOR_PILLOW:
            raise InputLimitError(
                f"{path.name} has more pixels than Pillow opens, more than the "
                f"{self.max_image_pixels} pixels allowed (InputLimits.max_image_pixels).",
                limit="max_image_pixels",
                actual=float("inf"),
                maximum=self.max_image_pixels,
            )
        if size is not None:
            self.check_image_pixels(size[0], size[1], path.name)

    def check_document(self, path: str | Path) -> None:
        """Run the check that fits the file type: PDF, ZIP-based Office file, image or other.

        A PDF is checked with :meth:`check_pdf`, a DOCX/XLSX/PPTX with
        :meth:`check_zip_container`, an image with :meth:`check_image_file` and
        anything else with :meth:`check_file_size`.
        """
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            self.check_pdf(path)
        elif suffix in _ZIP_SUFFIXES:
            self.check_zip_container(path)
        elif suffix in _IMAGE_SUFFIXES:
            self.check_image_file(path)
        else:
            self.check_file_size(path)

    def check_rendered_page(self, page: Any, zoom: float, name: str) -> None:
        """Refuse a PDF page whose image at ``zoom`` would exceed ``max_image_pixels``.

        ``page`` is a PyMuPDF page; checked before the page is rendered.
        """
        rect = page.rect
        self.check_image_pixels(rect.width * zoom, rect.height * zoom, name)

    def check_media(
        self, path: str | Path, *, timeout: float = PROBE_TIMEOUT_SECONDS
    ) -> float | None:
        """Refuse a recording over ``max_media_bytes`` or ``max_media_seconds``.

        A playlist or file list in place of a recording is refused too
        (:func:`check_not_media_list`), with a :class:`ValueError`.

        The duration is read with ffprobe. Returns it in seconds, or ``None``
        when ffprobe is missing or cannot read the file, or ``max_media_seconds``
        is off; the caller then checks the duration once it has decoded the
        audio, before any model call.
        """
        path = Path(path)
        self.check_media_size(path)
        check_not_media_list(path)
        if self.max_media_seconds is None:
            return None
        seconds = probe_media_seconds(path, timeout=timeout)
        if seconds is not None:
            self.check_media_seconds(seconds, path.name)
        return seconds


def count_table_rows(rows: Iterable[Any], limits: InputLimits, name: str) -> Iterator[Any]:
    """Yield ``rows``, refusing the table once it has more than ``max_table_rows`` data rows.

    A row counts when any of its values (or cells' ``.value``) is not blank; the
    first such row is the header and does not count.
    """
    filled = 0
    for row in rows:
        if any(_filled(getattr(value, "value", value)) for value in row):
            filled += 1
            limits.check_table_rows(filled - 1, name)
        yield row


def _filled(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def docling_limits(limits: InputLimits) -> dict[str, int]:
    """``DocumentConverter.convert`` keyword arguments that apply ``limits`` in Docling too.

    The components check size and pages themselves first; this keeps Docling to
    the same limits when no installed library could count the pages.
    """
    kwargs: dict[str, int] = {}
    if limits.max_pages is not None:
        kwargs["max_num_pages"] = limits.max_pages
    if limits.max_file_bytes is not None:
        kwargs["max_file_size"] = limits.max_file_bytes
    return kwargs


def image_size(image: Any) -> tuple[int, int] | None:
    """``(width, height)`` of a decoded image such as a Pillow image, else ``None``."""
    size = getattr(image, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        return int(size[0]), int(size[1])
    return None


def pdf_page_count(path: str | Path) -> int | None:
    """Page count of a PDF, or ``None`` when no installed library can read it.

    Uses PyMuPDF, else pypdfium2 (installed with Docling). Opening a PDF reads
    its cross-reference table only, not the page content.
    """
    try:
        import pymupdf
    except ImportError:
        pymupdf = None
    if pymupdf is not None:
        try:
            with pymupdf.open(path) as document:
                if document.is_pdf:
                    return document.page_count
        except Exception:
            pass  # try pypdfium2; an unreadable file is the parser's to report
    try:
        import pypdfium2
    except ImportError:
        return None
    try:
        document = pypdfium2.PdfDocument(str(path))
    except Exception:
        return None
    try:
        return len(document)
    finally:
        document.close()


_TOO_LARGE_FOR_PILLOW = (-1, -1)


def _image_header_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        # Image.open reads the header only. The pixel check here comes first, so
        # Pillow's own size warning is not needed and is silenced for this call.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                return image.size
    except Image.DecompressionBombError as error:
        # Pillow refuses to open an image over twice its own pixel limit; its
        # message names the image's pixel count, which is all the check needs.
        match = re.search(r"\((\d+) pixels\)", str(error))
        return (int(match.group(1)), 1) if match else _TOO_LARGE_FOR_PILLOW
    except Exception:
        return None  # not an image Pillow reads; the model or parser reports it


def probe_media_seconds(
    path: str | Path, *, timeout: float = PROBE_TIMEOUT_SECONDS
) -> float | None:
    """Duration of an audio or video file in seconds, read with ffprobe.

    Returns ``None`` when ffprobe is not installed, fails, times out or reports
    no duration.
    """
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                *media_input_args(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        duration = json.loads(result.stdout or "{}").get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (ValueError, TypeError, AttributeError):
        return None
