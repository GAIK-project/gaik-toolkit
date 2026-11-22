"""PDF files that carry actions a viewer would run are refused.

ClamAV (``malware_scan``) reports known malware but passes a PDF that runs
JavaScript when it is opened. Nothing in the demo runs a PDF's actions (gaik's
parsers read text and images), but some routes hand the file back to the
browser, so a PDF that names any of these is refused:

- a JavaScript action (``/S /JavaScript``), a ``/JS`` script or the document's
  ``/JavaScript`` name tree
- a launch action (``/S /Launch``), which opens another file or program
- an import-data action (``/S /ImportData``)
- rich media (``/Subtype /RichMedia``), embedded Flash or video with scripts

Where the names may be: in the file as written, and inside its streams, since
PDF 1.5 keeps most objects in compressed object streams. Every stream that is
not an image is decoded (Flate, LZW, ASCIIHex, ASCII85, RunLength, chained, and
PNG predictors) up to a budget for the whole file; a file over it is refused as
too complex to check. ``/Filter null`` and ``/DecodeParms null`` mean none,
and an object stream is read through its offsets with or without a filter;
each filter gets its own entry of a ``/DecodeParms`` list. A stream whose
filters cannot be read as a viewer reads them (a filter, a decode parameter or
an object stream's ``/First`` given by reference, twice or not as a plain
number, parameters that do not pair with the filters, an unknown filter, a
predictor this check does not apply, an image filter on an object stream, data
a filter cannot decode, an object stream whose offsets cannot be read) is
refused as not checkable rather than skipped. Each filter reads to its own
end of data, as a viewer's does, whatever ``/Length`` says; an unencoded object
stream is read to the furthest of its ``/Length`` and the next ``endstream``
(refused when its ``/Length`` is a reference). A stream's dictionary is read
from each object header that leads to it, so a header written inside a string
cannot hide the real one.

Names are matched as a viewer reads them: ``#xx`` escapes are decoded and
comments between tokens are skipped (an object header that could have a
comment between its own tokens is refused as not checkable). Text inside a
string is not a name, so a document whose text shows ``/S /JavaScript`` is not
refused for it. A string ends where the next object begins (an ``N G obj``
header, or an offset an object stream lists), because a viewer reads every
object from its own start; so a string cannot hide the object after it. The
text of a string still open there is matched twice, once with ``%`` read as a
comment and once as text.

A PDF that names an /Encrypt dictionary outside its strings is read as
encrypted. Its streams are still decoded, and one whose data does not decode
with its filter (or that names a crypt filter) is taken as ciphertext rather
than refused; the check's other limits still apply. Its dictionaries outside streams are plain,
so such a file is checked as far as that goes, and refused when it also has
object streams (``/ObjStm``, or any stream with ``/First``), where the checked
names could hide. A PDF with a user password is refused by the scanner.

Comments are blanked before any pattern runs, so every pattern runs in time
linear in its input. The bytes the check reads more than once, the bytes it
decodes and the streams it decodes are counted against budgets, and positions
are kept in compact arrays, so the check holds bounded memory on any file.
The steps of the check's own loops (each string and comment it blanks, each
byte the LZW, RunLength and predictor code reads, each stream it decodes, each
offset of an object stream) are counted against one more budget, and so are
the bytes its patterns read. The patterns read a window at a time and the
check looks at its deadline between windows, so it ends in bounded time on any
file and any machine, and no single search keeps other threads waiting long.
A name followed by more than ``MAX_GAP`` bytes of whitespace and digits is
refused as not checkable.

Those budgets are the first line. The upload check runs ``check`` in a process
of its own (``pdf_process``), which runs this file as a script and is stopped
at a deadline of its own, so not even a check that outruns its budgets can
hold the API's interpreter.
"""

from __future__ import annotations

import base64
import bisect
import itertools
import json
import operator
import os
import re
import sys
import time
import zlib
from array import array
from collections.abc import Sequence

#: Decoded bytes the check reads from one file in all. Images are not decoded;
#: the text, fonts and object streams of a 20 MB text document stay far below
#: this, and so do most vector drawings (path data compresses about 7:1). One
#: check holds a few times its largest stream in memory at its peak, so this is
#: half of the Solution Wizard's budget.
MAX_DECODED_BYTES = 128 * 1024 * 1024
#: Steps of the check's own Python loops in one file: each string, comment or
#: ``#xx`` escape it reads outside the patterns, each byte the LZW, RunLength
#: and PNG predictor code reads, each object header it walks, each offset of an
#: object stream, and each ``SCAN_BYTES`` the patterns read. A step takes about
#: a microsecond, a few on a slow machine.
MAX_WORK = 4_000_000
#: Bytes the patterns read for one step.
SCAN_BYTES = 1024
#: Bytes one pattern search reads before the check counts them and looks at
#: its deadline, so no single search runs long.
SCAN_WINDOW = 256 * 1024
#: Whitespace and digits read after a name to see what follows it; a name
#: followed by more is refused as not checkable.
MAX_GAP = 1024 * 1024
#: The steps a decoded stream costs besides its bytes.
STREAM_STEPS = 100
#: Seconds one check may take whatever its steps; a file that needs more is
#: refused as too complex. The steps bound a normal machine well below this.
CHECK_SECONDS = 15.0
#: Bytes of the file read more than once (stream dictionaries and stream
#: data), as a multiple of its size. A well-formed file reads each about twice.
REREAD_FACTOR = 4
_OUT_CHUNK = 1024 * 1024
_IN_CHUNK = 64 * 1024
#: Output one trial decode of a damaged Flate piece may give.
_MAX_TRIAL_BYTES = 16 * 1024 * 1024
#: Streams the check decodes in one file (each way of reading one counts).
#: A stream costs time however few bytes it reads.
MAX_DECODED_STREAMS = 100_000


class ActiveContentError(ValueError):
    """The PDF names an action or content we refuse; the message is for the person."""


class TooComplexError(ValueError):
    """The PDF decodes to more than the check reads, or cannot be checked."""


NOT_CHECKABLE = "the PDF's content cannot be checked; save it again as a standard PDF"
TOO_COMPLEX = "the PDF is too complex to be checked"


class _UndecodableError(TooComplexError):
    """A stream's data does not decode with its filter (as ciphertext does not)."""


ENCRYPTED_OBJECTS = (
    "encrypted PDF files whose content cannot be checked are not accepted; "
    "upload an unprotected copy"
)

_DELIM = rb"\x00\t\n\x0c\r /\[\]()<>{}%"
_END = rb"(?=[" + _DELIM + rb"]|$)"
_START = rb"(?<![^" + _DELIM + rb"])"
# Whitespace between tokens. Comments, which may stand there too, are blanked
# before any pattern runs (``_strip``), so a pattern never reads one.
_WS = rb"[\x00\t\n\x0c\r ]*+"
# An integer that starts where a number starts: no backtracking into digit runs.
_INT = rb"(?<![0-9])[0-9]++"
_REF = _INT + _WS + _INT + _WS + rb"R" + _END
_REF_OR_VALUE = rb"(?:<<|[(<\[]|" + _REF + rb")"

_FINDINGS: tuple[tuple[re.Pattern[bytes], str], ...] = (
    (re.compile(rb"/S" + _WS + rb"/JavaScript" + _END), "JavaScript"),
    (re.compile(rb"/JS" + _END + _WS + _REF_OR_VALUE), "JavaScript"),
    (
        re.compile(rb"/JavaScript" + _END + _WS + rb"(?:<<|" + _REF + rb")"),
        "JavaScript",
    ),
    (re.compile(rb"/S" + _WS + rb"/Launch" + _END), "an action that opens another file"),
    (re.compile(rb"/S" + _WS + rb"/ImportData" + _END), "an action that imports data"),
    (re.compile(rb"/Subtype" + _WS + rb"/RichMedia" + _END), "embedded rich media"),
)
# Every pattern above starts with one of these names, so it is tried only where
# one stands. Each name is short, so a search for them is read a window at a
# time; what follows a name is whitespace and digits (``_GAP``) and then at most
# ``_TAIL`` bytes.
_FIRST_NAMES = (b"S", b"JS", b"JavaScript", b"Subtype")
_CANDIDATE = re.compile(rb"/(" + b"|".join(_FIRST_NAMES) + rb")" + _END)
_BY_NAME = {
    name: tuple(
        f
        for f in _FINDINGS
        if re.match(rb"/([A-Za-z]+)", f[0].pattern).group(1) == name  # type: ignore[union-attr]
    )
    for name in _FIRST_NAMES
}
_CANDIDATE_OVERLAP = 16
_GAP = re.compile(rb"[\x00\t\n\x0c\r 0-9]*+")
_TAIL = 16
# A quick look at a window before its names are read one at a time (``_quiet``):
# any finding, and a first name followed by a gap longer than the look reads.
_ANY_FINDING = re.compile(b"|".join(b"(?:" + p.pattern + b")" for p, _ in _FINDINGS))
_QUICK_GAP = 64
_LONG_GAP = re.compile(_CANDIDATE.pattern + rb"[\x00\t\n\x0c\r 0-9]{" + b"%d" % _QUICK_GAP + rb"}")
#: How far past a window the quick look reads: the longest first name, a gap
#: shorter than ``_QUICK_GAP``, and the rest of a finding after its gap.
_QUICK_REACH = len(b"/JavaScript") + _QUICK_GAP + _TAIL + 1

_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_STREAM = re.compile(rb"(?<!end)stream(?:\r\n|\n|\r)")
_ENDSTREAM = re.compile(rb"endstream")
# Object headers are found without comments between their tokens, which keeps
# the search linear; a header that could have one is refused (``_headers``).
_OBJ = re.compile(_INT + _WS + _INT + _WS + rb"obj" + _END)
_OBJ_WORD = re.compile(_START + rb"obj" + _END)
_PERCENT = re.compile(rb"%")
_WHITE = frozenset(b"\x00\t\n\x0c\r ")
_DIGITS = frozenset(b"0123456789")
_BREAK = re.compile(_START + rb"(?:endobj|endstream|stream)" + _END)
_DICT_TOKEN = re.compile(rb"<<|>>")
_NAME = re.compile(rb"/([^" + _DELIM + rb"]*+)")
_LENGTH = re.compile(rb"/Length" + _WS + rb"([0-9]++)" + _WS + rb"(?=/|>>)")
_LENGTH_REF = re.compile(rb"/Length" + _WS + _REF)
_FILTER_KEY = re.compile(rb"/Filter" + _END)
_NULL = rb"null" + _END
_FILTER_NULL = re.compile(rb"/Filter" + _WS + _NULL)
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
# The value a viewer reads: null, one dictionary of plain values, or a list of
# them (one per filter). Anything else (a reference, a nested value) is refused.
_PARMS_DICT = rb"<<[^<>]*+>>"
_PARMS_ENTRY_RX = _NULL + rb"|" + _PARMS_DICT
_PARMS_ENTRY = re.compile(_PARMS_ENTRY_RX)
_PARMS = re.compile(
    rb"/DecodeParms"
    + _WS
    + rb"("
    + _PARMS_ENTRY_RX
    + rb"|\[(?:"
    + _WS
    + rb"(?:"
    + _PARMS_ENTRY_RX
    + rb"))*+"
    + _WS
    + rb"\])"
)
_REF_RX = re.compile(_REF)
_NOT_REF = rb"(?!" + _WS + _INT + _WS + rb"R" + _END + rb")"
_PARM_KEYS = (b"Predictor", b"Columns", b"Colors", b"BitsPerComponent", b"EarlyChange")
# References in the value are refused before these run.
_PARM = {
    key: (re.compile(rb"/" + key + _END), re.compile(rb"/" + key + _WS + rb"([0-9]++)" + _END))
    for key in _PARM_KEYS
}
_FIRST = re.compile(rb"/First" + _WS + rb"([0-9]++)" + _END + _NOT_REF)
_FIRST_KEY = re.compile(rb"/First" + _END)
_IMAGE = re.compile(rb"/Subtype" + _WS + rb"/Image" + _END)
# The trailer's /Encrypt names a dictionary; the name alone, or null, does not.
_ENCRYPT = re.compile(rb"/Encrypt" + _WS + rb"(?:<<|" + _REF + rb")")
_OBJSTM = re.compile(rb"/ObjStm" + _END)

_IMAGE_CODECS = frozenset(
    {b"DCTDecode", b"DCT", b"JPXDecode", b"CCITTFaxDecode", b"CCF", b"JBIG2Decode"}
)


def _unescape(buf: bytes, work: _Budget) -> bytes:
    if b"#" not in buf:
        return buf
    work.take(buf.count(b"#"))
    return _HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), buf)


class _Budget:
    def __init__(self, limit: int) -> None:
        self.left = limit

    def take(self, n: int) -> None:
        self.left -= n
        if self.left < 0:
            raise TooComplexError(TOO_COMPLEX)

    def tick(self) -> None:
        """Stop here when time is up; a plain budget has no deadline."""


class _Work(_Budget):
    """The steps the check takes, and its deadline."""

    def __init__(self) -> None:
        super().__init__(MAX_WORK)
        self.deadline = time.monotonic() + CHECK_SECONDS
        self.clock = 0

    def take(self, n: int) -> None:
        super().take(n)
        self.clock += n
        if self.clock >= 1024:
            self.clock = 0
            self.tick()

    def tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise TooComplexError(TOO_COMPLEX)


class _Budgets:
    def __init__(self, work: _Work | None = None) -> None:
        self.decoded = _Budget(MAX_DECODED_BYTES)
        self.work = work if work is not None else _Work()
        self.streams = _Budget(MAX_DECODED_STREAMS)


def _num(digits: bytes) -> int:
    """A number written in the file; a longer run than any offset or length
    reads as one past every file, so a viewer's limits never come into it."""
    digits = digits.lstrip(b"0") or b"0"
    return int(digits) if len(digits) <= 18 else 10**18


def _count(pattern: re.Pattern[bytes], text: bytes) -> int:
    """How often ``pattern`` occurs in ``text``: 0, 1, or 2 for twice or more.
    No list of the matches is built, however many there are."""
    return sum(1 for _ in itertools.islice(pattern.finditer(text), 2))


# ------------------------------------------------------------------ strings

_SPECIAL = re.compile(rb"[(<%]")
_IN_STRING = re.compile(rb"[()\\]")
_EOL = re.compile(rb"\r\n|\r|\n")
_LINE_END = re.compile(rb"[\r\n]")
_HEX_STRING = re.compile(rb"<[0-9A-Fa-f\x00\t\n\x0c\r ]*+>")
_COMMENT = re.compile(rb"%[^\r\n]*+")


def _search_byte(
    pattern: re.Pattern[bytes], buf: bytes, i: int, work: _Budget, limit: int | None = None
) -> re.Match[bytes] | None:
    """``pattern`` (one byte long) searched from ``i`` a window at a time: a
    step for the match and one for each ``SCAN_BYTES`` read before it."""
    n = len(buf) if limit is None else limit
    while i < n:
        end = min(n, i + SCAN_WINDOW)
        m = pattern.search(buf, i, end)
        work.take(1 + ((m.start() if m else end) - i) // SCAN_BYTES)
        if m is not None:
            return m
        i = end
    return None


def _string_end(buf: bytes, start: int, limit: int, work: _Budget) -> int | None:
    """End of the literal string opening at ``start``; None if it is open at ``limit``."""
    depth, i = 0, start
    while (m := _search_byte(_IN_STRING, buf, i, work, limit)) is not None:
        c = buf[m.start()]
        if c == 0x5C:  # backslash: the next byte is taken as it is
            i = m.start() + 2
            continue
        depth += 1 if c == 0x28 else -1
        i = m.end()
        if depth == 0:
            return i
    return None


def _strip(
    buf: bytes,
    work: _Budget,
    barriers: Sequence[int] = (),
    open_text: list[bytes] | None = None,
) -> bytes:
    """``buf`` with literal and hex strings emptied and comments blanked.

    A string or comment ends at the next of ``barriers`` (where an object
    begins). A string still open there keeps its text up to it, with each
    ``%`` read as text; when ``open_text`` is given, that text is also added
    to it with each ``%`` read as a comment, so the patterns read both. No
    ``%`` is left in what is returned.
    """
    n = len(buf)
    first = _search_byte(_SPECIAL, buf, 0, work)
    if first is None:
        return buf
    view = memoryview(buf)
    out = bytearray()
    last, i = 0, first.start()
    while (m := _search_byte(_SPECIAL, buf, i, work)) is not None:
        p = m.start()
        b = bisect.bisect_right(barriers, p)
        limit = barriers[b] if b < len(barriers) else n
        c = buf[p]
        if c == 0x25:  # % comment, to the end of the line
            # The line end itself is kept, as whitespace.
            e = _search_byte(_LINE_END, buf, p, work, limit)
            end = e.start() if e else limit
            out += view[last:p]
            out += b" "
        elif c == 0x28:  # ( literal string
            end = _string_end(buf, p, limit, work)
            if end is None:  # open at the barrier: its text is kept
                out += view[last:p]
                text = buf[p:limit]
                if b"%" in text:
                    if open_text is not None:
                        open_text.append(_COMMENT.sub(b" ", text))
                    text = text.replace(b"%", b" ")
                out += text
                last = i = limit if limit > p else p + 1
                continue
            out += view[last:p]
            out += b" () "
        elif buf[p + 1 : p + 2] == b"<":  # << dictionary
            i = p + 2
            continue
        else:  # < hex string, only when it is one
            h = _HEX_STRING.match(buf, p, limit)
            if h is None:
                i = p + 1
                continue
            end = h.end()
            work.take((end - p) // SCAN_BYTES)
            out += view[last:p]
            out += b" <> "
        last = i = end
    out += view[last:]
    view.release()
    return bytes(out)


def _names(stripped: bytes, work: _Budget, open_text: Sequence[bytes] = ()) -> str | None:
    """What ``stripped`` and ``open_text`` (from ``_strip``) name."""
    for text in (stripped, *open_text):
        what = _scan(_unescape(text, work), work)
        if what:
            return what
    return None


def _scan(text: bytes, work: _Budget) -> str | None:
    """What ``text`` names, read a window at a time: each window's bytes count
    as steps, and the deadline is looked at between windows."""
    n = len(text)
    pos, last = 0, -1
    while pos < n:
        end = min(n, pos + SCAN_WINDOW)
        work.take(1 + (end - pos) // SCAN_BYTES)
        work.tick()
        for m in () if _quiet(text, pos, end, work) else _CANDIDATE.finditer(text, pos, end):
            if m.end() == end < n:
                break  # its end is the window's: read again with the next one
            if m.start() <= last:
                continue  # read with the window before
            last = m.start()
            work.take(1)
            what = _match_at(text, m, work)
            if what:
                return what
        if end == n:
            break
        # The next window overlaps this one, so a name across its end is read.
        pos = end - _CANDIDATE_OVERLAP
    return None


def _quiet(text: bytes, pos: int, end: int, work: _Budget) -> bool:
    """True when no name in ``text[pos:end]`` can begin a finding, so its names
    need not be read one at a time: no finding begins there, and no first name
    there is followed by more whitespace and digits than this look reads past
    the window. Both searches run in C over the window and ``_QUICK_REACH``
    bytes past it, and count as steps for the bytes they read."""
    reach = min(len(text), end + _QUICK_REACH)
    work.take(2 * ((reach - pos) // SCAN_BYTES))
    found = _ANY_FINDING.search(text, pos, reach)
    if found is not None and found.start() < end:
        return False
    long_gap = _LONG_GAP.search(text, pos, reach)
    return long_gap is None or long_gap.start() >= end


def _match_at(text: bytes, name: re.Match[bytes], work: _Budget) -> str | None:
    """What the patterns that start with ``name`` find there."""
    n, start, name_end = len(text), name.start(), name.end()
    limit = min(n, name_end + MAX_GAP)
    gap = _GAP.match(text, name_end, limit).end()  # type: ignore[union-attr]
    work.take((gap - name_end) // SCAN_BYTES)
    if gap == limit < n:
        raise TooComplexError(NOT_CHECKABLE)
    stop = min(n, gap + _TAIL)
    for pattern, what in _BY_NAME[name.group(1)]:
        if pattern.match(text, start, stop):
            return what
    return None


def _findings(buf: bytes, starts: Sequence[int], work: _Budget) -> str | None:
    """What ``buf`` names outside strings; ``starts`` are where objects begin."""
    open_text: list[bytes] = []
    return _names(_strip(buf, work, starts, open_text), work, open_text)


def _comment_could_precede(
    data: bytes, q: int, line_starts: Sequence[int], percents: Sequence[int]
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


def _headers(data: bytes, work: _Budget) -> tuple[array[int], array[int]]:
    """Where every object header starts and ends; refuses a file where a header
    could have a comment between its tokens."""
    starts, ends = array("q"), array("q")
    for m in _OBJ.finditer(data):
        work.take(1)
        starts.append(m.start())
        ends.append(m.end())
    line_starts: array[int] | None = None
    percents: array[int] | None = None
    for word in _OBJ_WORD.finditer(data):
        work.take(1)
        e = bisect.bisect_left(ends, word.end())
        if e < len(ends) and ends[e] == word.end():
            continue
        if line_starts is None or percents is None:
            # Only a file with text such as "obj" outside a header needs these.
            line_starts = array("q", [0])
            line_starts.extend(m.end() for m in _EOL.finditer(data))
            percents = array("q", (m.start() for m in _PERCENT.finditer(data)))
        if _comment_could_precede(data, word.start(), line_starts, percents):
            raise TooComplexError(NOT_CHECKABLE)
    return starts, ends


# ------------------------------------------------------------------ decoders
#
# Each decoder reads ``data`` from ``start`` and stops at its own end of data
# (or at the end of ``data``), as a viewer's does whatever /Length says. The
# first filter of a stream reads the file itself; ``raw`` counts what it reads.


def _take(raw: _Budget | None, n: int) -> None:
    if raw is not None:
        raw.take(n)


def _out_of_memory(exc: zlib.error) -> None:
    """Refuse when zlib could not allocate (Z_MEM_ERROR, -4): that is no
    damage in the data, which may decode with memory to spare, so reading
    only what came before it could miss the rest."""
    if str(exc).startswith("Error -4 "):
        raise TooComplexError(TOO_COMPLEX) from exc


def _flate(
    data: bytes, start: int, budgets: _Budgets, parms: dict[bytes, int], raw: _Budget | None
) -> bytes:
    src = memoryview(data)
    decomp = zlib.decompressobj()
    out = bytearray()
    pos, n = start, len(data)
    try:
        while not decomp.eof:
            if decomp.unconsumed_tail:
                chunk: bytes | memoryview = decomp.unconsumed_tail
            elif pos < n:
                chunk = src[pos : pos + _IN_CHUNK]
                pos += len(chunk)
            else:
                break
            budgets.work.take(1)
            saved = decomp.copy()
            try:
                piece = decomp.decompress(chunk, _OUT_CHUNK)
            except zlib.error as exc:
                _out_of_memory(exc)
                # Damaged here: what decodes before the damage is still read,
                # as a viewer that keeps a damaged stream's start reads it.
                _keep_until_damage(saved, bytes(chunk), budgets, out)
                break
            budgets.decoded.take(len(piece))
            out += piece
            if not piece and len(decomp.unconsumed_tail) == len(chunk):
                break  # no progress
    except zlib.error as exc:
        _out_of_memory(exc)
    consumed = pos - start - len(decomp.unconsumed_tail) - len(decomp.unused_data)
    _take(raw, max(consumed, 0))
    return bytes(out)


def _drain(decomp: zlib._Decompress, chunk: bytes, budget: _Budget, out: bytearray | None) -> None:
    """Decompress all of ``chunk``, counting the output; raises at damage."""
    piece = decomp.decompress(chunk, _OUT_CHUNK)
    while True:
        budget.take(len(piece))
        if out is not None:
            out += piece
        if decomp.eof or not decomp.unconsumed_tail:
            return
        piece = decomp.decompress(decomp.unconsumed_tail, _OUT_CHUNK)


def _keep_until_damage(
    decomp: zlib._Decompress, chunk: bytes, budgets: _Budgets, out: bytearray
) -> None:
    """Add the output of the longest start of ``chunk`` that decodes, found by
    doubling and then halving: a few trial passes, fewer when the damage is
    near the start."""

    def decodes(size: int) -> bool:
        # A trial's output is not kept or counted, only bounded; its input
        # counts as steps, a step for each 4 kB.
        budgets.work.take(1 + size // 4096)
        trial = _Budget(min(budgets.decoded.left, _MAX_TRIAL_BYTES))
        try:
            _drain(decomp.copy(), chunk[:size], trial, None)
        except zlib.error as exc:
            _out_of_memory(exc)
            return False
        return True

    lo, hi, size = 0, len(chunk), 1  # chunk[:lo] decodes; chunk[:hi] does not
    while size < hi:
        if not decodes(size):
            hi = size
            break
        lo, size = size, size * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if decodes(mid):
            lo = mid
        else:
            hi = mid
    try:
        _drain(decomp, chunk[:lo], budgets.decoded, out)
    except zlib.error as exc:
        _out_of_memory(exc)


def _until(data: bytes, start: int, marker: bytes, raw: _Budget | None) -> bytes:
    end = data.find(marker, start)
    end = len(data) if end < 0 else end
    _take(raw, end - start)
    return data[start:end]


def _ascii_hex(
    data: bytes, start: int, budgets: _Budgets, parms: dict[bytes, int], raw: _Budget | None
) -> bytes:
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", _until(data, start, b">", raw))
    if len(digits) % 2:
        digits += b"0"
    budgets.decoded.take(len(digits) // 2)
    return bytes.fromhex(digits.decode("ascii"))


_A85_PREFIX = re.compile(_WS + rb"(?:<~)?")
_A85_RUN = re.compile(rb"[!-uz\x00\t\n\x0c\r ]*+")


def _ascii85(
    data: bytes, start: int, budgets: _Budgets, parms: dict[bytes, int], raw: _Budget | None
) -> bytes:
    begin = _A85_PREFIX.match(data, start).end()  # type: ignore[union-attr]
    end = _A85_RUN.match(data, begin).end()  # type: ignore[union-attr]
    _take(raw, end - start)
    if data[end : end + 1] != b"~":
        # Not ended by "~>": what a viewer reads past the data, or makes of a
        # byte that cannot be in it, is not known here.
        raise _UndecodableError(NOT_CHECKABLE)
    body = re.sub(rb"[\x00\t\n\x0c\r ]", b"", data[begin:end])
    if (len(body) - body.count(b"z")) % 5 == 1:  # a "z" stands for a whole group
        body = body[:-1]  # a lone last character holds no byte
    budgets.decoded.take(len(body) * 4 + body.count(b"z") * 4)
    try:
        return base64.a85decode(body, foldspaces=False, adobe=False)
    except ValueError:
        # A viewer reads such data its own way; what it reads is not known here.
        raise _UndecodableError(NOT_CHECKABLE) from None


def _run_length(
    data: bytes, start: int, budgets: _Budgets, parms: dict[bytes, int], raw: _Budget | None
) -> bytes:
    out = bytearray()
    i = counted = start
    while i < len(data):
        if i - counted >= _IN_CHUNK:  # what was read, counted a chunk at a time
            budgets.work.take(i - counted)
            _take(raw, i - counted)
            counted = i
        n = data[i]
        if n == 128:
            i += 1
            break
        if n < 128:
            piece = data[i + 1 : i + 2 + n]
            i += 2 + n
        else:
            piece = data[i + 1 : i + 2] * (257 - n)
            i += 2
        budgets.decoded.take(len(piece))
        out += piece
    i = min(i, len(data))
    budgets.work.take(i - counted)
    _take(raw, i - counted)
    return bytes(out)


def _lzw(
    data: bytes, start: int, budgets: _Budgets, parms: dict[bytes, int], raw: _Budget | None
) -> bytes:
    early = 0 if parms.get(b"EarlyChange") == 0 else 1
    src = memoryview(data)
    out = bytearray()
    table: list[bytes] = [bytes([i]) for i in range(256)] + [b"", b""]
    width, bits, nbits, prev = 9, 0, 0, b""
    for offset in range(start, len(data), _IN_CHUNK):
        chunk = src[offset : offset + _IN_CHUNK]
        for k, byte in enumerate(chunk):
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
                if code == 257 or not (code <= len(table) and (prev or code < len(table))):
                    # the end of data, or a code no table holds: a viewer stops
                    budgets.work.take(k + 1)
                    _take(raw, k + 1)
                    return bytes(out)
                if code < len(table):
                    entry = table[code]
                    if prev and len(table) < 4096:
                        table.append(prev + entry[:1])
                else:
                    entry = prev + prev[:1]
                    table.append(entry)
                budgets.decoded.take(len(entry))
                out += entry
                prev = entry
                if len(table) + early >= (1 << width) and width < 12:
                    width += 1
        budgets.work.take(len(chunk))  # a whole chunk read, counted after it
        _take(raw, len(chunk))
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


def _png_unpredict(data: bytes, parms: dict[bytes, int], budgets: _Budgets) -> bytes:
    colors = parms.get(b"Colors", 1) or 1
    bpc = parms.get(b"BitsPerComponent", 8) or 8
    columns = parms.get(b"Columns", 1) or 1
    bpp = (colors * bpc + 7) // 8  # bytes per pixel, at least one, as a viewer counts
    rowlen = (colors * bpc * columns + 7) // 8
    if rowlen > 1 << 20:
        raise TooComplexError(NOT_CHECKABLE)
    out = bytearray()
    prev = bytearray(rowlen)
    for start in range(0, len(data), rowlen + 1):
        kind = data[start]
        # The rows are rebuilt a byte at a time in Python: each byte is a step,
        # and the output counts as decoded.
        budgets.work.take(rowlen if kind else 1)
        budgets.decoded.take(rowlen)
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


def _filters(stream_dict: bytes) -> tuple[list[bytes], bool]:
    """The filter names, as a viewer reads them, and whether they were given
    as a list; refuses what it cannot read."""
    keys = _count(_FILTER_KEY, stream_dict)
    if keys == 0:
        return [], False
    if keys == 1 and _FILTER_NULL.search(stream_dict):
        return [], False  # null: no filter
    found = _FILTER.search(stream_dict)
    if keys > 1 or not found:  # given twice, by reference, or not names
        raise TooComplexError(NOT_CHECKABLE)
    value = found.group(1)
    return [name for name in _NAME.findall(value) if name], value.startswith(b"[")


def _read_parms(entry: bytes) -> dict[bytes, int]:
    """One filter's parameters; refuses one given twice or not as a plain number."""
    parms: dict[bytes, int] = {}
    for key, (key_rx, value_rx) in _PARM.items():
        count = _count(key_rx, entry)
        if count == 0:
            continue
        m = value_rx.search(entry)
        if count > 1 or m is None:
            raise TooComplexError(NOT_CHECKABLE)
        parms[key] = _num(m.group(1))
    return parms


def _changes_decoding(parms: dict[bytes, int]) -> bool:
    return parms.get(b"Predictor", 1) > 1 or parms.get(b"EarlyChange", 1) != 1


def _parms(stream_dict: bytes, filters: list[bytes], listed: bool) -> list[list[dict[bytes, int]]]:
    """The ways viewers read the decode parameters: each a list with one entry
    per filter, in the filters' order. Refuses parameters this check cannot
    pair or apply."""
    none: list[dict[bytes, int]] = [{} for _ in filters]
    keys = _count(_PARMS_KEY, stream_dict)
    if keys == 0:
        return [none]
    if keys > 1:
        raise TooComplexError(NOT_CHECKABLE)
    found = _PARMS.search(stream_dict)
    if not found or _REF_RX.search(found.group(1)):
        raise TooComplexError(NOT_CHECKABLE)
    value = found.group(1)
    as_list = value.startswith(b"[")
    if as_list:
        entries = [_read_parms(m.group()) for m in _PARMS_ENTRY.finditer(value)]
    else:
        entries = [_read_parms(value)]
    if as_list != listed and len(entries) == len(filters) == 1:
        # One filter with its parameters in the other shape: some viewers
        # apply them and some do not, so the data is read both ways.
        ways = [entries, none] if _changes_decoding(entries[0]) else [none]
    elif as_list != listed or len(entries) != len(filters):
        # Viewers pair such parameters differently; harmless only when none
        # of them changes how the data decodes.
        if any(_changes_decoding(e) for e in entries):
            raise TooComplexError(NOT_CHECKABLE)
        ways = [none]
    else:
        ways = [entries]
    for way in ways:
        for name, parms in zip(filters, way):
            predictor = parms.get(b"Predictor", 1)
            # A PNG predictor after a Flate or LZW filter is applied; a TIFF
            # predictor, or one after another filter, is not.
            if predictor > 1 and (predictor < 10 or name not in _PREDICTED):
                raise TooComplexError(NOT_CHECKABLE)
    return ways


def _is_object_stream(stream_dict: bytes) -> bool:
    # A viewer reads objects from a stream by its /First, whatever its /Type
    # says; without one (an ICC profile has /N) it reads none.
    return bool(_FIRST_KEY.search(stream_dict))


def _decode(
    data: bytes,
    start: int,
    filters: list[bytes],
    parms: list[dict[bytes, int]],
    budgets: _Budgets,
    reread: _Budget,
) -> bytes:
    """The stream at ``start`` through its filters; the first reads the file."""
    out, at, raw = data, start, reread
    for name, own in zip(filters, parms):
        decoder = _DECODERS.get(name)
        if decoder is None:  # an unknown filter, or a crypt filter
            raise _UndecodableError(NOT_CHECKABLE)
        out = decoder(out, at, budgets, own, raw)
        at, raw = 0, None
        if own.get(b"Predictor", 1) >= 10:
            out = _png_unpredict(out, own, budgets)
    return out


#: Where ``bytes.split()`` splits; an offset table is cut there into chunks.
_SPLIT_AT = re.compile(rb"[\t\n\x0b\x0c\r ]")
_TABLE_CHUNK = 64 * 1024


def _object_offsets(decoded: bytes, stream_dict: bytes, work: _Budget) -> Sequence[int]:
    """Where an object stream's objects begin, as it lists them, in order.

    Refuses a stream whose ``/First`` or offset list cannot be read: a viewer
    reads its objects from them, so its strings cannot be told from its names.
    An offset past the end names no object a viewer could read, and is dropped.
    The list is read a chunk at a time, each number a step, and only the
    offsets are kept, in an array: a list too long to check is refused before
    it is held.
    """
    first = _FIRST.search(stream_dict)
    if not first or _count(_FIRST_KEY, stream_dict) > 1:
        raise TooComplexError(NOT_CHECKABLE)
    start = _num(first.group(1))
    if start > len(decoded):
        raise TooComplexError(NOT_CHECKABLE)
    offsets: array[int] = array("q")
    numbers = pos = 0
    while pos < start:
        cut = _SPLIT_AT.search(decoded, min(pos + _TABLE_CHUNK, start), start)
        end = cut.end() if cut else start
        tokens = decoded[pos:end].split()
        work.take(len(tokens) + (end - pos) // SCAN_BYTES)
        if not all(map(bytes.isdigit, tokens)):
            raise TooComplexError(NOT_CHECKABLE)
        # Object numbers and offsets alternate; a chunk may begin with either.
        for token in tokens[1 - numbers % 2 :: 2]:
            offset = start + _num(token)
            if offset < len(decoded):
                offsets.append(offset)
        numbers += len(tokens)
        pos = end
    if numbers % 2:
        raise TooComplexError(NOT_CHECKABLE)
    if not all(map(operator.lt, offsets, itertools.islice(offsets, 1, None))):
        work.take(2 * len(offsets))  # sorting them
        offsets = array("q", sorted(offsets))
    return offsets or array("q", [start])


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


def _stream_dicts(
    data: bytes, kw: int, header_ends: Sequence[int], reread: _Budget, work: _Budget
) -> list[bytes]:
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
        work.take(1)
        stripped = _strip(data[lo:kw], work)
        if _single_dict(stripped):
            found.append(_unescape(stripped, work))
        elif _BREAK.search(stripped):
            break
        h -= 1
    return found


def _unencoded_end(data: bytes, start: int, stream_dict: bytes, stream_ends: Sequence[int]) -> int:
    """Where an unencoded stream ends: the furthest of its ``/Length`` and the
    next ``endstream``, as a viewer reads one whose length is wrong. Refuses a
    ``/Length`` given by reference, which could reach past an ``endstream``."""
    if _LENGTH_REF.search(stream_dict):
        raise TooComplexError(NOT_CHECKABLE)
    e = bisect.bisect_left(stream_ends, start)
    end = stream_ends[e] if e < len(stream_ends) else len(data)
    for m in _LENGTH.finditer(stream_dict):
        end = max(end, min(len(data), start + _num(m.group(1))))
    return end


def _check_stream(
    data: bytes,
    start: int,
    stream_dict: bytes,
    stream_ends: Sequence[int],
    budgets: _Budgets,
    reread: _Budget,
    encrypted: bool,
) -> str | None:
    objects = _is_object_stream(stream_dict)
    if objects and encrypted:
        raise ActiveContentError(ENCRYPTED_OBJECTS)
    if not objects and _IMAGE.search(stream_dict):
        return None  # images are not read
    filters, listed = _filters(stream_dict)
    if not filters:
        if not objects:
            return None  # unencoded: already read with the file
        end = _unencoded_end(data, start, stream_dict, stream_ends)
        reread.take(end - start)
        return _read_decoded(data[start:end], objects, stream_dict, budgets.work)
    if any(name in _IMAGE_CODECS for name in filters):
        if objects:  # a viewer would read objects from what the image filter gives
            raise TooComplexError(NOT_CHECKABLE)
        return None  # image data, read by a viewer as pixels
    # Read every way a viewer may read it; a way this check cannot read is
    # refused, since a viewer may still read something from it.
    for parms in _parms(stream_dict, filters, listed):
        budgets.streams.take(1)
        budgets.work.take(STREAM_STEPS)
        try:
            decoded = _decode(data, start, filters, parms, budgets, reread)
            what = _read_decoded(decoded, objects, stream_dict, budgets.work)
        except _UndecodableError:
            if encrypted:
                continue  # ciphertext: data that does not decode is opaque
            raise
        if what:
            return what
    return None


def _read_decoded(decoded: bytes, objects: bool, stream_dict: bytes, work: _Budget) -> str | None:
    if not decoded:
        return None
    if not objects:
        return _findings(decoded, (), work)
    return _findings(decoded, _object_offsets(decoded, stream_dict, work), work)


def check(data: bytes) -> None:
    """Raise ``ActiveContentError`` or ``TooComplexError``; return for a plain PDF."""
    budgets = _Budgets()
    work = budgets.work
    header_starts, header_ends = _headers(data, work)
    open_text: list[bytes] = []
    stripped = _strip(data, work, header_starts, open_text)
    what = _names(stripped, work, open_text)
    if what:
        raise ActiveContentError(f"PDF files that contain {what} are not accepted")
    plain = _unescape(stripped, work)  # names outside strings and comments
    # Read as encrypted when an /Encrypt dictionary is named outside strings,
    # wherever it is: a stream that then does not decode is taken as ciphertext.
    encrypted = bool(_ENCRYPT.search(plain))
    if encrypted and _OBJSTM.search(plain):
        raise ActiveContentError(ENCRYPTED_OBJECTS)
    del stripped, plain, open_text
    reread = _Budget(REREAD_FACTOR * len(data) + 1024 * 1024)
    stream_ends = array("q", (m.start() for m in _ENDSTREAM.finditer(data)))
    for match in _STREAM.finditer(data):
        work.take(1)
        seen: set[bytes] = set()
        for stream_dict in _stream_dicts(data, match.start(), header_ends, reread, work):
            if stream_dict in seen:
                continue
            seen.add(stream_dict)
            what = _check_stream(
                data, match.end(), stream_dict, stream_ends, budgets, reread, encrypted
            )
            if what:
                raise ActiveContentError(f"PDF files that contain {what} are not accepted")


# ------------------------------------------------------------------ own process
#
# ``pdf_process`` runs this file as a script (``python -I -S pdf_content.py
# <memory>``), a new process for each file, and reads its outcome.


#: Starts each line the check's process writes to stderr about a limit it could
#: not set; ``pdf_process`` logs those lines.
LIMIT_NOTICE = "PDF check process: "


def _limit_process(memory: int) -> None:
    """At most ``memory`` bytes of address space and a lower priority than the
    API's, where the system sets them for a process (Linux). Windows has neither,
    and macOS may refuse the memory cap; there nothing caps the memory of the
    check's process. Its budgets bound most of its work but not every step, so a
    hard file can take much memory before ``pdf_process`` stops the process at
    its deadline. A limit the system refuses is said on stderr, as the process
    then runs without it."""
    try:
        import resource
    except ImportError:
        return
    if memory > 0:
        try:
            _, hard = resource.getrlimit(resource.RLIMIT_AS)
            soft = memory if hard == resource.RLIM_INFINITY else min(memory, hard)
            resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
        except (ValueError, OSError) as exc:
            _say(f"no memory cap ({type(exc).__name__}: {exc})")
    try:
        os.nice(10)
    except OSError as exc:
        _say(f"no lower priority ({type(exc).__name__}: {exc})")


def _say(problem: str) -> None:
    """One line on stderr; stdout carries only the outcome."""
    sys.stderr.write(f"{LIMIT_NOTICE}{problem}\n")
    sys.stderr.flush()


def _serve() -> None:
    """One PDF on stdin, its outcome as one JSON object on stdout."""
    _limit_process(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    data = sys.stdin.buffer.read()
    if not data:
        return  # a spare process the API no longer needs
    try:
        check(data)
        outcome = {"outcome": "pass", "message": ""}
    except ActiveContentError as exc:
        outcome = {"outcome": "active", "message": str(exc)}
    except TooComplexError as exc:
        outcome = {"outcome": "complex", "message": str(exc)}
    except MemoryError:
        outcome = {"outcome": "complex", "message": TOO_COMPLEX}
    sys.stdout.write(json.dumps(outcome))
    sys.stdout.flush()


if __name__ == "__main__":
    _serve()
