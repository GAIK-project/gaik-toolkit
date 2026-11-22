"""Name a file in a log line without its path or name.

A file name can carry personal data (``Matti_Virtanen_lab_results.pdf``), and so can the
folders above it. Log lines and progress prints name a file by :func:`file_tag` instead:
its extension and a short tag that is the same for the same path within one process, so
the lines about one file can still be followed, but the name cannot be read back. The
salt comes from ``GAIK_LOG_TAG_SALT`` when it is set, so tags match across a
deployment's processes and restarts; otherwise it is new in every process.

Exceptions raised to the caller keep the path: the caller passed it in and needs it.
"""

from __future__ import annotations

import hashlib
import ntpath
import os
import posixpath
import re
import secrets
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

# blake2b takes a key of at most 64 bytes, so a set salt of any length is hashed to 32.
_SALT = (
    hashlib.sha256(os.environ["GAIK_LOG_TAG_SALT"].encode("utf-8")).digest()
    if os.environ.get("GAIK_LOG_TAG_SALT")
    else secrets.token_bytes(16)
)

# Only a known file type is kept as the extension: anything else after the last dot can
# be part of the name ("Virtanen.Matti").
_KNOWN_EXTENSIONS = frozenset(
    ".pdf .docx .doc .xlsx .xls .xlsm .csv .tsv .txt .md .json .xml .html .htm .pptx .odt "
    ".ods .rtf .png .jpg .jpeg .gif .webp .tif .tiff .bmp .heic .mp3 .wav .m4a .ogg .flac "
    ".webm .mp4 .mpeg .mpga .mov .mkv .avi .zip .eml .msg .bpmn .parquet".split()
)


def file_tag(path: str | PurePath | None) -> str:
    """``"file 3f9a1c2b.pdf"`` for a file name or path; ``"file"`` without one."""
    if not path:
        return "file"
    text = str(path)
    suffix = PurePath(text).suffix.lower()
    if suffix not in _KNOWN_EXTENSIONS:
        suffix = ""
    digest = hashlib.blake2b(text.encode("utf-8", "replace"), key=_SALT, digest_size=4)
    return f"file {digest.hexdigest()}{suffix}"


def _absolute(whole: str) -> set[str]:
    """The path made absolute, as given and with links resolved; empty if it cannot be."""
    forms = set()
    for make in (os.path.abspath, lambda text: str(Path(text).resolve())):
        try:
            forms.add(make(whole))
        except (OSError, RuntimeError, ValueError):
            pass
    return forms


def _spellings(whole: str) -> tuple[set[str], set[str]]:
    """The ways a message can spell the path, and the file's stems.

    The spellings: the path as given, with ``..`` and ``.`` collapsed, made absolute or
    resolved, each normalized (``str(PurePath())``, ``as_posix()``) by Windows and by
    POSIX rules and with the doubled backslashes of an OSError's repr; and the file's
    name when it has an extension. They are replaced wherever they appear. A stem
    (``report``) is also an ordinary word, so it is replaced only where it reads as a
    file name (see :func:`_stem_pattern`).
    """
    paths = {whole, ntpath.normpath(whole), posixpath.normpath(whole)} | _absolute(whole)
    forms = set()
    for path in paths:
        for pure in (PureWindowsPath(path), PurePosixPath(path)):
            forms |= {path, str(pure), pure.as_posix()}
    forms |= {form.replace("\\", "\\\\") for form in forms}
    stems = set()
    for pure in (PureWindowsPath(whole), PurePosixPath(whole)):
        if pure.suffix:
            forms.add(pure.name)
        stems.add(pure.stem)
    return {form for form in forms if len(form) >= 3}, {stem for stem in stems if len(stem) >= 3}


def _distinctive(stem: str) -> bool:
    """Unlikely to be an ordinary word: six or more characters, or a space, a digit or
    a letter outside ASCII in it (``Matti Virtanen``, ``scan01``, ``pöytäkirja``)."""
    return len(stem) >= 6 or any(
        char.isspace() or char.isdigit() or (char.isalpha() and not char.isascii()) for char in stem
    )


def _stem_pattern(stem: str) -> str:
    """Where the stem reads as a file name rather than as a word of the message.

    Before it: the start, a path separator, a quote or any other non-word character,
    never a letter, digit or ``_`` (``user_data`` stays). After it: an extension, a
    quote, a path separator, ``_`` or ``-`` (a file named after it, such as
    ``report_chunk_001.wav``); for a distinctive stem (see :func:`_distinctive`) also
    whitespace, a parenthesis, punctuation or the end (``cannot open report (corrupt)``).

    What still passes: a short ASCII stem such as ``notes`` or ``data`` standing as a
    word of the message ("no notes found"), since it is more likely the word than the
    file; the file's path and name are replaced wherever they appear.
    """
    word = re.escape(stem)
    after = r"(?![^\W_])" if _distinctive(stem) else r"(?=\.[^\W\d_]|['\"`/\\_-])"
    return rf"(?<=[/\\'\"`]){word}(?![^\W_])|(?<!\w){word}{after}"


def error_text(exc: BaseException, *paths: str | PurePath | None, limit: int = 300) -> str:
    """``"ValueError: cannot open file 3f9a1c2b.pdf"``: the error's message with each
    path, however it is spelled, and its file name and stem replaced by its tag (see
    :func:`_spellings`), so a log line keeps the cause. The error's type name is kept."""
    message = str(exc)
    for path in paths:
        if not path:
            continue
        forms, stems = _spellings(str(path))
        # One pass, longest spelling first, so a tag is never rewritten.
        alternatives = [re.escape(form) for form in sorted(forms, key=len, reverse=True)]
        alternatives += [_stem_pattern(stem) for stem in sorted(stems, key=len, reverse=True)]
        if alternatives:
            message = re.sub("|".join(alternatives), file_tag(path), message)
    text = f"{type(exc).__name__}: {message}"
    return text if len(text) <= limit else text[: limit - 1] + "…"
