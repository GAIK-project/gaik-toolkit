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
not an image is decoded (Flate, LZW, ASCIIHex, ASCII85, RunLength, chained, and
PNG predictors) up to a budget for the whole file; a file over it is refused as
too complex to check. A stream whose filters cannot be read as a viewer reads
them (a filter given by reference or twice, an unknown filter, a predictor this
check does not apply) is refused as not checkable rather than skipped. A
stream's dictionary is read from each object header that leads to it, so a
header written inside a string cannot hide the real one.

Names are matched as a viewer reads them: ``#xx`` escapes are decoded and
comments between tokens are skipped (an object header that could have a
comment between its own tokens is refused as not checkable). Text inside a
string is not a name, so a document whose text shows ``/S /JavaScript`` is not
refused for it. A string ends where the next object begins (an ``N G obj`` header, or an offset an
object stream lists), because a viewer reads every object from its own start;
so a string cannot hide the object after it. An object stream whose offsets
cannot be read is matched with its strings included.

An encrypted PDF keeps its streams encrypted. Its dictionaries outside streams
are still plain, so such a file is checked as far as that goes, and refused
when it also has object streams, where the checked names could hide. A PDF with
a user password is refused by the scanner.

Every pattern runs in time linear in its input, and the bytes the check reads
more than once are counted against a budget, so the check ends quickly on any
file.
"""

from __future__ import annotations

import base64
import bisect
import re
import zlib
from collections.abc import Sequence

#: Decoded bytes the check reads from one file in all. Images are not decoded;
#: text, fonts and object streams of a 50 MB document stay far below this.
MAX_DECODED_BYTES = 256 * 1024 * 1024
#: Decoded bytes that go through a PNG predictor in all (cross-reference and
#: object streams; a few kilobytes in a normal file).
MAX_PREDICTED_BYTES = 16 * 1024 * 1024
#: Bytes of the file read more than once (stream dictionaries and stream
#: data), as a multiple of its size. A well-formed file reads each about twice.
REREAD_FACTOR = 4
_OUT_CHUNK = 1024 * 1024


class ActiveContentError(ValueError):
    """The PDF names an action or content we refuse; the message is for the person."""


class TooComplexError(ValueError):
    """The PDF decodes to more than the check reads, or cannot be checked."""


NOT_CHECKABLE = "the PDF's content cannot be checked; save it again as a standard PDF"

_DELIM = rb"\x00\t\n\x0c\r /\[\]()<>{}%"
_END = rb"(?=[" + _DELIM + rb"]|$)"
_START = rb"(?<![^" + _DELIM + rb"])"
# Whitespace and comments, which may stand between any two tokens. Possessive:
# the two alternatives start differently, so nothing is given back.
_WS = rb"(?:[\x00\t\n\x0c\r ]|%[^\r\n]*+(?:\r\n|\r|\n|$))*+"
# An integer that starts where a number starts: no backtracking into digit runs.
_INT = rb"(?<![0-9])[0-9]++"
_REF = _INT + _WS + _INT + _WS + rb"R" + _END
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
_STREAM = re.compile(rb"(?<!end)stream(?:\r\n|\n|\r)")
_ENDSTREAM = re.compile(rb"endstream")
# Object headers are found without comments between their tokens, which keeps
# the search linear; a header that could have one is refused (``_headers``).
_WS0 = rb"[\x00\t\n\x0c\r ]*+"
_OBJ = re.compile(_INT + _WS0 + _INT + _WS0 + rb"obj" + _END)
_OBJ_WORD = re.compile(_START + rb"obj" + _END)
_PERCENT = re.compile(rb"%")
_WHITE = frozenset(b"\x00\t\n\x0c\r ")
_DIGITS = frozenset(b"0123456789")
_BREAK = re.compile(_START + rb"(?:endobj|endstream|stream)" + _END)
_DICT_TOKEN = re.compile(rb"<<|>>")
_NAME = re.compile(rb"/([^" + _DELIM + rb"]*+)")
_LENGTH = re.compile(rb"/Length" + _WS + rb"([0-9]++)" + _WS + rb"(?=/|>>)")
_FILTER_KEY = re.compile(rb"/Filter" + _END)
_FILTER = re.compile(
    rb"/Filter"
    + _WS
    + rb"(\[(?:"
    + _WS
    + rb"/[^"
    + _DELIM
    + rb"]*+)*+"
    + _WS
    + rb"\]|/[^"
    + _DELIM
    + rb"]*+)"
)
_PARMS_KEY = re.compile(rb"/DecodeParms" + _END)
_PARMS_REF = re.compile(rb"/DecodeParms" + _WS + _REF)
_PARM = {
    key: re.compile(rb"/" + key + _WS + rb"([0-9]++)" + _END)
    for key in (b"Predictor", b"Columns", b"Colors", b"BitsPerComponent", b"EarlyChange")
}
_FIRST = re.compile(rb"/First" + _WS + rb"([0-9]++)" + _END)
_FIRST_KEY = re.compile(rb"/First" + _END)
_N_KEY = re.compile(rb"/N" + _END)
_IMAGE = re.compile(rb"/Subtype" + _WS + rb"/Image" + _END)
_ENCRYPT = re.compile(rb"/Encrypt" + _END)
_OBJSTM = re.compile(rb"/ObjStm" + _END)

_IMAGE_CODECS = frozenset(
    {b"DCTDecode", b"DCT", b"JPXDecode", b"CCITTFaxDecode", b"CCF", b"JBIG2Decode"}
)


def _unescape(buf: bytes) -> bytes:
    return _HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), buf) if b"#" in buf else buf


class _Budget:
    def __init__(self, limit: int) -> None:
        self.left = limit

    def take(self, n: int) -> None:
        self.left -= n
        if self.left < 0:
            raise TooComplexError("the PDF is too complex to be checked")


# ------------------------------------------------------------------ strings

_SPECIAL = re.compile(rb"[(<%]")
_IN_STRING = re.compile(rb"[()\\]")
_EOL = re.compile(rb"\r\n|\r|\n")
_HEX_STRING = re.compile(rb"<[0-9A-Fa-f\x00\t\n\x0c\r ]*+>")


def _string_end(buf: bytes, start: int, limit: int) -> int | None:
    """End of the literal string opening at ``start``; None if it is open at ``limit``."""
    depth, i = 0, start
    while (m := _IN_STRING.search(buf, i, limit)) is not None:
        c = buf[m.start()]
        if c == 0x5C:  # backslash: the next byte is taken as it is
            i = m.start() + 2
            continue
        depth += 1 if c == 0x28 else -1
        i = m.end()
        if depth == 0:
            return i
    return None


def _strip(buf: bytes, barriers: Sequence[int] = ()) -> bytes:
    """``buf`` with literal and hex strings emptied and comments blanked.

    A string or comment ends at the next of ``barriers`` (where an object
    begins), and one that is still open there keeps its text up to it as it is.
    """
    if not _SPECIAL.search(buf):
        return buf
    out: list[bytes] = []
    last = i = 0
    n = len(buf)
    while (m := _SPECIAL.search(buf, i)) is not None:
        p = m.start()
        b = bisect.bisect_right(barriers, p)
        limit = barriers[b] if b < len(barriers) else n
        c = buf[p]
        if c == 0x25:  # % comment, to the end of the line
            e = _EOL.search(buf, p, limit)
            end = e.end() if e else limit
            out += (buf[last:p], b" ")
        elif c == 0x28:  # ( literal string
            end = _string_end(buf, p, limit)
            if end is None:  # open at the barrier: kept as it is
                i = limit if limit > p else p + 1
                continue
            out += (buf[last:p], b" () ")
        elif buf[p + 1 : p + 2] == b"<":  # << dictionary
            i = p + 2
            continue
        else:  # < hex string, only when it is one
            h = _HEX_STRING.match(buf, p, limit)
            if h is None:
                i = p + 1
                continue
            end = h.end()
            out += (buf[last:p], b" <> ")
        last = i = end
    out.append(buf[last:])
    return b"".join(out)


def _strict_findings(buf: bytes) -> str | None:
    """What ``buf`` names, strings included."""
    text = _unescape(buf)
    for pattern, what in _FINDINGS:
        if pattern.search(text):
            return what
    return None


def _findings(buf: bytes, starts: Sequence[int]) -> str | None:
    """What ``buf`` names outside strings; ``starts`` are where objects begin."""
    return _strict_findings(_strip(buf, starts))


def _comment_could_precede(
    data: bytes, q: int, line_starts: list[int], percents: list[int]
) -> bool:
    """Whether a comment could stand between the tokens of a header ending in
    the ``obj`` at ``q``: a ``%`` earlier on the line those tokens end on."""
    p = q
    while p > 0 and data[p - 1] in _WHITE:
        p -= 1
    if p > 0 and data[p - 1] in _DIGITS:
        while p > 0 and data[p - 1] in _DIGITS:
            p -= 1
        while p > 0 and data[p - 1] in _WHITE:
            p -= 1
        if p > 0 and data[p - 1] in _DIGITS:
            return False  # "N G obj" with whitespace only: found by _OBJ
    if p == 0:
        return False
    line = line_starts[bisect.bisect_right(line_starts, p - 1) - 1]
    k = bisect.bisect_left(percents, line)
    return k < len(percents) and percents[k] < p


def _headers(data: bytes) -> list[re.Match[bytes]]:
    """Every object header, as (start, end); refuses a file where a header
    could have a comment between its tokens."""
    found = list(_OBJ.finditer(data))
    ends = {m.end() for m in found}
    line_starts = [0, *(m.end() for m in _EOL.finditer(data))]
    percents = [m.start() for m in _PERCENT.finditer(data)]
    for word in _OBJ_WORD.finditer(data):
        if word.end() not in ends and _comment_could_precede(
            data, word.start(), line_starts, percents
        ):
            raise TooComplexError(NOT_CHECKABLE)
    return found


# ------------------------------------------------------------------ decoders


def _flate(data: bytes, budget: _Budget, parms: dict[bytes, int]) -> bytes:
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


def _ascii_hex(data: bytes, budget: _Budget, parms: dict[bytes, int]) -> bytes:
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">", 1)[0])
    if len(digits) % 2:
        digits += b"0"
    budget.take(len(digits) // 2)
    return bytes.fromhex(digits.decode("ascii"))


def _ascii85(data: bytes, budget: _Budget, parms: dict[bytes, int]) -> bytes:
    body = data.split(b"~>", 1)[0]
    body = re.sub(rb"[\x00\t\n\x0c\r ]", b"", body)
    if body.startswith(b"<~"):
        body = body[2:]
    budget.take(len(body) * 4 + body.count(b"z") * 4)
    try:
        return base64.a85decode(body, foldspaces=False, adobe=False)
    except ValueError:
        return b""


def _run_length(data: bytes, budget: _Budget, parms: dict[bytes, int]) -> bytes:
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


def _lzw(data: bytes, budget: _Budget, parms: dict[bytes, int]) -> bytes:
    early = 0 if parms.get(b"EarlyChange") == 0 else 1
    out = bytearray()
    table: list[bytes] = [bytes([i]) for i in range(256)] + [b"", b""]
    width, bits, nbits, prev = 9, 0, 0, b""
    for byte in data:
        bits = (bits << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = bits >> nbits
            bits &= (1 << nbits) - 1  # keep only the bits not read yet
            if code == 256:
                table = table[:258]
                width, prev = 9, b""
                continue
            if code == 257:
                return bytes(out)
            if code < len(table):
                entry = table[code]
                if prev and len(table) < 4096:
                    table.append(prev + entry[:1])
            elif prev and code == len(table):
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
#: The filters a predictor may follow.
_PREDICTED = frozenset({b"FlateDecode", b"Fl", b"LZWDecode", b"LZW"})


def _png_unpredict(data: bytes, parms: dict[bytes, int], budget: _Budget) -> bytes:
    colors = parms.get(b"Colors", 1) or 1
    bpc = parms.get(b"BitsPerComponent", 8) or 8
    columns = parms.get(b"Columns", 1) or 1
    bpp = max(1, colors * bpc // 8)
    rowlen = (colors * bpc * columns + 7) // 8
    if rowlen > 1 << 20:
        raise TooComplexError(NOT_CHECKABLE)
    budget.take(len(data))
    out = bytearray()
    prev = bytearray(rowlen)
    for start in range(0, len(data), rowlen + 1):
        kind = data[start]
        row = bytearray(data[start + 1 : start + 1 + rowlen].ljust(rowlen, b"\0"))
        if kind == 1:
            for i in range(bpp, rowlen):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif kind == 2:
            row = bytearray((a + b) & 0xFF for a, b in zip(row, prev))
        elif kind == 3:
            for i in range(rowlen):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(rowlen):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pred) & 0xFF
        elif kind != 0:
            raise TooComplexError(NOT_CHECKABLE)
        out += row
        prev = row
    return bytes(out)


# ------------------------------------------------------------------ streams


def _filters(stream_dict: bytes) -> list[bytes]:
    """The filter names, as a viewer reads them; refuses what it cannot read."""
    keys = len(_FILTER_KEY.findall(stream_dict))
    if keys == 0:
        return []
    found = _FILTER.search(stream_dict)
    if keys > 1 or not found:  # given twice, by reference, or not names
        raise TooComplexError(NOT_CHECKABLE)
    return [name for name in _NAME.findall(found.group(1)) if name]


def _parms(stream_dict: bytes, filters: list[bytes]) -> dict[bytes, int]:
    """The decode parameters this check applies; refuses others."""
    if not _PARMS_KEY.search(stream_dict):
        return {}
    if _PARMS_REF.search(stream_dict):
        raise TooComplexError(NOT_CHECKABLE)
    parms = {k: int(m.group(1)) for k, rx in _PARM.items() if (m := rx.search(stream_dict))}
    predictor = parms.get(b"Predictor", 1)
    # A PNG predictor after one Flate or LZW filter is applied; a TIFF
    # predictor, or one inside a chain, is not.
    if predictor > 1 and (predictor < 10 or len(filters) != 1 or filters[0] not in _PREDICTED):
        raise TooComplexError(NOT_CHECKABLE)
    return parms


def _is_object_stream(stream_dict: bytes) -> bool:
    # A viewer reads an object stream by /N and /First, whatever its /Type says.
    return bool(_FIRST_KEY.search(stream_dict) or _N_KEY.search(stream_dict))


def _decode(
    raw: bytes,
    filters: list[bytes],
    parms: dict[bytes, int],
    budgets: tuple[_Budget, _Budget],
    encrypted: bool,
) -> bytes | None:
    budget, predicted = budgets
    data = raw
    for name in filters:
        if name in _IMAGE_CODECS:
            return None
        if name == b"Crypt" and encrypted:
            return None  # encrypted: opaque, as the rest of the file's streams
        decoder = _DECODERS.get(name)
        if decoder is None:
            raise TooComplexError(NOT_CHECKABLE)
        data = decoder(data, budget, parms)
    if parms.get(b"Predictor", 1) >= 10:
        data = _png_unpredict(data, parms, predicted)
    return data


def _object_offsets(decoded: bytes, stream_dict: bytes) -> list[int] | None:
    """Where an object stream's objects begin, as it lists them; None if unread."""
    first = _FIRST.search(stream_dict)
    if not first:
        return None
    start = int(first.group(1))
    if start > len(decoded):
        return None
    numbers = decoded[:start].split()
    if len(numbers) % 2 or not all(n.isdigit() for n in numbers):
        return None
    offsets = sorted({start + int(n) for n in numbers[1::2]})
    return [o for o in offsets if o < len(decoded)] or [start]


def _single_dict(stripped: bytes) -> bool:
    """True when ``stripped`` is one ``<< ... >>`` and nothing else."""
    body = stripped.strip(b"\x00\t\n\x0c\r ")
    if not body.startswith(b"<<") or not body.endswith(b">>"):
        return False
    depth = 0
    for m in _DICT_TOKEN.finditer(body):
        depth += 1 if m.group() == b"<<" else -1
        if depth == 0:
            return m.end() == len(body)
    return False


def _stream_dicts(data: bytes, kw: int, header_ends: list[int], reread: _Budget) -> list[bytes]:
    """Every dictionary a viewer could read for the stream keyword at ``kw``.

    From the nearest object header back: each header whose text up to ``kw``
    is a single dictionary gives one. The walk ends at a header whose text has
    an ``endobj``, ``stream`` or ``endstream`` keyword outside a dictionary,
    since no earlier header leads past it.
    """
    found: list[bytes] = []
    h = bisect.bisect_right(header_ends, kw) - 1
    while h >= 0:
        lo = header_ends[h]
        reread.take(kw - lo)
        stripped = _strip(data[lo:kw])
        if _single_dict(stripped):
            found.append(_unescape(stripped))
        elif _BREAK.search(stripped):
            break
        h -= 1
    return found


def _stream_end(data: bytes, start: int, stream_dict: bytes, stream_ends: list[int]) -> int:
    length = _LENGTH.search(stream_dict)
    if length:
        return min(len(data), start + int(length.group(1)))
    e = bisect.bisect_left(stream_ends, start)
    return stream_ends[e] if e < len(stream_ends) else len(data)


def _check_stream(
    data: bytes,
    start: int,
    stream_dict: bytes,
    stream_ends: list[int],
    budgets: tuple[_Budget, _Budget],
    reread: _Budget,
    encrypted: bool,
) -> str | None:
    objects = _is_object_stream(stream_dict)
    if not objects and _IMAGE.search(stream_dict):
        return None
    filters = _filters(stream_dict)
    if not filters:
        return None  # unencoded: already read with the file
    parms = _parms(stream_dict, filters)
    end = _stream_end(data, start, stream_dict, stream_ends)
    reread.take(end - start)
    decoded = _decode(data[start:end], filters, parms, budgets, encrypted)
    if not decoded:
        return None
    if not objects:
        return _findings(decoded, [])
    offsets = _object_offsets(decoded, stream_dict)
    return _strict_findings(decoded) if offsets is None else _findings(decoded, offsets)


def check(data: bytes) -> None:
    """Raise ``ActiveContentError`` or ``TooComplexError``; return for a plain PDF."""
    headers = _headers(data)
    what = _findings(data, [m.start() for m in headers])
    if what:
        raise ActiveContentError(f"PDF files that contain {what} are not accepted")
    plain = _unescape(data)
    encrypted = bool(_ENCRYPT.search(plain))
    if encrypted and _OBJSTM.search(plain):
        raise ActiveContentError(
            "encrypted PDF files whose content cannot be checked are not accepted; "
            "upload an unprotected copy"
        )
    budgets = (_Budget(MAX_DECODED_BYTES), _Budget(MAX_PREDICTED_BYTES))
    reread = _Budget(REREAD_FACTOR * len(data) + 1024 * 1024)
    header_ends = [m.end() for m in headers]
    stream_ends = [m.start() for m in _ENDSTREAM.finditer(data)]
    for match in _STREAM.finditer(data):
        seen: set[bytes] = set()
        for stream_dict in _stream_dicts(data, match.start(), header_ends, reread):
            if stream_dict in seen:
                continue
            seen.add(stream_dict)
            what = _check_stream(
                data, match.end(), stream_dict, stream_ends, budgets, reread, encrypted
            )
            if what:
                raise ActiveContentError(f"PDF files that contain {what} are not accepted")
