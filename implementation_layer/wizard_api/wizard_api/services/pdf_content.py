"""PDF files that carry actions a viewer would run are refused.

ClamAV (``malware_scan``) reports known malware but passes a PDF that runs
JavaScript when it is opened. Nothing in the wizard runs a PDF's actions (the
parsers read text and images), but the file is also handed to the sandbox run's
parsers and downloaded again by the person, so a PDF that names any of these is
refused:

- a JavaScript action (``/S /JavaScript``), a ``/JS`` script or the document's
  ``/JavaScript`` name tree
- a launch action (``/S /Launch``), which opens another file or program
- an import-data action (``/S /ImportData``)
- rich media (``/Subtype /RichMedia``), embedded Flash or video with scripts

Where the names may be: in the file as written, and inside its streams, since
PDF 1.5 keeps most objects in compressed object streams. Every stream that is
not an image is decoded (Flate, LZW, ASCIIHex, ASCII85, RunLength, chained) up
to a budget for the whole file; a file over it is refused as too complex to
check. Names written with ``#xx`` escapes and comments between tokens are read
as a viewer reads them.

An encrypted PDF keeps its streams encrypted. Its dictionaries outside streams
are still plain, so such a file is checked as far as that goes, and refused
when it also has object streams, where the checked names could hide. A PDF with
a user password is refused by the scanner.
"""

from __future__ import annotations

import base64
import re
import zlib

#: Decoded bytes the check reads from one file in all. Images are not decoded;
#: text, fonts and object streams of a 50 MB document stay far below this.
MAX_DECODED_BYTES = 256 * 1024 * 1024
_OUT_CHUNK = 1024 * 1024
#: How far back from a stream's data its dictionary may start.
_DICT_LOOKBACK = 16 * 1024


class ActiveContentError(ValueError):
    """The PDF names an action or content we refuse; the message is for the person."""


class TooComplexError(ValueError):
    """The PDF decodes to more than the check reads."""


_DELIM = rb"\x00\t\n\x0c\r /\[\]()<>{}%"
_END = rb"(?=[" + _DELIM + rb"]|$)"
# Whitespace and comments, which may stand between any two tokens.
_WS = rb"(?:[\x00\t\n\x0c\r ]|%[^\r\n]*(?:\r\n|\r|\n|$))*"
_REF = rb"\d+" + _WS + rb"\d+" + _WS + rb"R" + _END
_REF_OR_VALUE = rb"(?:<<|[(<\[]|" + _REF + rb")"

_FINDINGS: tuple[tuple[re.Pattern[bytes], str], ...] = (
    (re.compile(rb"/S" + _WS + rb"/JavaScript" + _END), "JavaScript"),
    (re.compile(rb"/JS" + _WS + _REF_OR_VALUE), "JavaScript"),
    (
        re.compile(rb"/JavaScript" + _WS + rb"(?:<<|" + _REF + rb")"),
        "JavaScript",
    ),
    (re.compile(rb"/S" + _WS + rb"/Launch" + _END), "an action that opens another file"),
    (re.compile(rb"/S" + _WS + rb"/ImportData" + _END), "an action that imports data"),
    (re.compile(rb"/Subtype" + _WS + rb"/RichMedia" + _END), "embedded rich media"),
)

_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_STREAM = re.compile(rb"stream(?:\r\n|\n|\r)")
_OBJ = re.compile(rb"\d+" + _WS + rb"\d+" + _WS + rb"obj" + _END)
_NAME = re.compile(rb"/([^" + _DELIM + rb"]*)")
_LENGTH = re.compile(rb"/Length" + _WS + rb"(\d+)" + _WS + rb"(?=/|>>)")
_FILTER = re.compile(rb"/Filter" + _WS + rb"(\[[^\]]*\]|/[^" + _DELIM + rb"]*)")

_IMAGE_CODECS = frozenset(
    {b"DCTDecode", b"DCT", b"JPXDecode", b"CCITTFaxDecode", b"CCF", b"JBIG2Decode"}
)


def _unescape(buf: bytes) -> bytes:
    return _HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), buf) if b"#" in buf else buf


def _findings(buf: bytes) -> str | None:
    text = _unescape(buf)
    for pattern, what in _FINDINGS:
        if pattern.search(text):
            return what
    return None


class _Budget:
    def __init__(self) -> None:
        self.left = MAX_DECODED_BYTES

    def take(self, n: int) -> None:
        self.left -= n
        if self.left < 0:
            raise TooComplexError("the PDF is too complex to be checked")


# ------------------------------------------------------------------ decoders


def _flate(data: bytes, budget: _Budget) -> bytes:
    decomp = zlib.decompressobj()
    out = bytearray()
    try:
        piece = decomp.decompress(data, _OUT_CHUNK)
        while True:
            budget.take(len(piece))
            out += piece
            if not decomp.unconsumed_tail:
                break
            piece = decomp.decompress(decomp.unconsumed_tail, _OUT_CHUNK)
    except zlib.error:
        pass  # what decoded before the damage is still read
    return bytes(out)


def _ascii_hex(data: bytes, budget: _Budget) -> bytes:
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">", 1)[0])
    if len(digits) % 2:
        digits += b"0"
    budget.take(len(digits) // 2)
    return bytes.fromhex(digits.decode("ascii"))


def _ascii85(data: bytes, budget: _Budget) -> bytes:
    body = data.split(b"~>", 1)[0]
    body = re.sub(rb"[\x00\t\n\x0c\r ]", b"", body)
    if body.startswith(b"<~"):
        body = body[2:]
    budget.take(len(body) * 4 + body.count(b"z") * 4)
    try:
        return base64.a85decode(body, foldspaces=False, adobe=False)
    except ValueError:
        return b""


def _run_length(data: bytes, budget: _Budget) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        n = data[i]
        if n == 128:
            break
        if n < 128:
            piece = data[i + 1 : i + 2 + n]
            i += 2 + n
        else:
            piece = data[i + 1 : i + 2] * (257 - n)
            i += 2
        budget.take(len(piece))
        out += piece
    return bytes(out)


def _lzw(data: bytes, budget: _Budget, early: int = 1) -> bytes:
    out = bytearray()
    table: list[bytes] = [bytes([i]) for i in range(256)] + [b"", b""]
    width, bits, nbits, prev = 9, 0, 0, b""
    for byte in data:
        bits = (bits << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = (bits >> nbits) & ((1 << width) - 1)
            if code == 256:
                table = table[:258]
                width, prev = 9, b""
                continue
            if code == 257:
                return bytes(out)
            if code < len(table):
                entry = table[code]
                if prev:
                    table.append(prev + entry[:1])
            elif prev:
                entry = prev + prev[:1]
                table.append(entry)
            else:
                return bytes(out)
            budget.take(len(entry))
            out += entry
            prev = entry
            if len(table) + early >= (1 << width) and width < 12:
                width += 1
    return bytes(out)


_DECODERS = {
    b"FlateDecode": _flate,
    b"Fl": _flate,
    b"ASCIIHexDecode": _ascii_hex,
    b"AHx": _ascii_hex,
    b"ASCII85Decode": _ascii85,
    b"A85": _ascii85,
    b"RunLengthDecode": _run_length,
    b"RL": _run_length,
    b"LZWDecode": _lzw,
    b"LZW": _lzw,
}


# ------------------------------------------------------------------ streams


def _stream_dict(data: bytes, start: int) -> bytes:
    """The bytes between the stream's ``N G obj`` and its ``stream`` keyword."""
    window = data[max(0, start - _DICT_LOOKBACK) : start]
    last = None
    for last in _OBJ.finditer(window):
        pass
    return window[last.end() :] if last else window


def _filters(stream_dict: bytes) -> list[bytes]:
    found = _FILTER.search(stream_dict)
    if not found:
        return []
    return [name for name in _NAME.findall(found.group(1)) if name]


def _is_image(stream_dict: bytes) -> bool:
    # An object stream is decoded whatever else its dictionary claims: a viewer
    # reads it by /N and /First, which no image has.
    if re.search(rb"/First" + _END, stream_dict) or re.search(rb"/N" + _WS + rb"\d", stream_dict):
        return False
    return bool(re.search(rb"/Subtype" + _WS + rb"/Image" + _END, stream_dict))


def _decode(raw: bytes, filters: list[bytes], budget: _Budget) -> bytes | None:
    data = raw
    for name in filters:
        if name in _IMAGE_CODECS:
            return None
        decoder = _DECODERS.get(name)
        if decoder is None:  # Crypt or a filter we do not know: opaque to us
            return None
        data = decoder(data, budget)
    return data


def _streams(data: bytes):
    """Each stream's dictionary and raw data, in file order."""
    for match in _STREAM.finditer(data):
        start = match.end()
        stream_dict = _unescape(_stream_dict(data, match.start()))
        length = _LENGTH.search(stream_dict)
        end = data.find(b"endstream", start)
        if length:
            end = min(len(data), start + int(length.group(1)))
        elif end < 0:
            end = len(data)
        yield stream_dict, data[start:end]


def check(data: bytes) -> None:
    """Raise ``ActiveContentError`` or ``TooComplexError``; return for a plain PDF."""
    what = _findings(data)
    if what:
        raise ActiveContentError(f"PDF files that contain {what} are not accepted")
    plain = _unescape(data)
    if re.search(rb"/Encrypt" + _END, plain) and re.search(rb"/ObjStm" + _END, plain):
        raise ActiveContentError(
            "encrypted PDF files whose content cannot be checked are not accepted; "
            "upload an unprotected copy"
        )
    budget = _Budget()
    for stream_dict, raw in _streams(data):
        if _is_image(_unescape(stream_dict)):
            continue
        filters = [_unescape(f) for f in _filters(stream_dict)]
        if not filters:
            continue  # unencoded: already read with the file
        decoded = _decode(raw, filters, budget)
        if decoded:
            what = _findings(decoded)
            if what:
                raise ActiveContentError(f"PDF files that contain {what} are not accepted")
