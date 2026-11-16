"""Uploads pass a malware scanner and a check of PDF actions and office macros.

The scanner here is a small fake clamd on a local port, speaking the same
INSTREAM protocol; the last test runs against a real one when
``DEMO_TEST_CLAMD`` names it. Every file is generated here; the "malware" is
the EICAR test string, which is harmless by design.
"""

from __future__ import annotations

import asyncio
import io
import os
import socket
import struct
import threading
import time
import zipfile
import zlib
from pathlib import Path

import pytest
from api.routers import classifier as route
from api.utils import malware_scan
from api.utils.upload_check import content_problem, office_has_macros, upload_problem
from fastapi import FastAPI
from fastapi.testclient import TestClient

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JS_ACTION = b"<< /S /JavaScript /JS (app.alert(1)) >>"


def _pdf(catalog_extra: bytes = b"", objects: bytes = b"") -> bytes:
    return (
        b"%PDF-1.7\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b">>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
        + objects
        + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )


def _stream(num: int, dictionary: bytes, data: bytes) -> bytes:
    return (
        f"{num} 0 obj\n<< ".encode()
        + dictionary
        + f" /Length {len(data)} >>\nstream\n".encode()
        + data
        + b"\nendstream\nendobj\n"
    )


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _docx(extra: dict[str, bytes] | None = None) -> bytes:
    return _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w/>", **(extra or {})})


def _xlsm(extra: dict[str, bytes] | None = None, types: bytes = b"") -> bytes:
    content_types = (
        b'<Types><Override PartName="/xl/workbook.xml" '
        b'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/>'
        + types
        + b"</Types>"
    )
    return _zip(
        {"[Content_Types].xml": content_types, "xl/workbook.xml": b"<workbook/>", **(extra or {})}
    )


# ---------------------------------------------------------------------------
# What a document carries
# ---------------------------------------------------------------------------


def test_a_plain_pdf_and_a_link_mentioning_javascript_pass():
    link = b"4 0 obj\n<< /S /URI /URI (https://example.test/JavaScript/guide) >>\nendobj\n"
    assert content_problem(".pdf", _pdf()) is None
    assert content_problem(".pdf", _pdf(objects=link)) is None


@pytest.mark.parametrize(
    "catalog",
    [
        b"/OpenAction " + JS_ACTION,
        b"/OpenAction << /S /J#61vaScript /JS 7 0 R >>",
        b"/OpenAction << /S %hidden\n/JavaScript /JS (x) >>",
        b"/OpenAction << /S /Launch /F (cmd.exe) >>",
    ],
)
def test_a_pdf_with_an_action_a_viewer_would_run_is_refused(catalog):
    assert content_problem(".pdf", _pdf(catalog)).startswith("PDF files that contain")


def test_javascript_inside_a_compressed_object_stream_is_found():
    body = b"10 0 " + JS_ACTION
    hidden = _stream(9, b"/Type /ObjStm /N 1 /First 4 /Filter /FlateDecode", zlib.compress(body))
    assert "JavaScript" in content_problem(".pdf", _pdf(b"/OpenAction 10 0 R", hidden))


def test_image_data_is_not_read_for_actions():
    image = _stream(
        6,
        b"/Type /XObject /Subtype /Image /Width 1 /Height 1 /Filter /FlateDecode",
        zlib.compress(b"/S /JavaScript " * 100),
    )
    assert content_problem(".pdf", _pdf(objects=image)) is None


@pytest.mark.parametrize(
    "suffix, data",
    [
        (".docx", _docx({"word/vbaProject.bin": b"\xd0\xcf\x11\xe0"})),
        (".docx", _docx({"word/activeX/activeX1.bin": b"\xd0\xcf\x11\xe0"})),
        (".xlsm", _xlsm({"xl/vbaProject.bin": b"\xd0\xcf\x11\xe0"})),
        (".xlsm", _xlsm({"xl/macrosheets/sheet1.xml": b"<xm:macrosheet/>"})),
        (
            ".xlsm",
            _xlsm(
                types=b'<Override PartName="/xl/m.xml" '
                b'ContentType="application/vnd.ms-excel.macrosheet+xml"/>'
            ),
        ),
    ],
)
def test_an_office_file_with_macros_is_refused(suffix, data):
    assert office_has_macros(data)
    assert "macros" in content_problem(suffix, data)


ACTIVEX_XML = b'<ax:ocx xmlns:ax="http://schemas.microsoft.com/office/2006/activeX"/>'
ACTIVEX_TYPE = b"application/vnd.ms-office.activeX+xml"


@pytest.mark.parametrize(
    "suffix, data",
    [
        # A control kept as XML, not as a binary part.
        (".docx", _docx({"word/activeX/activeX1.xml": ACTIVEX_XML})),
        (".xlsx", _zip({"[Content_Types].xml": b"<Types/>", "xl/activeX/activeX1.xml": b"<x/>"})),
        (".xlsm", _xlsm({"xl/activeX/activeX1.xml": ACTIVEX_XML})),
        # A control in a part of another name, known by its content type.
        (
            ".xlsx",
            _zip(
                {
                    "[Content_Types].xml": b'<Types><Override PartName="/xl/c/c1.xml" '
                    b'ContentType="' + ACTIVEX_TYPE + b'"/></Types>',
                    "xl/c/c1.xml": ACTIVEX_XML,
                }
            ),
        ),
    ],
)
def test_an_office_file_with_an_activex_control_in_any_form_is_refused(suffix, data):
    assert "macros" in content_problem(suffix, data)


def test_an_office_file_without_macros_passes():
    assert content_problem(".docx", _docx()) is None


def test_a_macro_enabled_workbook_without_macros_passes():
    # Excel marks every .xlsm as macro-enabled, with or without code.
    assert content_problem(".xlsm", _xlsm()) is None


# ---------------------------------------------------------------------------
# The scanner
# ---------------------------------------------------------------------------


class FakeClamd:
    """Answers like clamd: FOUND for the EICAR string, OK otherwise."""

    def __init__(self, reply: bytes | None = None) -> None:
        self.reply = reply
        self.received: list[bytes] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                self._handle(conn)

    def _handle(self, conn: socket.socket) -> None:
        buf = b""
        while b"\0" not in buf:
            part = conn.recv(4096)
            if not part:
                return
            buf += part
        command, _, buf = buf.partition(b"\0")
        if command == b"zPING":
            conn.sendall(b"PONG\0")
            return
        data = b""
        while True:
            while len(buf) < 4:
                buf += conn.recv(4096)
            (size,) = struct.unpack(">I", buf[:4])
            buf = buf[4:]
            if size == 0:
                break
            while len(buf) < size:
                buf += conn.recv(65536)
            data, buf = data + buf[:size], buf[size:]
        self.received.append(data)
        if self.reply is not None:
            conn.sendall(self.reply)
        elif EICAR in data:
            conn.sendall(b"stream: Eicar-Test-Signature FOUND\0")
        else:
            conn.sendall(b"stream: OK\0")

    def close(self) -> None:
        self.sock.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def clamd(monkeypatch):
    server = FakeClamd()
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", f"127.0.0.1:{server.port}")
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    yield server
    server.close()


def test_scanning_is_required_when_a_scanner_is_named_and_off_otherwise(monkeypatch):
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    monkeypatch.delenv("DEMO_MALWARE_SCANNER", raising=False)
    assert malware_scan.mode() == "off"
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", "gaik-demo-scanner:3310")
    assert malware_scan.mode() == "required"
    monkeypatch.setenv("DEMO_MALWARE_SCAN", "off")
    assert malware_scan.mode() == "off"
    monkeypatch.setenv("DEMO_MALWARE_SCAN", "anything else")
    assert malware_scan.mode() == "required"


def test_the_whole_file_reaches_the_scanner(clamd):
    data = os.urandom(150 * 1024)
    assert asyncio.run(upload_problem(".txt", b"plain text\n")) is None
    asyncio.run(malware_scan.check_upload(data))
    assert clamd.received[-1] == data


def test_each_problem_gets_its_own_status(clamd):
    assert asyncio.run(upload_problem(".pdf", PNG)).status == 415
    assert asyncio.run(upload_problem(".pdf", _pdf(b"/OpenAction " + JS_ACTION))).status == 422
    found = asyncio.run(upload_problem(".png", PNG + EICAR))
    assert found.status == 422 and "Eicar" not in found.message


def test_required_scanning_with_no_scanner_answering_refuses(monkeypatch):
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")
    problem = asyncio.run(upload_problem(".png", PNG))
    assert problem.status == 503


@pytest.mark.parametrize("reply", [b"INSTREAM size limit exceeded. ERROR\0", b"garbage\0"])
def test_an_answer_that_is_no_verdict_refuses(monkeypatch, reply):
    server = FakeClamd(reply=reply)
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", f"127.0.0.1:{server.port}")
    try:
        assert asyncio.run(upload_problem(".png", PNG)).status == 503
    finally:
        server.close()


def test_routes_with_their_own_type_rules_skip_only_the_type_check(clamd):
    assert asyncio.run(upload_problem(".anything", b"notes", check_type=False)) is None
    assert asyncio.run(upload_problem(".anything", EICAR, check_type=False)).status == 422


def test_a_file_larger_than_the_scanner_reads_is_refused(clamd, monkeypatch):
    monkeypatch.setattr(malware_scan, "MAX_SCAN_BYTES", 10)
    problem = asyncio.run(upload_problem(".anything", b"x" * 11, check_type=False))
    assert problem.status == 422 and "too large" in problem.message
    assert clamd.received == []


@pytest.mark.skipif(not os.getenv("DEMO_TEST_CLAMD"), reason="DEMO_TEST_CLAMD not set")
def test_a_real_clamd_reports_the_eicar_test_file(monkeypatch):
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", os.environ["DEMO_TEST_CLAMD"])
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    assert asyncio.run(upload_problem(".pdf", _pdf())) is None
    assert asyncio.run(upload_problem(".docx", _docx({"word/media/x.txt": EICAR}))).status == 422


# ---------------------------------------------------------------------------
# A route
# ---------------------------------------------------------------------------


@pytest.fixture
def classify(monkeypatch):
    calls: list = []

    class FakeClassifier:
        def __init__(self, config):
            pass

        def classify(self, file_or_dir, classes, parser=None):
            from pathlib import Path

            calls.append(file_or_dir)
            return {Path(file_or_dir).name: {"class": classes[0], "confidence": 1, "reasoning": ""}}

    monkeypatch.setattr(
        "gaik.software_components.doc_classifier.DocumentClassifier", FakeClassifier
    )
    monkeypatch.setattr(route, "get_api_config", lambda: {"model": "m"})
    app = FastAPI()
    app.include_router(route.router, prefix="/classify")
    client = TestClient(app)

    def post(name: str, data: bytes):
        return client.post("/classify", files={"file": (name, data)}, data={"classes": "a,b"})

    post.calls = calls  # type: ignore[attr-defined]
    return post


def test_a_route_never_hands_a_refused_file_to_the_component(classify, clamd):
    infected = classify("scan.png", PNG + EICAR)
    scripted = classify("doc.pdf", _pdf(b"/OpenAction " + JS_ACTION))
    clean = classify("scan.png", PNG)

    assert infected.status_code == 422, infected.text
    assert scripted.status_code == 422 and "JavaScript" in scripted.json()["detail"]
    assert clean.status_code == 200, clean.text
    assert len(classify.calls) == 1  # type: ignore[attr-defined]


def test_a_route_refuses_uploads_while_the_scanner_is_down(classify, monkeypatch):
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")
    res = classify("scan.png", PNG)
    assert res.status_code == 503
    assert classify.calls == []  # type: ignore[attr-defined]


def test_a_scanner_that_stops_reading_is_given_up_on_time(monkeypatch):
    # Accepts the connection and never reads, as a stuck scanner would; it hangs
    # up only after a while.
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held: list[socket.socket] = []

    def hold() -> None:
        conn, _ = server.accept()
        held.append(conn)
        time.sleep(5)
        conn.close()

    threading.Thread(target=hold, daemon=True).start()
    monkeypatch.setenv("DEMO_MALWARE_SCANNER", f"127.0.0.1:{server.getsockname()[1]}")
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    monkeypatch.setattr(malware_scan, "SCAN_TIMEOUT_SECONDS", 0.3)
    start = time.monotonic()
    with pytest.raises(malware_scan.ScannerUnavailableError):
        asyncio.run(malware_scan.check_upload(b"x" * (8 * 1024 * 1024)))
    assert time.monotonic() - start < 2.0
    server.close()


@pytest.mark.parametrize("as_sample", [False, True])
def test_the_report_writer_refuses_an_unsafe_upload_without_writing_it(
    monkeypatch, tmp_path, as_sample
):
    from api.routers import report_writer

    monkeypatch.delenv("DEMO_MALWARE_SCANNER", raising=False)
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    started: list[bool] = []
    monkeypatch.setattr(report_writer, "_run_options", lambda *a: started.append(True))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(report_writer.tempfile, "mkdtemp", lambda *a, **k: str(run_dir))
    written: list[str] = []
    real_write = report_writer.Path.write_bytes

    def write_bytes(self, data):
        written.append(self.name)
        return real_write(self, data)

    monkeypatch.setattr(report_writer.Path, "write_bytes", write_bytes)
    app = FastAPI()
    app.include_router(report_writer.router, prefix="/report-writer")
    pdf = _pdf(b"/OpenAction " + JS_ACTION)
    files = [("files", ("notes.md", b"# Notes", "text/markdown"))]
    if as_sample:
        files.append(("sample_report", ("survey.pdf", pdf, "application/pdf")))
    else:
        files.append(("files", ("survey.pdf", pdf, "application/pdf")))
    response = TestClient(app).post("/report-writer/run", data={"config": "{}"}, files=files)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("survey.pdf: PDF files that contain JavaScript")
    assert "survey.pdf" not in written
    assert not run_dir.exists()  # what was written before the refusal is removed
    assert not started


def test_a_pdf_about_pdf_syntax_passes_the_upload_check(monkeypatch):
    monkeypatch.delenv("DEMO_MALWARE_SCANNER", raising=False)
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    text = b"BT /F1 12 Tf 20 100 Td (An action: << /S /JavaScript /JS (code) >>) Tj ET"
    info = b"4 0 obj\n<< /Title (How /S /Launch actions work) >>\nendobj\n"
    pdf = _pdf(objects=info + _stream(6, b"/Filter /FlateDecode", zlib.compress(text)))
    assert asyncio.run(upload_problem(".pdf", pdf)) is None


@pytest.mark.parametrize(
    "line",
    [
        b"1" + b" " * 2_000_000 + b"obj\n",  # a long gap inside what could be a header
        b"4 0 obj\n(" + b"/S%" * 300_000 + b"\nendobj\n",  # comment marks in an open string
    ],
)
def test_the_upload_check_returns_quickly_on_a_long_header_line(monkeypatch, line):
    monkeypatch.delenv("DEMO_MALWARE_SCANNER", raising=False)
    monkeypatch.delenv("DEMO_MALWARE_SCAN", raising=False)
    start = time.monotonic()
    asyncio.run(upload_problem(".pdf", _pdf(objects=line)))
    assert time.monotonic() - start < 3.0


# ---------------------------------------------------------------------------
# Every route that takes a file checks it
# ---------------------------------------------------------------------------

ROUTERS = Path(__file__).resolve().parents[1] / "routers"
#: Routes that take an upload which is not a document, with the reason.
NOT_DOCUMENTS = {
    # A JSON object of path to text, validated against its schema; no parser
    # or viewer reads it as a file.
    "knowledge_curator.py",
}


def _takes_files(text: str) -> bool:
    """A router takes files as uploads, or as base64 it decodes (attachments)."""
    return "UploadFile" in text or "b64decode(" in text


@pytest.mark.parametrize(
    "router",
    sorted(p.name for p in ROUTERS.glob("*.py") if _takes_files(p.read_text(encoding="utf-8"))),
)
def test_every_router_that_takes_a_file_checks_it(router):
    if router in NOT_DOCUMENTS:
        pytest.skip("its upload is not a document")
    assert "upload_problem(" in (ROUTERS / router).read_text(encoding="utf-8")
