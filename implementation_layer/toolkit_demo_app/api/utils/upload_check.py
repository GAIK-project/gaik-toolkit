"""One check for every uploaded file, before a route writes or parses it.

1. What the file is: its content must match its extension (``file_content``).
   Routes that take many kinds of file (report writer, source normalizer) skip
   this step and keep their own rules.
2. What the document carries: DOCX/XLSX/XLSM with a VBA project, macro sheets
   or ActiveX controls (an ``.xlsm`` without them passes, though Excel marks
   every ``.xlsm`` as macro-enabled), and
   PDF files with JavaScript, launch or import-data actions or rich media
   (``pdf_content``), are refused.
3. Malware: the ClamAV scan (``malware_scan``), when a scanner is configured.

Step 2 runs in a small pool of its own, so slow checks never hold the threads
other routes use. The PDF check runs in a process of its own (``pdf_process``),
so it never holds the API's interpreter, and that process is stopped at a
deadline.

``upload_problem`` returns what to answer, or None for a file the route may use.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

try:
    from utils import malware_scan, pdf_content, pdf_process
    from utils.file_content import content_mismatch
except ImportError:
    from api.utils import malware_scan, pdf_content, pdf_process
    from api.utils.file_content import content_mismatch

_OFFICE = {".docx", ".xlsx", ".xlsm"}
MACRO_MESSAGE = "Files with macros are not accepted. Save the document without macros."


@dataclass(frozen=True)
class UploadProblem:
    status: int
    message: str


def _is_macro_part(name: str) -> bool:
    lowered = name.lower().replace("\\", "/")
    base = lowered.rsplit("/", 1)[-1]
    return (
        base in {"vbaproject.bin", "vbadata.xml"}
        # An ActiveX control is a binary part or one kept as XML; either runs.
        or "/activex/" in f"/{lowered}"
        or "/macrosheets/" in f"/{lowered}"
    )


def office_has_macros(data: bytes) -> bool:
    """A VBA project, macro sheet or ActiveX control, by part name or content type.

    The workbook's macro-enabled content type alone is not a macro: Excel
    writes it for every ``.xlsm``, with or without code."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if any(_is_macro_part(name) for name in names):
                return True
            if "[Content_Types].xml" not in names:
                return False
            info = archive.getinfo("[Content_Types].xml")
            if info.file_size > 1024 * 1024:
                return True  # no real content-types part is this large
            lowered = archive.read(info).lower()
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, NotImplementedError):
        return False  # not an archive we can read: the type check reports it
    return b"vbaproject" in lowered or b"macrosheet" in lowered or b"activex" in lowered


def content_problem(suffix: str, data: bytes) -> str | None:
    """Macros or PDF actions; None for a plain document. Blocking."""
    suffix = suffix.lower()
    if suffix in _OFFICE and office_has_macros(data):
        return MACRO_MESSAGE
    if suffix == ".pdf" or data.startswith(b"%PDF-"):
        try:
            pdf_process.check(data)
        except (pdf_content.ActiveContentError, pdf_content.TooComplexError) as exc:
            text = str(exc)
            return text[:1].upper() + text[1:] + "."
    return None


#: Content checks at a time; more wait for a free thread.
CHECK_THREADS = 2
_checks = ThreadPoolExecutor(max_workers=CHECK_THREADS, thread_name_prefix="upload-check")


async def upload_problem(
    suffix: str, data: bytes, *, check_type: bool = True
) -> UploadProblem | None:
    """What is wrong with this upload, or None when the route may use it."""
    if check_type and (mismatch := content_mismatch(suffix, data)) is not None:
        return UploadProblem(415, mismatch)
    loop = asyncio.get_running_loop()
    if (problem := await loop.run_in_executor(_checks, content_problem, suffix, data)) is not None:
        return UploadProblem(422, problem)
    try:
        await malware_scan.check_upload(data)
    except malware_scan.UnsafeInputError as exc:
        text = str(exc)
        return UploadProblem(422, text[:1].upper() + text[1:] + ".")
    except malware_scan.ScannerUnavailableError:
        text = malware_scan.UNAVAILABLE_MESSAGE
        return UploadProblem(503, text[:1].upper() + text[1:] + ".")
    return None
