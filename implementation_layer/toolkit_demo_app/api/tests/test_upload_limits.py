"""Each route's body limit and file count hold while the body arrives.

The middleware is driven with raw ASGI messages, so a test can see how much of
the body was read when the answer was decided.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path

import pytest
from api.utils.upload_limits import (
    DEFAULT_LIMIT,
    LIMITS_FILE,
    MIB,
    ROUTE_LIMITS,
    BodyLimit,
    FilePartCounter,
    UploadLimitMiddleware,
    limit_for,
    multipart_boundary,
)
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

DEMO = Path(__file__).resolve().parents[2]
BOUNDARY = "----demo-boundary"
SMALL = BodyLimit(max_bytes=1000, max_files=2, message="Uploads exceed the test limit")


def _multipart(files: int, size: int = 10, fields: int = 1) -> bytes:
    parts = [
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="note{i}"\r\n\r\nhello\r\n'.encode()
        for i in range(fields)
    ]
    for i in range(files):
        parts.append(
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="files"; '
            f'filename="f{i}.txt"\r\nContent-Type: text/plain\r\n\r\n'.encode()
            + b"x" * size
            + b"\r\n"
        )
    return b"".join(parts) + f"--{BOUNDARY}--\r\n".encode()


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/upload")
    async def upload(files: list[UploadFile] = File(...), note0: str = Form("")):
        sizes = [len(await f.read()) for f in files]
        return {"files": len(files), "bytes": sum(sizes)}

    app.add_middleware(UploadLimitMiddleware, limit_of=lambda path: SMALL)
    return app


def _run(body_chunks: list[bytes], *, declared: int | None, content_type: str):
    """Send the chunks one receive() at a time; return (status, body, chunks read)."""
    app = _app()
    read = 0
    sent: list[dict] = []
    headers = [(b"content-type", content_type.encode())]
    if declared is not None:
        headers.append((b"content-length", str(declared).encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("test", 1),
        "server": ("test", 80),
    }

    async def receive():
        nonlocal read
        if read < len(body_chunks):
            read += 1
            return {
                "type": "http.request",
                "body": body_chunks[read - 1],
                "more_body": read < len(body_chunks),
            }
        await asyncio.sleep(3600)  # the client waits for the answer
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=10))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(body), read


def _chunks(data: bytes, size: int = 100) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"


def test_upload_within_limits_reaches_the_route():
    body = _multipart(files=2, size=50)
    status, payload, _ = _run(_chunks(body), declared=len(body), content_type=CONTENT_TYPE)
    assert status == 200
    assert payload == {"files": 2, "bytes": 100}


def test_declared_length_over_the_limit_is_refused_before_any_body_is_read():
    status, payload, read = _run([b"x" * 100] * 50, declared=5000, content_type=CONTENT_TYPE)
    assert status == 413
    assert payload == {"detail": "Uploads exceed the test limit"}
    assert read == 0


def test_body_without_declared_length_is_refused_once_bytes_read_pass_the_limit():
    body = _multipart(files=1, size=20_000)
    chunks = _chunks(body)
    status, payload, read = _run(chunks, declared=None, content_type=CONTENT_TYPE)
    assert status == 413
    assert payload == {"detail": "Uploads exceed the test limit"}
    # Reading stopped at the chunk that passed 1000 bytes, not at the end.
    assert read == 11 < len(chunks)


def test_body_longer_than_its_declared_length_is_refused_at_the_limit():
    body = _multipart(files=1, size=20_000)
    chunks = _chunks(body)
    status, _, read = _run(chunks, declared=900, content_type=CONTENT_TYPE)
    assert status == 413
    assert read < len(chunks)


def test_one_file_part_more_than_the_route_takes_is_refused_before_the_rest_is_read():
    body = _multipart(files=6, size=10)
    chunks = _chunks(body, size=40)
    status, payload, read = _run(chunks, declared=None, content_type=CONTENT_TYPE)
    assert len(body) < SMALL.max_bytes
    assert status == 400
    assert payload == {"detail": "Too many files: at most 2 files per request."}
    assert read < len(chunks)


@pytest.mark.parametrize("chunk", [1, 3, 7, 64, 10_000])
def test_file_parts_are_counted_however_the_body_is_split(chunk):
    body = _multipart(files=4, size=300, fields=3)
    counter = FilePartCounter(BOUNDARY.encode())
    for piece in _chunks(body, chunk):
        counter.feed(piece)
    assert counter.files == 4


def test_a_field_named_filename_is_not_a_file_part():
    body = (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="filename"\r\n\r\n'
        f"report.pdf\r\n--{BOUNDARY}--\r\n"
    ).encode()
    counter = FilePartCounter(BOUNDARY.encode())
    assert counter.feed(body) == 0


def test_boundary_is_read_from_quoted_and_plain_content_types():
    assert multipart_boundary('multipart/form-data; boundary="a b"') == b"a b"
    assert multipart_boundary("multipart/form-data; charset=utf-8; boundary=xyz") == b"xyz"
    assert multipart_boundary("application/json") is None


@pytest.mark.parametrize(
    "content_type",
    [
        f"multipart/form-data; xboundary=other; boundary={BOUNDARY}",
        f'multipart/form-data; my-boundary="other"; boundary="{BOUNDARY}"',
        f"Multipart/Form-Data; Boundary={BOUNDARY}",
    ],
)
def test_counter_splits_the_body_on_the_boundary_the_form_parser_uses(content_type):
    # Within the limits, the route's form parser sees both files...
    body = _multipart(files=2, size=10)
    status, payload, _ = _run(_chunks(body), declared=len(body), content_type=content_type)
    assert status == 200
    assert payload == {"files": 2, "bytes": 20}
    # ...and the counter sees the same parts, so one file more is refused.
    body = _multipart(files=3, size=10)
    status, payload, _ = _run(_chunks(body), declared=len(body), content_type=content_type)
    assert status == 400
    assert payload == {"detail": "Too many files: at most 2 files per request."}


def test_route_limits_are_looked_up_by_path_and_prefix():
    assert limit_for("/parse").max_bytes == 22 * MIB
    assert limit_for("/transcribe").max_files == 1
    assert limit_for("/wizard/message/abc").max_bytes == 68 * MIB
    assert limit_for("/rag/query") == DEFAULT_LIMIT
    assert DEFAULT_LIMIT.max_files == 0


def _upload_params(route: APIRoute) -> list[inspect.Parameter]:
    params = inspect.signature(route.endpoint).parameters.values()
    return [p for p in params if "UploadFile" in str(p.annotation)]


def _api_routes(routes, prefix: str = ""):
    """(full path, route) of every APIRoute, through the included routers."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif (context := getattr(route, "include_context", None)) is not None:
            yield from _api_routes(route.original_router.routes, prefix + context.prefix)


def test_every_upload_route_of_the_demo_api_has_a_limit_that_takes_its_files():
    from api.main import app

    routes = list(_api_routes(app.routes))
    assert len(routes) > 50
    upload_paths = set()
    for path, route in routes:
        if not (uploads := _upload_params(route)):
            continue
        upload_paths.add(path)
        limit = limit_for(path)
        assert limit is not DEFAULT_LIMIT, f"{path} takes files but has no entry"
        # A list[UploadFile] parameter takes several files, so it needs room for
        # more than one; a single UploadFile needs room for one.
        needed = sum(2 if "list[" in str(p.annotation) else 1 for p in uploads)
        assert limit.max_files >= needed, path
    named = {p for p in ROUTE_LIMITS if not p.endswith("/")}
    paths = {path for path, _ in routes}
    assert named <= paths, f"entries for routes the API lacks: {named - paths}"
    assert upload_paths <= named


def test_audio_and_document_limits_say_what_the_routes_already_say():
    from api.utils.config import AUDIO_TOO_LARGE_DETAIL, MAX_FILE_SIZE_MB

    assert limit_for("/transcribe").message == AUDIO_TOO_LARGE_DETAIL
    assert limit_for("/parse").message == f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"


def test_largest_limit_fits_the_proxy_and_the_route_in_front_of_the_api():
    largest_mb = max(
        entry["max_mb"] for entry in json.loads(LIMITS_FILE.read_text())["routes"].values()
    )
    next_config = (DEMO / "next.config.ts").read_text()
    route_yaml = (DEMO / "openshift" / "route.yaml").read_text()
    proxy_mb = int(re.search(r'proxyClientMaxBodySize:\s*"(\d+)mb"', next_config).group(1))
    route_mb = int(re.search(r"proxy-body-size:\s*(\d+)m", route_yaml).group(1))
    assert largest_mb <= proxy_mb
    assert largest_mb <= route_mb


def test_the_real_app_refuses_an_oversized_upload_by_its_declared_length():
    from api.main import app

    client = TestClient(app)
    response = client.post(
        "/parse",
        content=b"x" * 10,
        headers={"content-type": CONTENT_TYPE, "content-length": str(23 * MIB)},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "File too large. Maximum size is 20MB"}
