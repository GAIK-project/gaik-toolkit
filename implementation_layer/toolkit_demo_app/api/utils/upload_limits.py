"""Request body limits, held while the body arrives.

Each route has a whole-request limit and a number of file parts it may carry
(``upload_limits.json`` next to ``main.py``; the Next proxy reads the same
file). ``UploadLimitMiddleware`` refuses a request whose declared
Content-Length is over the route's limit before reading any of it, and stops
reading the body as soon as the bytes received pass the limit or the multipart
body opens one file part more than the route takes. The route's own checks of
each file stay as they are; this one only bounds what is read before them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from python_multipart.multipart import parse_options_header

MIB = 1024 * 1024
LIMITS_FILE = Path(__file__).resolve().parent.parent / "upload_limits.json"
#: Methods whose body is never read, so nothing is counted for them.
_NO_BODY = {"GET", "HEAD", "OPTIONS"}
#: A part's header block longer than this is counted as a file part.
_MAX_PART_HEADERS = 16 * 1024
_FILENAME = re.compile(rb"filename\*?\s*=", re.IGNORECASE)


@dataclass(frozen=True)
class BodyLimit:
    max_bytes: int
    max_files: int
    message: str

    def too_many_files(self) -> str:
        if self.max_files == 0:
            return "This request takes no files."
        noun = "file" if self.max_files == 1 else "files"
        return f"Too many files: at most {self.max_files} {noun} per request."


def _limit(entry: dict) -> BodyLimit:
    return BodyLimit(
        max_bytes=int(entry["max_mb"] * MIB),
        max_files=int(entry["max_files"]),
        message=str(entry["message"]),
    )


def load_limits(path: Path = LIMITS_FILE) -> tuple[BodyLimit, dict[str, BodyLimit]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _limit(data["default"]), {p: _limit(e) for p, e in data["routes"].items()}


DEFAULT_LIMIT, ROUTE_LIMITS = load_limits()


def limit_for(path: str) -> BodyLimit:
    """The limit of an API path: an exact entry, else the longest '/'-ended prefix."""
    if path in ROUTE_LIMITS:
        return ROUTE_LIMITS[path]
    prefixes = [p for p in ROUTE_LIMITS if p.endswith("/") and path.startswith(p)]
    return ROUTE_LIMITS[max(prefixes, key=len)] if prefixes else DEFAULT_LIMIT


def multipart_boundary(content_type: str | None) -> bytes | None:
    """The boundary of a multipart/form-data body, or None for any other body.

    The header is parsed with the same function Starlette's form parser uses,
    so the counter splits the body on the delimiter the parser will use."""
    if not content_type:
        return None
    media_type, params = parse_options_header(content_type)
    if media_type != b"multipart/form-data":
        return None
    return params.get(b"boundary") or None


class FilePartCounter:
    """Counts the file parts of a multipart body as its chunks arrive.

    A part is a file part when its Content-Disposition names a filename, as
    the form parser decides. Only a delimiter's worth of bytes, or one part's
    header block, is kept between chunks."""

    def __init__(self, boundary: bytes):
        self._delimiter = b"\r\n--" + boundary
        # The body opens with "--boundary", without the line break before it.
        self._buffer = b"\r\n"
        self._in_headers = False
        self.files = 0

    def feed(self, chunk: bytes) -> int:
        self._buffer += chunk
        while True:
            if self._in_headers:
                end = self._buffer.find(b"\r\n\r\n")
                if end < 0:
                    if len(self._buffer) > _MAX_PART_HEADERS:
                        self.files += 1
                        self._buffer = self._buffer[-3:]
                        self._in_headers = False
                    return self.files
                if _FILENAME.search(self._buffer[:end]):
                    self.files += 1
                self._buffer = self._buffer[end + 4 :]
                self._in_headers = False
            else:
                start = self._buffer.find(self._delimiter)
                if start < 0:
                    self._buffer = self._buffer[-(len(self._delimiter) - 1) :]
                    return self.files
                rest = self._buffer[start + len(self._delimiter) :]
                if rest.startswith(b"--"):
                    # The closing delimiter: nothing after it is a part.
                    self._buffer = b""
                    return self.files
                self._buffer = rest
                self._in_headers = True


class BodyRefused(HTTPException):
    """Raised from the body reader; the route answers it like any HTTPException."""


def _declared_length(scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _content_type(scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-type":
            return value.decode("latin-1")
    return None


class UploadLimitMiddleware:
    """Holds each route's body limit and file count while the body streams."""

    def __init__(self, app, limit_of=limit_for):
        self.app = app
        self.limit_of = limit_of

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in _NO_BODY:
            return await self.app(scope, receive, send)
        limit = self.limit_of(scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit.max_bytes:
            response = JSONResponse({"detail": limit.message}, status_code=413)
            return await response(scope, receive, send)

        boundary = multipart_boundary(_content_type(scope))
        counter = FilePartCounter(boundary) if boundary else None
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > limit.max_bytes:
                    raise BodyRefused(413, limit.message)
                if counter is not None and counter.feed(chunk) > limit.max_files:
                    raise BodyRefused(400, limit.too_many_files())
            return message

        response_started = False

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyRefused as refused:
            # Read outside the route's own handling (a middleware or a task).
            if response_started:
                raise
            response = JSONResponse({"detail": refused.detail}, status_code=refused.status_code)
            await response(scope, receive, send)
