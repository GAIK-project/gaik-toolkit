"""File arguments of the tools: paths inside one folder, or base64 content in a working folder.

A path is accepted only when it stays inside the server's root after symbolic links are
followed. The answer for a path outside the root is the same whether or not the file exists.
The server reads no file itself: it hands the path to ``gaik.operations``, which decides the
file type from the content.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

OUTSIDE = "The path is outside the folder this server may read."
NO_ROOT = (
    "This server was started without a folder for paths (--root or GAIK_MCP_ROOT); "
    "send the file as content_base64."
)
NO_WRITE_ROOT = (
    "This server was started without a folder to write to (--root or GAIK_MCP_ROOT); "
    "leave output_path out to get the content."
)
NOT_FOUND = "File not found."

_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}")


def megabytes(size: int) -> str:
    """A byte count as megabytes for a message: ``25`` or ``0.5``."""
    return f"{size / (1024 * 1024):.3g}"


def too_large(max_bytes: int) -> ValueError:
    return ValueError(f"The file is too large. The limit is {megabytes(max_bytes)} MB.")


def inside_root(path: str, root: Path | None) -> Path:
    """The path with links followed, when it stays inside the root.

    Raises:
        PermissionError: There is no root, or the path leaves it.
        ValueError: The path is empty or holds a NUL.
    """
    if root is None:
        raise PermissionError(NO_ROOT)
    if not path or not path.strip() or "\x00" in path:
        raise ValueError("The path is not valid.")
    base = root.resolve()
    # Text only, no file access: a path on another drive, share or device is refused before
    # anything is opened (resolving a network path would contact that host).
    lexical = Path(os.path.abspath(base / path))
    if lexical.anchor.lower() != base.anchor.lower():
        raise PermissionError(OUTSIDE)
    try:
        resolved = lexical.resolve(strict=False)
    except (OSError, RuntimeError):  # a loop of links, or a name the system refuses
        raise PermissionError(OUTSIDE) from None
    if not resolved.is_relative_to(base):
        raise PermissionError(OUTSIDE)
    return resolved


def input_path(path: str, root: Path | None, max_bytes: int) -> Path:
    """A file an operation may read: inside the root, a regular file, within the size limit."""
    resolved = inside_root(path, root)
    if not resolved.is_file():
        raise FileNotFoundError(NOT_FOUND)
    if resolved.stat().st_size > max_bytes:
        raise too_large(max_bytes)
    return resolved


def output_path(path: str, root: Path | None, *, overwrite: bool) -> Path:
    """Where a Word file may be written: inside the root, ``.docx``, not there yet."""
    if root is None:
        raise PermissionError(NO_WRITE_ROOT)
    resolved = inside_root(path, root)
    if resolved.suffix.lower() != ".docx":
        raise ValueError("output_path must end in .docx.")
    if resolved.is_dir():
        raise ValueError("output_path is a folder.")
    if resolved.exists() and not overwrite:
        raise ValueError("The file exists already. Set overwrite to replace it.")
    return resolved


def write_output(path: Path, content: bytes, *, overwrite: bool) -> None:
    """Write the file, with its parent folders. Without ``overwrite`` an existing file stays."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "wb" if overwrite else "xb") as handle:
            handle.write(content)
    except FileExistsError:
        raise ValueError("The file exists already. Set overwrite to replace it.") from None


def shown_path(path: Path, root: Path) -> str:
    """The path as the agent gets it back: relative to the root, with forward slashes."""
    return path.relative_to(root.resolve()).as_posix()


def decoded_size(content_base64: str) -> int:
    """How many bytes the base64 text decodes to, without decoding it."""
    padding = len(content_base64) - len(content_base64.rstrip("="))
    return max(0, len(content_base64) * 3 // 4 - min(padding, 2))


def decode(content_base64: str, max_bytes: int) -> bytes:
    """Strictly decoded content. The size is checked before decoding."""
    if decoded_size(content_base64) > max_bytes:
        raise too_large(max_bytes)
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("content_base64 is not valid base64.") from None
    if not data:
        raise ValueError("The file is empty.")
    return data


def suffix_of(filename: str | None) -> str:
    """The extension of a file name the client sent, lower-cased. Nothing else of it is used."""
    suffix = PurePosixPath((filename or "").strip().replace("\\", "/")).suffix
    if not _SUFFIX.fullmatch(suffix):
        raise ValueError("Give filename with the file's extension, for example report.pdf.")
    return suffix.lower()


@dataclass(frozen=True)
class FileSource:
    """A checked file argument: a path inside the root, or content to put in a working folder."""

    path: Path | None = None
    content_base64: str | None = None
    suffix: str = ""
    max_bytes: int = 0
    work_dir: str | Path | None = None

    @contextlib.contextmanager
    def open(self) -> Iterator[Path]:
        """The file on disk. Content is written under a name the server makes, in a folder
        that is removed when the block ends."""
        if self.path is not None:
            yield self.path
            return
        data = decode(self.content_base64 or "", self.max_bytes)
        with tempfile.TemporaryDirectory(prefix="gaik-mcp-", dir=self.work_dir) as folder:
            local = Path(folder) / f"input{self.suffix}"
            local.write_bytes(data)
            del data
            yield local


def file_source(
    *,
    path: str | None,
    content_base64: str | None,
    filename: str | None,
    root: Path | None,
    max_bytes: int,
    work_dir: str | Path | None = None,
) -> FileSource:
    """Check a tool's file arguments: exactly one of ``path`` and ``content_base64``.

    Everything that can be refused without decoding is refused here: the path rules, a
    missing file name and the size of the content.
    """
    if (path is None) == (content_base64 is None):
        raise ValueError("Give exactly one of path and content_base64.")
    if path is not None:
        return FileSource(path=input_path(path, root, max_bytes))
    suffix = suffix_of(filename)
    if decoded_size(content_base64 or "") > max_bytes:
        raise too_large(max_bytes)
    return FileSource(
        content_base64=content_base64, suffix=suffix, max_bytes=max_bytes, work_dir=work_dir
    )
