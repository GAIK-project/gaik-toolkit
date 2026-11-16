"""Keep the file paths read from a manifest, a spec or a config file inside their folder.

A path written in such a file names a file to read or write relative to the file's own
folder. Checked here before anything is opened, so an edited file cannot make another
file on the machine source material for the model.
"""

from __future__ import annotations

from pathlib import Path, PurePath


class SourcePathError(ValueError):
    """A path from a manifest, spec or config file is absolute or leads out of its folder."""


def path_inside(
    entry: str | PurePath,
    base: str | Path,
    *,
    root: str | Path | None = None,
    what: str = "path",
) -> Path:
    """Return ``base / entry`` after checking that it stays inside ``root``.

    Args:
        entry: The path as written in the file, relative to ``base``. An absolute path is
            taken only when ``root`` is given, and must lie inside it.
        base: The folder ``entry`` is relative to, usually the file's own folder.
        root: The folder the path must stay inside; ``base`` by default.
        what: What the path names, for the error message, e.g. ``"source"``.

    The joined path is resolved with symbolic links followed, so a ``..`` segment or a
    link that leads out of ``root`` is refused like an absolute path. Nothing is opened.
    The returned path is ``base / entry`` as joined, not resolved, so a file keeps the
    name it was given.

    Raises:
        SourcePathError: ``entry`` is absolute while ``root`` is not given, or it lies
            outside ``root``.
    """
    pure = PurePath(entry)
    if pure.anchor and root is None:
        raise SourcePathError(
            f"The {what} {str(entry)!r} is an absolute path; write it relative to the "
            "folder of the file that names it"
        )
    joined = Path(base) / pure
    limit = Path(root if root is not None else base).resolve()
    if not joined.resolve().is_relative_to(limit):
        raise SourcePathError(
            f"The {what} {str(entry)!r} is outside the folder {limit.name or limit}/ "
            "(through '..', an absolute path or a symbolic link); keep the file inside it"
        )
    return joined
