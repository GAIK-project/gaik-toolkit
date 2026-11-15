"""One check for every uploaded file, before a route writes or parses it.

1. What the file is: its content must match its extension (``file_content``).
   Routes that take many kinds of file (report writer, source normalizer) skip
   this step and keep their own rules.
2. What the document carries: DOCX/XLSX/XLSM with macros or ActiveX parts, and
   PDF files with JavaScript, launch or import-data actions or rich media
   (``pdf_content``), are refused.
3. Malware: the ClamAV scan (``malware_scan``), when a scanner is configured.

``upload_problem`` returns what to answer, or None for a file the route may use.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from dataclasses import dataclass

try:
    from utils import malware_scan, pdf_content
    from utils.file_content import content_mismatch
except ImportError:
    from api.utils import malware_scan, pdf_content
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
    return base in {"vbaproject.bin", "vbadata.xml"} or (
        "/activex/" in f"/{lowered}" and base.endswith(".bin")
    )


def office_has_macros(data: bytes) -> bool:
    """A VBA project or ActiveX binary, or a macro-enabled content type."""
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
    return b"macroenabled" in lowered or b"vbaproject" in lowered


def content_problem(suffix: str, data: bytes) -> str | None:
    """Macros or PDF actions; None for a plain document. Blocking."""
    suffix = suffix.lower()
    if suffix in _OFFICE and office_has_macros(data):
        return MACRO_MESSAGE
    if suffix == ".pdf" or data.startswith(b"%PDF-"):
        try:
            pdf_content.check(data)
        except (pdf_content.ActiveContentError, pdf_content.TooComplexError) as exc:
            text = str(exc)
            return text[:1].upper() + text[1:] + "."
    return None


async def upload_problem(
    suffix: str, data: bytes, *, check_type: bool = True
) -> UploadProblem | None:
    """What is wrong with this upload, or None when the route may use it."""
    if check_type and (mismatch := content_mismatch(suffix, data)) is not None:
        return UploadProblem(415, mismatch)
    if (problem := await asyncio.to_thread(content_problem, suffix, data)) is not None:
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
