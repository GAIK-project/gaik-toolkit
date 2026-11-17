"""How the PDF check reads a file: as a viewer reads it, in bounded time.

Every file is generated here. ``check`` raises ``ActiveContentError`` for an
action a viewer would run, ``TooComplexError`` for a file it cannot read the
way a viewer does, and returns for a plain PDF.
"""

from __future__ import annotations

import base64
import time
import tracemalloc
import zlib

import pytest
from api.utils import pdf_content
from api.utils.pdf_content import ActiveContentError, TooComplexError, check

JS_ACTION = b"<< /S /JavaScript /JS (app.alert(1)) >>"


def _pdf(catalog_extra: bytes = b"", objects: bytes = b"", trailer_extra: bytes = b"") -> bytes:
    return (
        b"%PDF-1.7\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b">>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
        + objects
        + b"trailer\n<< /Root 1 0 R "
        + trailer_extra
        + b">>\n%%EOF\n"
    )


def _stream(num: int, dictionary: bytes, data: bytes) -> bytes:
    return (
        f"{num} 0 obj\n<< ".encode()
        + dictionary
        + f" /Length {len(data)} >>\nstream\n".encode()
        + data
        + b"\nendstream\nendobj\n"
    )


def _object_stream(dictionary: bytes, body: bytes, encode=zlib.compress) -> bytes:
    return _stream(9, b"/Type /ObjStm /N 1 /First 5 " + dictionary, encode(body))


OBJECTS = b"10 0 " + JS_ACTION  # one object, number 10, at offset 0 after /First 5


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
        if nxt < 4096:
            table[wc] = nxt
            nxt += 1
        # Early change, as a viewer reads it: the decoder's table is one entry
        # behind, so the width grows when this table reaches the next power of two.
        if nxt >= (1 << width) and width < 12:
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
            out_bits &= (1 << nbits) - 1
    if nbits:
        out.append((out_bits << (8 - nbits)) & 0xFF)
    return bytes(out)


def _png_up(data: bytes, columns: int) -> bytes:
    """PNG 'Up' prediction (row type 2), for the fixture only."""
    rows = [data[i : i + columns].ljust(columns, b"\0") for i in range(0, len(data), columns)]
    out, prev = bytearray(), bytes(columns)
    for row in rows:
        out += b"\x02" + bytes((a - b) & 0xFF for a, b in zip(row, prev))
        prev = row
    return bytes(out)


def _png_sub(data: bytes, rowlen: int, bpp: int) -> bytes:
    """PNG 'Sub' prediction (row type 1), for the fixture only."""
    out = bytearray()
    for i in range(0, len(data), rowlen):
        row = data[i : i + rowlen].ljust(rowlen, b"\0")
        out += b"\x01" + bytes(
            (row[j] - (row[j - bpp] if j >= bpp else 0)) & 0xFF for j in range(rowlen)
        )
    return bytes(out)


def _steps(data: bytes) -> int:
    """The steps ``check`` takes on ``data``, whether it passes or refuses it.

    The bound these tests hold is the steps, not seconds, so they do not depend
    on the machine; ``MAX_WORK`` is what keeps the time in step with them."""
    budgets = pdf_content._Budgets()
    real = pdf_content._Budgets
    pdf_content._Budgets = lambda: budgets  # type: ignore[misc,assignment]
    try:
        check(data)
    except (ActiveContentError, TooComplexError):
        pass
    finally:
        pdf_content._Budgets = real  # type: ignore[misc]
    return pdf_content.MAX_WORK - budgets.work.left


def _bounded(data: bytes) -> bool:
    """True when the check stops within ``MAX_WORK`` steps and its deadline.

    A refused file may count past ``MAX_WORK`` by the one take that refuses it
    (at most a predictor row of 1 MiB), before that work is done."""
    start = time.monotonic()
    steps = _steps(data)
    return (
        steps <= pdf_content.MAX_WORK + (1 << 20)
        and time.monotonic() - start < pdf_content.CHECK_SECONDS
    )


# ---------------------------------------------------------------- bounded time


@pytest.mark.parametrize(
    "body",
    [
        b"1" * 200_000,  # one long number
        b"9" * 15_000 + b"\nstream\nx\nendstream\n",  # a long number before a stream
        (b"1 " * 5_000 + b"stream\nx\nendstream\n") * 20,
        b"1 " * 100_000,  # many numbers
        (b"1 0 obj << /Length 9 >> stream\n" + b"x" * 30) * 3_000,
        b"stream\n" * 100_000,  # stream keywords with no dictionary or end
        b"1 0 obj << /Filter /FlateDecode >>\n" + b"stream\n" * 100_000,
        b"(" * 100_000 + b"/S /JavaScript",
        b"<" * 100_000,
        b"%" * 100_000,
        b"4 0 obj\n(" + b"/S%" * 100_000 + b"\nendobj\n",  # comment marks in an open string
        b"4 0 obj\n(" + b"/JS%1" * 60_000 + b"\nendobj\n",
        b"1" + b" " * 300_000 + b"obj\n",  # a long gap before an object keyword
    ],
)
def test_the_check_stays_within_its_steps_and_deadline_on_any_file(body):
    assert _bounded(_pdf(objects=body))


def test_an_object_stream_full_of_comment_marks_stays_within_the_steps():
    text = b"(" + b"/S%" * 100_000
    body = b"10 0 "
    hidden = _stream(
        9,
        f"/Type /ObjStm /N 1 /First {len(body)} /Filter /FlateDecode".encode(),
        zlib.compress(body + text),
    )
    assert _bounded(_pdf(objects=hidden))


def test_lzw_decoding_takes_time_in_step_with_the_stream():
    data = bytes(range(256)) * 600  # about 150 kB that compresses poorly
    encoded = _lzw_encode(data)
    budgets = pdf_content._Budgets()
    assert pdf_content._lzw(encoded, 0, budgets, {}, None) == data
    # One step for each byte read: the time is in step with the stream.
    assert pdf_content.MAX_WORK - budgets.work.left == len(encoded)


def test_a_large_compressed_stream_with_line_ends_inside_its_length_stays_within_the_steps():
    # Over a megabyte decoded, and /Length counts the line end after the data.
    content = zlib.compress(b"q 1 0 0 1 0 0 cm Q\n" * 200_000) + b"\r\n"
    assert _bounded(_pdf(objects=_stream(6, b"/Filter /FlateDecode", content)))


def test_many_compressed_streams_damaged_at_their_end_are_read_within_the_steps():
    body = bytes((i * 7919) % 251 for i in range(100_000))
    damaged = zlib.compress(body, 1)[:-4] + b"\xff\xff\xff\xff"  # a wrong checksum
    streams = b"".join(_stream(100 + i, b"/Filter /FlateDecode", damaged) for i in range(100))
    assert _bounded(_pdf(objects=streams))


def test_many_tiny_compressed_streams_stop_at_the_step_budget():
    tiny = b"1 0 obj << /Filter /Fl >> stream\nx\nendstream endobj\n" * 200_000
    with pytest.raises(TooComplexError, match="too complex"):
        check(_pdf(objects=tiny))
    assert _bounded(_pdf(objects=tiny))


def test_slow_decoders_stop_at_the_step_budget(monkeypatch):
    monkeypatch.setattr(pdf_content, "MAX_WORK", 1024)
    stream = _stream(6, b"/Filter /RunLengthDecode", b"\x00a" * 2048)
    with pytest.raises(TooComplexError, match="too complex"):
        check(_pdf(objects=stream))


@pytest.mark.parametrize(
    "body",
    [
        b"<a" * 50_000_000,  # hex string marks that open no string
        b"(a)" * 30_000_000,  # many short strings
        b"(" + b"\\(" * 50_000_000,  # escapes inside one string
        b"%\n" * 50_000_000,  # many comments
        b"/A#41" * 20_000_000,  # many escaped names
    ],
)
def test_a_small_file_that_decodes_to_much_work_stops_at_the_step_budget(body):
    # About 100 kB compressed, 100 MB decoded: the work is counted, not the bytes.
    data = _pdf(objects=_stream(6, b"/Filter /FlateDecode", zlib.compress(body, 9)))
    assert len(data) < 200_000
    with pytest.raises(TooComplexError, match="too complex"):
        check(data)


def test_predictor_rows_count_as_steps_and_as_decoded_bytes():
    rowlen = 1000
    rows = (b"\x04" + b"\x01" * rowlen) * 1_000  # Paeth rows, 1 MB
    stream = _stream(
        6,
        f"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns {rowlen} >>".encode(),
        zlib.compress(rows, 9),
    )
    data = _pdf(objects=stream)
    assert _steps(data) >= 1_000 * rowlen
    budgets = pdf_content._Budgets()
    pdf_content._png_unpredict(rows, {b"Predictor": 12, b"Columns": rowlen}, budgets)
    assert pdf_content.MAX_DECODED_BYTES - budgets.decoded.left == 1_000 * rowlen


def test_the_check_stops_at_its_deadline(monkeypatch):
    monkeypatch.setattr(pdf_content, "CHECK_SECONDS", 0.0)
    with pytest.raises(TooComplexError, match="too complex"):
        check(_pdf(objects=b"(a)" * 10_000))


def test_many_small_strings_are_checked_in_memory_in_step_with_the_file(monkeypatch):
    # Memory, not time: tracing slows the check, which a busy machine could
    # push past the deadline.
    monkeypatch.setattr(pdf_content, "CHECK_SECONDS", 600.0)
    data = _pdf(objects=b"4 0 obj\n[" + b"(a)" * 300_000 + b"]\nendobj\n")
    tracemalloc.start()
    try:
        check(data)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * len(data)


def test_the_bytes_the_patterns_read_count_as_steps():
    decoded = b"0 0 m 10 10 l S\n" * 1_000_000  # 16 MB of plain drawing
    data = _pdf(objects=_stream(6, b"/Filter /FlateDecode", zlib.compress(decoded, 9)))
    check(data)
    # Read twice at least: once to blank strings and once by the patterns.
    assert _steps(data) >= 2 * len(decoded) // pdf_content.SCAN_BYTES


@pytest.mark.parametrize("shift", range(0, 40))
def test_a_name_across_the_edge_of_a_scan_window_is_found(monkeypatch, shift):
    monkeypatch.setattr(pdf_content, "SCAN_WINDOW", 64)
    action = b"4 0 obj\n" + b" " * shift + JS_ACTION + b"\nendobj\n"
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(objects=action))


@pytest.mark.parametrize("shift", range(0, 40, 3))
def test_page_text_across_the_edge_of_a_scan_window_passes(monkeypatch, shift):
    monkeypatch.setattr(pdf_content, "SCAN_WINDOW", 64)
    content = b" " * shift + b"BT /F1 12 Tf 72 712 Td (/S /JavaScript) Tj ET /Subtype /Form"
    check(_pdf(objects=_stream(6, b"", content)))


@pytest.mark.parametrize("gap", [0, 1, 40, 63, 64, 65, 120, 3000])
@pytest.mark.parametrize(
    "first, rest",
    [
        (b"/S", b"/JavaScript"),
        (b"/S", b"/Launch"),
        (b"/JS", b"12 0 R"),
        (b"/JavaScript", b"7 0 R"),
        (b"/Subtype", b"/RichMedia"),
    ],
)
@pytest.mark.parametrize("shift", [0, 17, 40])
def test_a_finding_is_found_whatever_its_gap_and_place_in_a_window(
    monkeypatch, gap, first, rest, shift
):
    monkeypatch.setattr(pdf_content, "SCAN_WINDOW", 64)
    names = b"/S /P " * 20  # names that begin no finding, before it
    gap = max(gap, rest[:1].isdigit())  # "/JS12" would be another name
    action = b"4 0 obj\n<< " + names + b" " * shift + first + b"\n" * gap + rest + b" >>\nendobj\n"
    with pytest.raises(ActiveContentError):
        check(_pdf(objects=action))


def test_a_window_of_names_that_begin_nothing_is_not_read_name_by_name(monkeypatch):
    calls: list[int] = []
    real = pdf_content._match_at
    monkeypatch.setattr(pdf_content, "_match_at", lambda *a: calls.append(1) or real(*a))
    # A tagged document names a structure type for every element.
    elements = b"<< /Type /StructElem /S /P /P 9 0 R /K 1 >>\n" * 20_000
    check(_pdf(objects=_stream(6, b"/Filter /FlateDecode", zlib.compress(elements))))
    assert calls == []


def test_a_name_followed_by_a_long_gap_is_read_through_it(monkeypatch):
    monkeypatch.setattr(pdf_content, "MAX_GAP", 4096)
    action = b"4 0 obj\n<< /S" + b"\n" * 4000 + b"/JavaScript >>\nendobj\n"
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(objects=action))


def test_a_name_followed_by_a_gap_longer_than_the_check_reads_is_refused(monkeypatch):
    monkeypatch.setattr(pdf_content, "MAX_GAP", 4096)
    action = b"4 0 obj\n<< /S" + b" " * 5000 + b"/Normal >>\nendobj\n"
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(objects=action))


def test_a_long_offset_list_is_refused_in_memory_in_step_with_the_step_budget():
    numbers = b"1 2 " * 4_000_000  # 8 million numbers, more steps than the budget
    decoded = numbers + b"<< >>"
    stream_dict = f"/Type /ObjStm /N 4000000 /First {len(numbers)}".encode()
    tracemalloc.start()
    try:
        with pytest.raises(TooComplexError, match="too complex"):
            pdf_content._object_offsets(decoded, stream_dict, pdf_content._Work())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # At most one kept offset for two steps, eight bytes each; the whole list
    # held at once would take many times the size of the numbers.
    assert peak < 5 * pdf_content.MAX_WORK


def test_an_object_stream_lists_its_offsets_in_order():
    body = b"11 6 10 0 " + b"<< >>\n" + JS_ACTION
    offsets = pdf_content._object_offsets(body, b"/First 10", pdf_content._Work())
    assert list(offsets) == [10, 16]


# ---------------------------------------------------------------- filters


@pytest.mark.parametrize(
    "filters, encode",
    [
        (b"/Filter /LZWDecode", _lzw_encode),
        (b"/Filter /LZWDecode /DecodeParms << /EarlyChange 1 >>", _lzw_encode),
        (
            b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 8 >>",
            lambda d: zlib.compress(_png_up(d, 8)),
        ),
        (
            b"/Filter [/FlateDecode] /DecodeParms [<< /Predictor 12 /Columns 8 >>]",
            lambda d: zlib.compress(_png_up(d, 8)),
        ),
        (
            # three 4-bit colours: two bytes a pixel, as a viewer counts them
            b"/Filter /FlateDecode /DecodeParms"
            b" << /Predictor 11 /Colors 3 /BitsPerComponent 4 /Columns 4 >>",
            lambda d: zlib.compress(_png_sub(d, 6, 2)),
        ),
        (
            b"/Filter [/ASCII85Decode /FlateDecode]",
            lambda d: base64.a85encode(zlib.compress(d)) + b"~>",
        ),
        (
            # each filter has its own parameters; the predictor follows Flate
            b"/Filter [/ASCIIHexDecode /FlateDecode]"
            b" /DecodeParms [null << /Predictor 12 /Columns 8 >>]",
            lambda d: zlib.compress(_png_up(d, 8)).hex().encode() + b">",
        ),
    ],
)
def test_javascript_in_an_object_stream_is_found_through_its_decode_parameters(filters, encode):
    hidden = _object_stream(filters, OBJECTS, encode)
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize(
    "filters",
    [
        b"/Filter 8 0 R",  # the filter given by reference
        b"/Filter /SomeOtherDecode",  # a filter the check does not know
        b"/Filter /FlateDecode /Filter /ASCIIHexDecode",  # given twice
        b"/Filter [/FlateDecode null]",  # not a list of names
        b"/Filter /FlateDecode /DecodeParms 8 0 R",
        b"/Filter /FlateDecode /DecodeParms << /Predictor 2 /Columns 8 >>",
        b"/Filter [/ASCIIHexDecode /FlateDecode] /DecodeParms [<< /Predictor 12 >> null]",
        b"/Filter [/FlateDecode /LZWDecode] /DecodeParms [<< /Predictor 12 /Columns 8 >>]",
        b"/Filter [/FlateDecode /LZWDecode] /DecodeParms << /Predictor 12 /Columns 8 >>",
        b"/Filter /FlateDecode /DecodeParms [8 0 R]",  # parameters in a list, by reference
        b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 8 0 R >>",
        b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 8.0 >>",
        b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 8 /Columns 4 >>",
        b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 8 >> /DecodeParms null",
        b"/Filter /JPXDecode",  # objects read from what an image filter gives
    ],
)
def test_a_stream_whose_filters_cannot_be_read_is_refused_as_not_checkable(filters):
    # Encoded as the parameters say where they can be read, so only the way
    # they are written leads to the refusal.
    predicted = b"/Predictor 12 /Columns 8" in filters
    encode = (lambda d: zlib.compress(_png_up(d, 8))) if predicted else zlib.compress
    hidden = _object_stream(filters, OBJECTS, encode)
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_data_the_ascii85_filter_cannot_decode_is_refused_as_not_checkable():
    hidden = _object_stream(b"/Filter /ASCII85Decode", OBJECTS, lambda d: b"vwxy{|}~>")
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize(
    "dictionary",
    [b"/Filter null", b"/Filter []", b"/Filter /FlateDecode /DecodeParms null"],
)
def test_a_null_or_empty_filter_or_null_parameters_mean_none(dictionary):
    encode = zlib.compress if b"Flate" in dictionary else (lambda d: d)
    content = b"BT /F1 12 Tf 20 100 Td (plain text) Tj ET"
    check(_pdf(objects=_stream(6, dictionary, encode(content))))
    hidden = _object_stream(dictionary, OBJECTS, encode)
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_each_filter_gets_its_own_decode_parameters():
    # The EarlyChange entry belongs to Flate; LZW keeps its default. The
    # action comes after LZW's codes have grown past nine bits.
    pad = b"<" + bytes(range(256)).hex().encode() * 4 + b"> "
    table = f"11 0 10 {len(pad)} ".encode()
    hidden = _stream(
        9,
        f"/Type /ObjStm /N 2 /First {len(table)}".encode()
        + b" /Filter [/FlateDecode /LZWDecode] /DecodeParms [<< /EarlyChange 0 >> null]",
        zlib.compress(_lzw_encode(table + pad + JS_ACTION)),
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize("dictionary", [b"/Filter null", b""])
def test_an_unencoded_object_stream_is_read_through_its_offsets(dictionary):
    first = b"(an open string "
    body = f"11 0 10 {len(first)} ".encode()
    hidden = _stream(
        9,
        f"/Type /ObjStm /N 2 /First {len(body)} ".encode() + dictionary,
        body + first + JS_ACTION + b" )",
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def _flate_with_stored_start(stored: bytes, rest: bytes) -> bytes:
    """Flate data whose first block is stored as it is, for the fixture only."""
    comp = zlib.compressobj(wbits=-15)
    body = comp.compress(rest) + comp.flush()
    header = (
        b"\x00" + len(stored).to_bytes(2, "little") + (0xFFFF ^ len(stored)).to_bytes(2, "little")
    )
    adler = zlib.adler32(stored + rest).to_bytes(4, "big")
    return b"\x78\x01" + header + stored + body + adler


def test_a_compressed_stream_is_read_to_its_own_end_past_an_end_keyword_inside_it():
    # Object 11 is a string whose text holds the stream's end keyword, stored
    # as it is; object 10 follows, compressed. /Length is a reference.
    note = b"(\nendstream\n) "
    table = f"11 0 10 {len(note)} ".encode()
    data = _flate_with_stored_start(table + note, JS_ACTION)
    hidden = (
        f"9 0 obj\n<< /Type /ObjStm /N 2 /First {len(table)} /Filter /FlateDecode".encode()
        + b" /Length 8 0 R >>\nstream\n"
        + data
        + b"\nendstream\nendobj\n8 0 obj\n"
        + str(len(data)).encode()
        + b"\nendobj\n"
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_an_unencoded_object_stream_with_a_referenced_length_is_refused():
    first = b"(an open string "
    body = f"11 0 10 {len(first)} ".encode()
    hidden = (
        f"9 0 obj\n<< /Type /ObjStm /N 2 /First {len(body)} /Length 8 0 R >>\nstream\n".encode()
        + body
        + first
        + JS_ACTION
        + b" )\nendstream\nendobj\n"
    )
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_a_compressed_stream_whose_referenced_length_is_elsewhere_passes():
    # Object 8 may be in an object stream; the filter's own end is read.
    content = zlib.compress(b"BT /F1 12 Tf 20 100 Td (text) Tj ET")
    check(_pdf(objects=_stream(6, b"/Filter /FlateDecode /Length 8 0 R", content)))


def test_ascii85_data_without_its_end_marker_is_refused_as_not_checkable():
    data = base64.a85encode(zlib.compress(OBJECTS))
    hidden = _object_stream(b"/Filter [/ASCII85Decode /FlateDecode]", OBJECTS, lambda d: data)
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_a_compressed_stream_damaged_at_its_end_is_read_up_to_the_damage():
    data = zlib.compress(OBJECTS)[:-4] + b"\xff\xff\xff\xff"  # a wrong checksum
    hidden = _object_stream(b"/Filter /FlateDecode", OBJECTS, lambda d: data)
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_an_encrypted_file_with_objects_in_a_stream_without_its_type_is_refused():
    hidden = _stream(9, b"/N 1 /First 5 /Filter /FlateDecode", zlib.compress(OBJECTS))
    with pytest.raises(ActiveContentError, match="encrypted"):
        check(_pdf(objects=hidden, trailer_extra=b"/Encrypt 20 0 R"))


def test_a_stream_is_read_past_a_length_that_stops_short():
    data = zlib.compress(OBJECTS)
    hidden = (
        b"9 0 obj\n<< /Type /ObjStm /N 1 /First 5 /Filter /FlateDecode /Length 4 >>\n"
        b"stream\n" + data + b"\nendstream\nendobj\n"
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize(
    "filters",
    [
        b"/Filter /FlateDecode /DecodeParms [<< /Predictor 12 /Columns 8 >>]",
        b"/Filter [/FlateDecode] /DecodeParms << /Predictor 12 /Columns 8 >>",
    ],
)
@pytest.mark.parametrize("predicted", [True, False])
def test_parameters_in_the_other_shape_for_one_filter_are_read_both_ways(filters, predicted):
    # Whether a viewer applies the parameters or not, the action is not passed:
    # found where both ways read, refused where one way cannot be read.
    encode = (lambda d: zlib.compress(_png_up(d, 8))) if predicted else zlib.compress
    expected = ActiveContentError if predicted else TooComplexError
    with pytest.raises(expected):
        check(_pdf(b"/OpenAction 10 0 R", _object_stream(filters, OBJECTS, encode)))


def test_a_one_item_filter_list_with_a_predictor_dictionary_passes():
    rows = bytes([1, 0, 15, 0]) * 6
    xref = _stream(
        12,
        b"/Type /XRef /Size 6 /W [1 2 1] /Filter [/FlateDecode] "
        b"/DecodeParms << /Predictor 12 /Columns 4 >>",
        zlib.compress(_png_up(rows, 4)),
    )
    check(_pdf(objects=xref))


def test_many_small_streams_pass():
    content = b"BT /F1 12 Tf 20 100 Td (text) Tj ET"
    flate = b"".join(
        _stream(100 + i, b"/Filter /FlateDecode", zlib.compress(content)) for i in range(300)
    )
    lzw = b"".join(
        _stream(400 + i, b"/Filter /LZWDecode", _lzw_encode(content)) for i in range(300)
    )
    check(_pdf(objects=flate + lzw))


def test_ascii85_data_with_zero_groups_is_read_whole():
    compressed = zlib.compress(OBJECTS)
    compressed += b" " * (-len(compressed) % 4)  # whole groups, then four "z" groups
    data = base64.a85encode(compressed + b"\0" * 16 + b"A") + b"~>"
    assert data.count(b"z") == 4
    hidden = _object_stream(b"/Filter [/ASCII85Decode /FlateDecode]", OBJECTS, lambda d: data)
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


UNTERMINATED_A85 = _stream(6, b"/Filter /ASCII85Decode", base64.a85encode(JS_ACTION))


@pytest.mark.parametrize("value", [b"null", b"/Standard"])
def test_an_encrypt_entry_that_names_no_dictionary_does_not_make_the_file_encrypted(value):
    # Read as plain, data the filter cannot decode is refused.
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(objects=UNTERMINATED_A85, trailer_extra=b"/Encrypt " + value))


def test_an_encrypt_entry_in_a_string_does_not_make_the_file_encrypted():
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(objects=UNTERMINATED_A85, trailer_extra=b"/Info (/Encrypt 20 0 R)"))


def test_streams_an_encrypted_file_keeps_readable_are_still_checked():
    # Encryption that leaves streams as they are (an identity crypt filter).
    attachment = _stream(6, b"/Type /EmbeddedFile /Filter /FlateDecode", zlib.compress(JS_ACTION))
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(objects=attachment, trailer_extra=b"/Encrypt 20 0 R"))


@pytest.mark.parametrize("value", [b"0000000000000000001", b"1"])
def test_numbers_with_leading_zeros_are_read_as_written(value):
    stream = _object_stream(
        b"/Filter /FlateDecode /DecodeParms << /Predictor " + value + b" /Columns 8 >>", OBJECTS
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", stream))


def test_a_very_long_number_after_startxref_passes():
    data = _pdf() + b"startxref\n" + b"9" * 5_000 + b"\n%%EOF\n"
    check(data)


def test_a_file_of_many_small_compressed_streams_passes():
    glyph = zlib.compress(b"0 0 m 10 10 l S")
    streams = b"".join(_stream(100 + i, b"/Filter /FlateDecode", glyph) for i in range(5_000))
    check(_pdf(objects=streams))


def test_parameters_that_change_nothing_need_not_pair_with_the_filters():
    data = base64.a85encode(zlib.compress(b"BT (text) Tj ET")) + b"~>"
    stream = _stream(
        6, b"/Filter [/ASCII85Decode /FlateDecode] /DecodeParms << /Predictor 1 >>", data
    )
    check(_pdf(objects=stream))


def test_a_stream_of_an_encrypted_file_that_does_not_decode_is_taken_as_ciphertext():
    stream = _stream(6, b"/Filter /ASCII85Decode", bytes(range(256)))  # ciphertext
    check(_pdf(objects=stream, trailer_extra=b"/Encrypt 20 0 R"))


def test_an_encrypted_file_is_still_held_to_the_checks_other_limits():
    stream = _stream(
        6,
        b"/Filter /FlateDecode /DecodeParms << /Predictor 12 /Columns 9999999 >>",
        zlib.compress(b"x" * 64),
    )
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(objects=stream, trailer_extra=b"/Encrypt 20 0 R"))


def test_a_file_that_mentions_encryption_in_its_text_is_not_read_as_encrypted():
    hidden = _object_stream(b"/Filter /FlateDecode", b"10 0 << /Type /Font >>")
    info = b"4 0 obj\n<< /Title (About /Encrypt and /ObjStm) >>\nendobj\n"
    check(_pdf(objects=info + hidden))


def test_a_colour_profile_stream_with_n_but_no_first_passes():
    profile = bytes(range(256)) * 8 + b"(open"
    check(
        _pdf(
            objects=_stream(
                6, b"/N 3 /Alternate /DeviceRGB /Filter /FlateDecode", zlib.compress(profile)
            )
        )
    )


def test_the_dictionary_is_read_from_the_real_header_when_a_string_holds_another():
    # The viewer reads object 9 from its header, and "6 0 obj" is text in a string.
    hidden = _stream(
        9,
        b"/Filter /FlateDecode /Note (see 6 0 obj) /Type /ObjStm /N 1 /First 5",
        zlib.compress(OBJECTS),
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_a_long_stream_dictionary_is_read_whole():
    padding = b"/Pad [" + b"0 " * 20_000 + b"] "
    hidden = _stream(
        9,
        b"/Filter /FlateDecode " + padding + b"/Type /ObjStm /N 1 /First 5",
        zlib.compress(OBJECTS),
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_a_plain_xref_stream_with_a_png_predictor_passes():
    rows = bytes([1, 0, 15, 0]) * 6
    xref = _stream(
        12,
        b"/Type /XRef /Size 6 /W [1 2 1] /Filter /FlateDecode "
        b"/DecodeParms << /Predictor 12 /Columns 4 >>",
        zlib.compress(_png_up(rows, 4)),
    )
    check(_pdf(objects=xref))


# ---------------------------------------------------------------- text and strings


@pytest.mark.parametrize(
    "content",
    [
        b"BT /F1 12 Tf 20 100 Td (Actions are written /S /JavaScript /JS 5 0 R) Tj ET",
        b"BT /F1 12 Tf [(/S /Launch) 120 (/Subtype /RichMedia)] TJ ET",
        b"BT /F1 12 Tf <2F53202F4A617661536372697074> Tj ET % /S /JavaScript",
    ],
)
def test_page_text_that_shows_action_names_passes(content):
    compressed = _stream(6, b"/Filter /FlateDecode", zlib.compress(content))
    plain = _stream(7, b"", content)
    check(_pdf(objects=compressed))
    check(_pdf(objects=plain))


def test_a_document_about_pdf_syntax_passes():
    info = b"4 0 obj\n<< /Title (How /S /JavaScript and /S /Launch actions work) >>\nendobj\n"
    content = b"BT /F1 12 Tf 20 100 Td (An action: << /S /JavaScript /JS (code) >>) Tj ET"
    body = b"11 0 "
    in_objects = _stream(
        9,
        f"/Type /ObjStm /N 1 /First {len(body)} /Filter /FlateDecode".encode(),
        zlib.compress(body + b"<< /Title (see /S /ImportData and /Subtype /RichMedia) >>"),
    )
    check(_pdf(objects=info + _stream(6, b"/Filter /FlateDecode", zlib.compress(content))))
    check(_pdf(objects=in_objects))


def test_a_string_left_open_does_not_hide_the_next_object():
    objects = (
        b"4 0 obj\n(an open string\nendobj\n"
        b"5 0 obj\n" + JS_ACTION + b"\nendobj\n"
        b"6 0 obj\n(closing it) )\nendobj\n"
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 5 0 R", objects))


def test_a_string_left_open_in_an_object_stream_does_not_hide_the_next_object():
    first = b"(an open string "
    body = f"11 0 10 {len(first)} ".encode()
    hidden = _stream(
        9,
        f"/Type /ObjStm /N 2 /First {len(body)} /Filter /FlateDecode".encode(),
        zlib.compress(body + first + JS_ACTION),
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize(
    "dictionary, body",
    [
        (b"/First 8 0 R", b"10 0 " + JS_ACTION),  # /First by reference
        (b"/First 5 /First 6", OBJECTS),  # given twice
        (b"/First 400", OBJECTS),  # past the end of the stream
        (b"/First 5", b"10 x " + JS_ACTION),  # offsets that are not numbers
    ],
)
def test_an_object_stream_whose_offsets_cannot_be_read_is_refused(dictionary, body):
    hidden = _stream(
        9, b"/Type /ObjStm /N 1 " + dictionary + b" /Filter /FlateDecode", zlib.compress(body)
    )
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


@pytest.mark.parametrize(
    "header",
    [b"10 %note\n0 obj", b"10 0 %note\nobj"],
)
def test_an_object_header_with_a_comment_between_its_tokens_is_refused(header):
    hidden = header + b"\n<< /Type /ObjStm /N 1 /First 5 /Filter /FlateDecode >>\nstream\n"
    hidden += zlib.compress(OBJECTS) + b"\nendstream\nendobj\n"
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


def test_a_comment_line_before_a_plain_header_passes():
    check(_pdf(objects=b"% generated object 4\n4 0 obj\n<< /Type /Font >>\nendobj\n"))


def test_binary_data_with_many_percent_signs_and_few_line_ends_stays_within_the_steps():
    binary = (b"7 %" + bytes(range(14, 256))) * 2_000  # no line ends
    image = _stream(6, b"/Subtype /Image /Width 1 /Height 1 /Filter /DCTDecode", binary)
    assert _bounded(_pdf(objects=image))


# ------------------------------------------------- object stream offsets


def test_an_object_streams_offset_table_is_counted_before_it_is_held(monkeypatch):
    monkeypatch.setattr(pdf_content, "MAX_WORK", 20_000)
    monkeypatch.setattr(pdf_content, "CHECK_SECONDS", 600.0)  # the steps refuse it
    table = b"12 34 " * 200_000  # far more numbers than the steps left
    hidden = _stream(
        9,
        f"/Type /ObjStm /N 200000 /First {len(table)} /Filter /FlateDecode".encode(),
        zlib.compress(table + JS_ACTION, 9),
    )
    tracemalloc.start()
    try:
        with pytest.raises(TooComplexError, match="too complex"):
            check(_pdf(objects=hidden))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The decoded stream and its copies, not a list of its numbers (which
    # takes about 16 times the table).
    assert peak < 6 * len(table)


@pytest.mark.parametrize("chunk", [1, 2, 3, 5, 8, 13, 1000])
def test_an_offset_table_read_in_chunks_gives_every_offset(monkeypatch, chunk):
    monkeypatch.setattr(pdf_content, "_TABLE_CHUNK", chunk)
    pairs = [(10 + i, (i * 37) % 200) for i in range(40)] + [(99, 37)]  # out of order, one twice
    table = b" ".join(b"%d %d" % pair for pair in pairs) + b"\n"
    decoded = table + b"x" * 300
    offsets = pdf_content._object_offsets(
        decoded, f"/First {len(table)}".encode(), pdf_content._Work()
    )
    assert list(offsets) == sorted(len(table) + offset for _, offset in pairs)


@pytest.mark.parametrize(
    "table",
    [b"10 0 11", b"10 0 1x 5", b"10 -0"],  # odd, a token that is not a number
)
def test_an_offset_table_that_cannot_be_read_is_refused(table):
    decoded = table + b" << >>"
    with pytest.raises(TooComplexError, match="cannot be checked"):
        pdf_content._object_offsets(
            decoded, f"/First {len(table) + 1}".encode(), pdf_content._Work()
        )


# ------------------------------------------------- deadline and memory


def test_the_deadline_is_looked_at_between_scan_windows(monkeypatch):
    monkeypatch.setattr(pdf_content, "CHECK_SECONDS", -1.0)  # already past
    with pytest.raises(TooComplexError, match="too complex"):
        pdf_content._names(b"<< /Type /Catalog >>", pdf_content._Work())


def test_zlib_running_out_of_memory_is_not_read_as_damaged_data(monkeypatch):
    class OutOfMemory:
        eof = False
        unconsumed_tail = unused_data = b""

        def copy(self):
            return self

        def decompress(self, data, max_length=0):
            raise zlib.error("Error -4 while decompressing data")

    monkeypatch.setattr(pdf_content.zlib, "decompressobj", OutOfMemory)
    stream = _stream(6, b"/Filter /FlateDecode", zlib.compress(b"q Q " * 100))
    with pytest.raises(TooComplexError, match="too complex"):
        check(_pdf(objects=stream))
