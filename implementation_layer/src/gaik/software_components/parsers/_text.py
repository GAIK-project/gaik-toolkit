"""The text of a plain-text file (.csv, .txt) from its bytes.

A file with a byte order mark is read in the encoding the mark names, UTF-16 without
one by where its NUL bytes fall, and other content as UTF-8. Content that is not UTF-8
is read as Windows-1252 (cp1252), the code page Excel and Notepad save "ANSI" files in
on Western-European Windows, such as a CSV from Excel in a Finnish locale. Content
that is neither, or that holds NUL bytes and is no UTF-8 (binary data), raises
``ValueError`` with the fix in the message.

A file with a UTF-8 byte order mark is UTF-8 whatever follows: a byte in it that is no
UTF-8 is read as U+FFFD, with a warning, rather than the whole file as cp1252.
"""

from __future__ import annotations

import codecs
import logging
from pathlib import PurePath

from .._log_names import file_tag
from ..file_type import _utf16_codec

logger = logging.getLogger(__name__)

FALLBACK_ENCODING = "cp1252"


def decode_text(
    data: bytes,
    path: str | PurePath,
    encoding: str | None = None,
    *,
    advice: str = "save it as UTF-8",
) -> str:
    """Decode a text file's bytes.

    Args:
        data: The file's content.
        path: The file, named in the error message (by its name) and the log.
        encoding: The file's encoding; ``None`` (default) reads it as the module
            docstring says. A UTF-8 byte order mark is dropped in either case.
        advice: What the error message tells the caller to do with content that
            cannot be decoded.

    Raises:
        ValueError: If ``encoding`` is unknown, or the content cannot be decoded.
    """
    name = PurePath(path).name
    if encoding is not None:
        try:
            codec = codecs.lookup(encoding).name
        except LookupError:
            raise ValueError(f"{name}: unknown text encoding {encoding!r}") from None
        if codec == "utf-8":
            codec = "utf-8-sig"
        try:
            return data.decode(codec)
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"{name}: the content is not {encoding} text (byte {exc.start}); "
                "pass the file's own encoding"
            ) from None
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        codec = "utf-16"
    else:
        codec = _utf16_codec(data[:8192]) or "utf-8-sig"
    try:
        return data.decode(codec)
    except UnicodeDecodeError:
        if codec != "utf-8-sig":
            raise ValueError(f"{name}: the content is not valid UTF-16 text; {advice}") from None
    if data.startswith(codecs.BOM_UTF8):
        text = data.decode("utf-8-sig", "replace")
        logger.warning(
            "%s has a UTF-8 byte order mark but bytes that are no UTF-8; they are read as U+FFFD",
            file_tag(path),
        )
        return text
    if b"\x00" in data:
        # Text in an 8-bit code page has no NUL bytes; binary data has them.
        raise ValueError(f"{name}: the content holds NUL bytes, so it is not text; {advice}")
    try:
        text = data.decode(FALLBACK_ENCODING)
    except UnicodeDecodeError:
        raise ValueError(
            f"{name}: the content is neither UTF-8 nor Windows-1252 text; {advice}"
        ) from None
    logger.warning("%s is not UTF-8; read it as Windows-1252 (cp1252)", file_tag(path))
    return text
