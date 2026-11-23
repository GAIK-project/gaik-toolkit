"""How the PDF check reads a file: as a viewer reads it, in bounded time.

Every file is generated here. ``check`` raises ``ActiveContentError`` for an
action a viewer would run, ``TooComplexError`` for a file it cannot read the
way a viewer does, and returns for a plain PDF.
"""

from __future__ import annotations

import time
import zlib

import pytest
from wizard_api.services import pdf_content
from wizard_api.services.pdf_content import ActiveContentError, TooComplexError, check

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


def _timed(data: bytes) -> float:
    start = time.monotonic()
    try:
        check(data)
    except (ActiveContentError, TooComplexError):
        pass
    return time.monotonic() - start


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
    ],
)
def test_the_check_ends_quickly_on_any_file(body):
    assert _timed(_pdf(objects=body)) < 3.0


def test_lzw_decoding_takes_time_in_step_with_the_stream():
    data = bytes(range(256)) * 600  # about 150 kB that compresses poorly
    encoded = _lzw_encode(data)
    start = time.monotonic()
    assert pdf_content._lzw(encoded, pdf_content._Budget(10**9), {}) == data
    assert time.monotonic() - start < 2.0


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
        b"/Filter [/ASCIIHexDecode /FlateDecode] /DecodeParms [null << /Predictor 12 >>]",
    ],
)
def test_a_stream_whose_filters_cannot_be_read_is_refused_as_not_checkable(filters):
    hidden = _object_stream(filters, OBJECTS)
    with pytest.raises(TooComplexError, match="cannot be checked"):
        check(_pdf(b"/OpenAction 10 0 R", hidden))


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


def test_an_object_stream_whose_offsets_cannot_be_read_is_matched_with_its_strings():
    hidden = _stream(
        9,
        b"/Type /ObjStm /N 1 /First 8 0 R /Filter /FlateDecode",
        zlib.compress(b"(x) " + JS_ACTION),
    )
    with pytest.raises(ActiveContentError, match="JavaScript"):
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


def test_binary_data_with_many_percent_signs_and_few_line_ends_is_quick():
    binary = (b"7 %" + bytes(range(14, 256))) * 2_000  # no line ends
    image = _stream(6, b"/Subtype /Image /Width 1 /Height 1 /Filter /DCTDecode", binary)
    assert _timed(_pdf(objects=image)) < 3.0
