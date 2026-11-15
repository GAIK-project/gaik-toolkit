"""Settings of the MCP server: the allowed folder, the size limits and the model settings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gaik.operations import OperationSettings

MAX_FIELDS = 60
MAX_LABELS = 50
MAX_OPTIONS = 100
"""Allowed values of one field."""
MAX_NAME_CHARS = 200
"""Longest label, field name, field label and date format."""
MAX_REQUIREMENT_CHARS = 4000
DEFAULT_WINDOW_CHARS = 50_000
JEV_MAX_CHARS = 10_000
"""What ``JevClassifier.classify`` reads of a text; it cuts the rest without saying so."""
MIN_TOKEN_CHARS = 32
"""Shortest bearer token the HTTP transport accepts."""

# Seconds a tool waits at least for its operation (`run_async(..., deadline=)`). A model
# tool waits longer when one model request may take longer: see `deadline`.
# Parsing itself takes seconds. The first call imports gaik's parsers package, and that
# loads Docling when it is installed (gaik[parser], gaik[all]): up to a minute or more.
PARSE_DEADLINE = 300.0
TRANSCRIBE_DEADLINE = 900.0
GENERATE_DEADLINE = 300.0
EXTRACT_DEADLINE = 300.0
CLASSIFY_DEADLINE = 120.0
WORD_DEADLINE = 60.0
DEADLINE_MARGIN = 30.0
"""Seconds a model tool waits beyond the model's own request timeout."""

DEFAULT_MAX_FILE_MB = 25.0
DEFAULT_MAX_TEXT_CHARS = 100_000
DEFAULT_TIMEOUT = 120.0


def deadline(least: float, request_timeout: float | None) -> float:
    """Seconds a model tool waits for its operation.

    Never less than ``least``, and never less than one model request may take plus a
    margin. A tool that gave up before the request did would report a failure for an
    answer that was still coming, and leave its worker thread running.
    """
    if not request_timeout or request_timeout <= 0:
        return least
    return max(least, request_timeout + DEADLINE_MARGIN)


@dataclass(frozen=True)
class ServerSettings:
    """What one server may read and how much, and how its operations reach a model."""

    root: Path | None = None
    """The only folder path arguments may point into, and the only one ``fields_to_word``
    writes to. None: paths are refused."""
    max_file_bytes: int = int(DEFAULT_MAX_FILE_MB * 1024 * 1024)
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    """Longest text argument, and the longest text window ``parse_document`` returns."""
    operations: OperationSettings = field(default_factory=OperationSettings)
    token: str | None = field(default=None, repr=False)
    """Bearer token of the HTTP transport."""
    allowed_hosts: tuple[str, ...] = ()
    """Host headers the HTTP transport answers besides localhost and 127.0.0.1."""
    jev_url: str | None = None
    jev_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str],
        *,
        root: str | Path | None = None,
        provider: str | None = None,
        allowed_hosts: Sequence[str] = (),
    ) -> ServerSettings:
        """Settings from ``GAIK_MCP_*`` variables. An argument wins over its variable.

        There is no root unless one is named, on either transport: the folder a client
        starts the server in can be the filesystem root or the home folder.

        Raises:
            ValueError: A number is not a positive number, or the root is not a folder, is
                a whole drive or holds the home folder.
        """
        folder = root if root is not None else _text(environ, "GAIK_MCP_ROOT")
        hosts = [host.strip() for host in allowed_hosts if host.strip()]
        if not hosts:
            listed = _text(environ, "GAIK_MCP_ALLOWED_HOSTS") or ""
            hosts = [host.strip() for host in listed.split(",") if host.strip()]
        megabytes = _number(environ, "GAIK_MCP_MAX_FILE_MB", DEFAULT_MAX_FILE_MB)
        return cls(
            root=None if folder is None else _folder(folder),
            max_file_bytes=int(megabytes * 1024 * 1024),
            max_text_chars=int(_number(environ, "GAIK_MCP_MAX_TEXT_CHARS", DEFAULT_MAX_TEXT_CHARS)),
            operations=OperationSettings(
                provider=(provider or "").strip() or None,
                timeout=_number(environ, "GAIK_MCP_TIMEOUT", DEFAULT_TIMEOUT),
            ),
            token=_text(environ, "GAIK_MCP_TOKEN"),
            allowed_hosts=tuple(hosts),
            jev_url=_text(environ, "GAIK_DECIDE_URL"),
            jev_key=_text(environ, "GAIK_DECIDE_API_KEY"),
        )


def _text(environ: Mapping[str, str], name: str) -> str | None:
    return (environ.get(name) or "").strip() or None


def _number(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = _text(environ, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not 0 < value < float("inf"):
        raise ValueError(f"{name} must be a positive number")
    return value


def _folder(folder: str | Path) -> Path:
    path = Path(folder).expanduser()
    if not path.is_dir():
        raise ValueError("the root folder does not exist")
    resolved = path.resolve()
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):  # no home folder to protect
        home = None
    if resolved == Path(resolved.anchor) or (home is not None and home.is_relative_to(resolved)):
        # `--root .` in a client that starts its servers in `/` or in the home folder
        # would open every document of the user to the agent.
        raise ValueError(
            "the root folder must not be a whole drive, the filesystem root, the home "
            "folder or a folder that holds it; name a project folder"
        )
    return resolved
