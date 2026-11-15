"""Uploads pass a malware scanner and a check of PDF actions and office macros.

The scanner here is a small fake clamd on a local port, speaking the same
INSTREAM protocol; ``test_a_real_clamd_reports_the_eicar_test_file`` runs
against a real one when ``WIZARD_TEST_CLAMD`` names it. Every PDF and office
file is generated here; the "malware" is the EICAR test string, which is not
harmful by design.
"""

from __future__ import annotations

import asyncio
import base64
import os
import socket
import struct
import threading
import zlib

import pytest
from helpers import requires_postgres
from test_input_content import SAMPLES, _case_upload, _docx, _poc_session, _zip
from wizard_api import ops_metrics
from wizard_api.services import malware_scan, pdf_content
from wizard_api.services.input_content import InvalidInputError, check

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

# ---------------------------------------------------------------------------
# PDF fixtures
# ---------------------------------------------------------------------------


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


def _object_stream(body: bytes, filters: bytes, encoded: bytes) -> bytes:
    return _stream(9, b"/Type /ObjStm /N 1 /First 4 /Filter " + filters, encoded)


_JS_ACTION = b"<< /S /JavaScript /JS (app.alert(1)) >>"


def _lzw_encode(data: bytes) -> bytes:
    """A plain LZW encoder (9-12 bit codes, early change), for the fixture only."""
    table = {bytes([i]): i for i in range(256)}
    width, nxt, out_bits, nbits = 9, 258, 0, 0
    codes: list[tuple[int, int]] = [(256, 9)]
    w = b""
    for byte in data:
        wc = w + bytes([byte])
        if wc in table:
            w = wc
            continue
        codes.append((table[w], width))
        table[wc] = nxt
        nxt += 1
        if nxt + 1 >= (1 << width) and width < 12:
            width += 1
        w = bytes([byte])
    if w:
        codes.append((table[w], width))
    codes.append((257, width))
    out = bytearray()
    for code, bits in codes:
        out_bits = (out_bits << bits) | code
        nbits += bits
        while nbits >= 8:
            nbits -= 8
            out.append((out_bits >> nbits) & 0xFF)
    if nbits:
        out.append((out_bits << (8 - nbits)) & 0xFF)
    return bytes(out)


# ---------------------------------------------------------------------------
# PDF actions
# ---------------------------------------------------------------------------


def test_a_plain_pdf_is_accepted():
    assert check("invoice.pdf", _pdf()) == "pdf"


def test_a_link_whose_address_mentions_javascript_is_accepted():
    link = b"4 0 obj\n<< /S /URI /URI (https://example.test/JavaScript/guide) >>\nendobj\n"
    assert check("guide.pdf", _pdf(objects=link)) == "pdf"


@pytest.mark.parametrize(
    "catalog, what",
    [
        (b"/OpenAction " + _JS_ACTION, "JavaScript"),
        (b"/OpenAction << /S /J#61vaScript /JS 7 0 R >>", "JavaScript"),
        (b"/OpenAction << /S %hidden\n/JavaScript /JS (x) >>", "JavaScript"),
        (b"/Names << /JavaScript 8 0 R >>", "JavaScript"),
        (b"/OpenAction << /S /Launch /F (cmd.exe) >>", "opens another file"),
        (b"/OpenAction << /S /ImportData /F (data.fdf) >>", "imports data"),
    ],
)
def test_a_pdf_with_an_action_a_viewer_would_run_is_refused(catalog, what):
    with pytest.raises(InvalidInputError, match=what):
        check("invoice.pdf", _pdf(catalog))


def test_rich_media_is_refused():
    annot = b"5 0 obj\n<< /Type /Annot /Subtype /RichMedia >>\nendobj\n"
    with pytest.raises(InvalidInputError, match="rich media"):
        check("invoice.pdf", _pdf(objects=annot))


@pytest.mark.parametrize(
    "filters, encode",
    [
        (b"/FlateDecode", zlib.compress),
        (b"/Fl", zlib.compress),
        (b"[/ASCIIHexDecode /FlateDecode]", lambda d: zlib.compress(d).hex().encode() + b">"),
        (b"[/ASCII85Decode]", lambda d: base64.a85encode(d) + b"~>"),
        (b"/LZWDecode", _lzw_encode),
        (b"/RunLengthDecode", lambda d: bytes([len(d) - 1]) + d + b"\x80"),
    ],
)
def test_javascript_inside_an_encoded_object_stream_is_found(filters, encode):
    body = b"10 0 " + _JS_ACTION
    hidden = _object_stream(body, filters, encode(body))
    with pytest.raises(InvalidInputError, match="JavaScript"):
        check("invoice.pdf", _pdf(b"/OpenAction 10 0 R", hidden))


def test_an_object_stream_dressed_as_an_image_is_still_read():
    body = b"10 0 " + _JS_ACTION
    dressed = _stream(
        9, b"/Type /ObjStm /Subtype /Image /N 1 /First 4 /Filter /FlateDecode", zlib.compress(body)
    )
    with pytest.raises(InvalidInputError, match="JavaScript"):
        check("invoice.pdf", _pdf(b"/OpenAction 10 0 R", dressed))


def test_image_data_is_not_decoded_and_cannot_raise_a_false_alarm():
    pixels = b"/S /JavaScript " * 1000  # what an image's bytes happen to hold
    image = _stream(
        6,
        b"/Type /XObject /Subtype /Image /Width 10 /Height 10 /Filter /FlateDecode",
        zlib.compress(pixels),
    )
    assert check("scan.pdf", _pdf(objects=image)) == "pdf"


def test_a_pdf_that_decodes_past_the_budget_is_refused(monkeypatch):
    monkeypatch.setattr(pdf_content, "MAX_DECODED_BYTES", 1024)
    big = _stream(6, b"/Filter /FlateDecode", zlib.compress(b"q 0 0 m Q\n" * 500))
    with pytest.raises(InvalidInputError, match="too complex"):
        check("report.pdf", _pdf(objects=big))


def test_an_encrypted_pdf_with_object_streams_is_refused():
    enc = b"/Encrypt 20 0 R"
    objstm = _stream(9, b"/Type /ObjStm /N 1 /First 4 /Filter /FlateDecode", b"\x00" * 16)
    data = _pdf(objects=objstm).replace(b"/Root 1 0 R", b"/Root 1 0 R " + enc)
    with pytest.raises(InvalidInputError, match="encrypted"):
        check("invoice.pdf", data)


def test_an_encrypted_pdf_without_object_streams_is_checked_and_accepted():
    data = _pdf().replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 20 0 R")
    assert check("invoice.pdf", data) == "pdf"


# ---------------------------------------------------------------------------
# Office macros
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, data",
    [
        ("letter.docx", _docx({"word/vbaProject.bin": b"\xd0\xcf\x11\xe0"})),
        ("letter.docx", _docx({"word/activeX/activeX1.bin": b"\xd0\xcf\x11\xe0"})),
        (
            "sheet.xlsx",
            _zip(
                {
                    "[Content_Types].xml": b'<Types><Override ContentType="application/'
                    b'vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>',
                    "xl/workbook.xml": b"<workbook/>",
                }
            ),
        ),
    ],
)
def test_an_office_file_with_macros_is_refused(name, data):
    with pytest.raises(InvalidInputError, match="macros"):
        check(name, data)


def test_an_office_file_without_macros_is_accepted():
    assert check(*SAMPLES["docx"]) == "docx"
    assert check(*SAMPLES["xlsx"]) == "xlsx"


# ---------------------------------------------------------------------------
# The scanner client
# ---------------------------------------------------------------------------


class FakeClamd:
    """Answers INSTREAM like clamd: FOUND for the EICAR string, OK otherwise."""

    def __init__(self, reply: bytes | None = None, drop: bool = False) -> None:
        self.reply = reply
        self.drop = drop
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
        command, _, rest = buf.partition(b"\0")
        if command == b"zPING":
            conn.sendall(b"PONG\0")
            return
        if command == b"zVERSION":
            conn.sendall(b"ClamAV 1.4.6/28184/Sun Nov 15 06:27:28 2026\0")
            return
        if self.drop:
            return
        data, buf = b"", rest
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


@pytest.fixture
def clamd(monkeypatch):
    server = FakeClamd()
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{server.port}")
    monkeypatch.delenv("WIZARD_MALWARE_SCAN", raising=False)
    yield server
    server.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_scanning_is_required_when_a_scanner_is_named_and_off_otherwise(monkeypatch):
    monkeypatch.delenv("WIZARD_MALWARE_SCAN", raising=False)
    monkeypatch.delenv("WIZARD_MALWARE_SCANNER", raising=False)
    assert malware_scan.mode() == "off"
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", "scanner:3310")
    assert malware_scan.mode() == "required"
    assert malware_scan.scanner_address() == ("scanner", 3310)
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "off")
    assert malware_scan.mode() == "off"
    # Anything but "off" fails closed.
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "yes please")
    assert malware_scan.mode() == "required"


def test_a_clean_file_passes_and_the_whole_file_reaches_the_scanner(clamd):
    data = os.urandom(200 * 1024)
    asyncio.run(malware_scan.check_upload(data))
    assert clamd.received == [data]


def test_a_reported_file_is_refused_with_our_own_words(clamd):
    with pytest.raises(malware_scan.UnsafeInputError) as raised:
        asyncio.run(malware_scan.check_upload(b"notes " + EICAR))
    assert str(raised.value) == "the file was refused by the malware check"
    assert raised.value.signature == "Eicar-Test-Signature"


@pytest.mark.parametrize(
    "signature, words",
    [
        ("Heuristics.OLE2.ContainsMacros.VBA", "macros"),
        ("Heuristics.Encrypted.PDF", "password-protected"),
        ("Heuristics.Limits.Exceeded.MaxScanSize", "too large"),
        ("Win.Trojan.Agent-1", "refused by the malware check"),
    ],
)
def test_each_kind_of_report_has_its_own_message(signature, words):
    assert words in malware_scan.refusal_message(signature)


def test_required_scanning_with_no_scanner_listening_refuses_the_upload(monkeypatch):
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")
    with pytest.raises(malware_scan.ScannerUnavailableError):
        asyncio.run(malware_scan.check_upload(b"hello"))


def test_required_scanning_with_no_scanner_named_refuses_the_upload(monkeypatch):
    monkeypatch.delenv("WIZARD_MALWARE_SCANNER", raising=False)
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "required")
    with pytest.raises(malware_scan.ScannerUnavailableError):
        asyncio.run(malware_scan.check_upload(b"hello"))


@pytest.mark.parametrize("reply", [b"INSTREAM size limit exceeded. ERROR\0", b"\0", b"garbage\0"])
def test_an_answer_that_is_no_verdict_refuses_the_upload(monkeypatch, reply):
    server = FakeClamd(reply=reply)
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{server.port}")
    try:
        with pytest.raises(malware_scan.ScannerUnavailableError):
            asyncio.run(malware_scan.check_upload(b"hello"))
    finally:
        server.close()


def test_a_scanner_that_hangs_up_refuses_the_upload(monkeypatch):
    server = FakeClamd(drop=True)
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{server.port}")
    try:
        with pytest.raises(malware_scan.ScannerUnavailableError):
            asyncio.run(malware_scan.check_upload(b"hello"))
    finally:
        server.close()


def test_scanning_off_does_not_contact_anything(monkeypatch):
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "off")
    asyncio.run(malware_scan.check_upload(EICAR))


def test_the_probe_reads_the_signature_date(clamd):
    state = malware_scan.probe()
    assert state is not None and state.up
    assert state.signatures_time == 1794724048.0  # 2026-11-15 06:27:28 UTC


def test_the_probe_reports_a_scanner_that_does_not_answer(monkeypatch):
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")
    assert malware_scan.probe(timeout=0.5) == malware_scan.ScannerState(False, None)


def test_the_scan_results_and_refusal_codes_are_primed_for_the_alerts():
    assert {"result": "refused"} in ops_metrics._PRIMED["uploads_scanned"]
    codes = {attrs["code"] for attrs in ops_metrics._PRIMED["refusals"]}
    assert {"input_unsafe", "scanner_unavailable"} <= codes


def test_the_gauges_show_whether_uploads_are_scanned(monkeypatch):
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "off")
    assert list(ops_metrics._malware_scan()) == [(0.0, {})]
    monkeypatch.setenv("WIZARD_MALWARE_SCAN", "required")
    assert list(ops_metrics._malware_scan()) == [(1.0, {})]


@pytest.mark.skipif(not os.getenv("WIZARD_TEST_CLAMD"), reason="WIZARD_TEST_CLAMD not set")
def test_a_real_clamd_reports_the_eicar_test_file(monkeypatch):
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", os.environ["WIZARD_TEST_CLAMD"])
    monkeypatch.delenv("WIZARD_MALWARE_SCAN", raising=False)
    asyncio.run(malware_scan.check_upload(SAMPLES["pdf"][1]))
    with pytest.raises(malware_scan.UnsafeInputError):
        asyncio.run(malware_scan.check_upload(_docx({"word/media/x.txt": EICAR})))


# ---------------------------------------------------------------------------
# The upload endpoints
# ---------------------------------------------------------------------------


@requires_postgres
def test_a_case_input_the_scanner_reports_is_not_stored(client, db_session, clamd):
    url, folder = _case_upload(client, db_session, ["text"])

    res = client.post(url, files={"file": ("notes.txt", b"notes " + EICAR, "text/plain")})
    ok = client.post(url, files={"file": ("plain.txt", b"plain notes\n", "text/plain")})

    assert res.status_code == 422, res.text
    assert res.json()["detail"]["error"] == "input_unsafe"
    assert "Eicar" not in res.text  # the signature stays in the log
    assert not (folder / "notes.txt").exists()
    assert ok.status_code == 201, ok.text


@requires_postgres
def test_a_case_input_is_not_stored_while_the_scanner_is_down(client, db_session, monkeypatch):
    url, folder = _case_upload(client, db_session, ["text"])
    monkeypatch.setenv("WIZARD_MALWARE_SCANNER", f"127.0.0.1:{_free_port()}")

    res = client.post(url, files={"file": ("notes.txt", b"plain notes\n", "text/plain")})

    assert res.status_code == 503, res.text
    assert res.json()["detail"]["error"] == "scanner_unavailable"
    assert not (folder / "notes.txt").exists()


@requires_postgres
def test_a_poc_sample_input_gets_the_same_scan(client, db_session, clamd):
    url, folder = _poc_session(client, db_session, ["text"])

    res = client.post(url, files={"file": ("notes.txt", b"notes " + EICAR, "text/plain")})

    assert res.status_code == 422 and res.json()["detail"]["error"] == "input_unsafe"
    assert "notes.txt" not in os.listdir(folder)


@requires_postgres
def test_a_pdf_with_javascript_never_reaches_the_scanner(client, db_session, clamd):
    url, folder = _case_upload(client, db_session, ["pdf"])

    res = client.post(url, files={"file": ("x.pdf", _pdf(b"/OpenAction " + _JS_ACTION))})

    assert res.status_code == 422 and res.json()["detail"]["error"] == "input_unsafe"
    assert "JavaScript" in res.json()["detail"]["message"]
    assert clamd.received == []
