"""Find the passage a reviewer edit's ``search`` string means, in bounded time.

A reviewer copies its ``search`` from the draft, but not always letter for letter: a
curly quote, a double space, a changed case or a typo. :func:`locate` finds the one
passage of the text such a search means, or says why it cannot:

1. the search as it is, when it occurs exactly once;
2. the search with case, quote and dash styles and whitespace runs ignored, when that
   form occurs exactly once;
3. a close match: the pieces of the search that occur exactly once in the text anchor
   it, and the characters between and around them must differ in no more than
   ``1 - threshold`` of the passage, never in a number. Where an edge of the search is changed, the
   passage's edge is taken only when one place for it is clearly better; two spans
   that fit (two passages, or a passage with and without the character beside it)
   leave the edit unresolved, so an edit never lands on a shifted or a second span.

The work is linear in the text's length times the number of anchor pieces (at most
:data:`_MAX_PIECES`), plus edit-distance tables of at most :data:`_MAX_CELLS` cells,
whatever the lengths of the text and the search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Curly quotes, dashes and the no-break spaces as their plain forms.
_FOLD = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
        " ": " ",
    }
)

MIN_FUZZY_LENGTH = 10
"""A shorter search is matched only exactly or in its loose form, never fuzzily."""
_MAX_PIECES = 256
"""Most anchor pieces looked up in the text for one search."""
_MAX_CELLS = 250_000
"""Largest edit-distance table computed for one stretch of the search."""

NOT_FOUND = "not found in the text"
AMBIGUOUS = "fits more than one passage; copy it exactly, with enough words to be unique"
NUMBER_DIFFERS = "not found in the text: the closest passage has other numbers; copy it exactly"

_DIGITS = re.compile(r"\d+")
# A list item's number after a line break ("\n2. Toinen"), which a search may drop.
# One at the very start stays: a search that adds "2. " the text lacks must not take the
# previous sentence's ". " as its edge.
_INNER_LIST_MARKER = re.compile(r"(?<=\n)[ \t]*\d+[.)](?=\s)")
# A thousands separator: "1 200", "1,200" and "1.200" are the number 1200.
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d)[   ,.](?=\d{3}(?!\d))")


def _numbers_of(text: str) -> list[str]:
    """The numbers of ``text`` in order, grouped digits joined, list markers inside left out."""
    return _DIGITS.findall(_THOUSANDS_SEPARATOR.sub("", _INNER_LIST_MARKER.sub("", text)))


@dataclass(frozen=True)
class Span:
    """Where an edit applies: ``text[start:end]``.

    ``lead`` and ``trail`` are the whitespace at the search's ends that the text does
    not have beside the passage, so it can be left off a replacement that repeats it.
    """

    start: int
    end: int
    lead: str = ""
    trail: str = ""


def _folded(text: str) -> tuple[str, list[int]]:
    """``text`` lower-cased, quotes and dashes folded and each whitespace run one space,
    with the index in ``text`` of each character kept."""
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text.translate(_FOLD)):
        if ch.isspace():
            if out and out[-1] == " ":
                continue
            ch = " "
        for c in ch.lower():
            out.append(c)
            where.append(i)
    return "".join(out), where


def _kind(ch: str) -> str:
    if ch.isalnum() or ch == "_":
        return "w"
    return "s" if ch.isspace() else "p"


def _edit_distance(a: str, b: str, budget: int) -> int | None:
    """The edit distance of ``a`` and ``b``, or None when it is over ``budget`` or the
    table would exceed :data:`_MAX_CELLS`."""
    if a == b:
        return 0
    i, m = 0, min(len(a), len(b))
    while i < m and a[i] == b[i]:
        i += 1
    a, b = a[i:], b[i:]
    j, m = 0, min(len(a), len(b))
    while j < m and a[-1 - j] == b[-1 - j]:
        j += 1
    if j:
        a, b = a[:-j], b[:-j]
    if abs(len(a) - len(b)) > budget:
        return None
    if not a or not b:
        return max(len(a), len(b))
    if len(a) * len(b) > _MAX_CELLS:
        return None
    prev = list(range(len(b) + 1))
    for x, ca in enumerate(a, start=1):
        cur = [x] + [0] * len(b)
        for y, cb in enumerate(b, start=1):
            cur[y] = min(prev[y] + 1, cur[y - 1] + 1, prev[y - 1] + (ca != cb))
        if min(cur) > budget:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= budget else None


def _edge_costs(piece: str, text: str, budget: int) -> list[int] | None:
    """``costs[L]``: the edit distance of ``piece`` and ``text[:L]``, for every ``L`` up
    to ``len(text)``; None when the table would exceed :data:`_MAX_CELLS`."""
    if len(piece) * (len(text) + 1) > _MAX_CELLS:
        return None
    prev = list(range(len(text) + 1))
    for x, ca in enumerate(piece, start=1):
        cur = [x] + [0] * len(text)
        for y, cb in enumerate(text, start=1):
            cur[y] = min(prev[y] + 1, cur[y - 1] + 1, prev[y - 1] + (ca != cb))
        prev = cur
    return prev


def _pick(candidates: list[tuple[int, int]], clean: set[int]) -> int | None:
    """The length with the lowest cost; on a tie, the one tied length whose edge does
    not split a word of the text (``clean``); otherwise None."""
    low = min(cost for _, cost in candidates)
    best = [length for length, cost in candidates if cost == low]
    if len(best) == 1:
        return best[0]
    clean_best = [length for length in best if length in clean]
    return clean_best[0] if len(clean_best) == 1 else None


def _anchors(search: str, text: str) -> list[tuple[int, int]]:
    """``(position in search, position in text)`` of each search piece that occurs
    exactly once in ``text``."""
    n = len(search)
    k = max(5, min(32, n // 4))
    step = max(1, k // 2)
    starts = list(range(0, n - k + 1, step))
    if not starts or starts[-1] != n - k:
        starts.append(n - k)
    if len(starts) > _MAX_PIECES:
        stride = (len(starts) - 1) / (_MAX_PIECES - 1)
        starts = sorted({starts[round(i * stride)] for i in range(_MAX_PIECES)})
    found = []
    for j in starts:
        piece = search[j : j + k]
        p = text.find(piece)
        if p >= 0 and text.find(piece, p + 1) < 0:
            found.append((j, p))
    return found


def _fit(
    search: str, text: str, anchors: list[tuple[int, int]], budget: int
) -> tuple[int, int, int] | None:
    """``(start, end, edits)`` of the passage of ``text`` the anchors point to, or None
    when it differs from ``search`` by more than ``budget`` edits or an edge is unclear."""
    k = max(5, min(32, len(search) // 4))
    # Exact blocks (position in search, position in text, length), in order.
    blocks: list[list[int]] = []
    for j, p in sorted(anchors):
        length = min(k, len(search) - j)
        if blocks:
            bj, bp, bl = blocks[-1]
            if p <= bp:
                continue  # out of order: not part of one passage
            if j - p == bj - bp and j <= bj + bl:
                blocks[-1][2] = max(bl, j + length - bj)
                continue
            shift = max(bj + bl - j, bp + bl - p, 0)
            j, p, length = j + shift, p + shift, length - shift
            if length <= 0:
                continue
        blocks.append([j, p, length])
    if not blocks:
        return None

    edits = 0
    for (aj, ap, al), (bj, bp, _) in zip(blocks, blocks[1:], strict=False):
        cost = _edit_distance(search[aj + al : bj], text[ap + al : bp], budget - edits)
        if cost is None:
            return None
        edits += cost

    # The start: extend the first block back while the characters agree, then align
    # what is left of the search's start with the text before it.
    j0, p0, _ = blocks[0]
    while j0 and p0 and search[j0 - 1] == text[p0 - 1]:
        j0, p0 = j0 - 1, p0 - 1
    start = p0
    if j0:
        room = min(p0, j0 + budget - edits)
        before = text[p0 - room : p0][::-1]
        costs = _edge_costs(search[:j0][::-1], before, budget - edits)
        if costs is None:
            return None
        candidates = [(length, cost) for length, cost in enumerate(costs) if cost <= budget - edits]
        if not candidates:
            return None
        # A start inside a word of the text is never the passage's edge.
        clean = {
            length
            for length, _ in candidates
            if p0 - length == 0
            or not (_kind(text[p0 - length]) == "w" == _kind(text[p0 - length - 1]))
        }
        length = _pick(candidates, clean)
        if length is None:
            return None
        edits += costs[length]
        start = p0 - length

    # The end, the same way forward from the last block.
    lj, lp, ll = blocks[-1]
    je, pe = lj + ll, lp + ll
    while je < len(search) and pe < len(text) and search[je] == text[pe]:
        je, pe = je + 1, pe + 1
    end = pe
    if je < len(search):
        room = min(len(text) - pe, len(search) - je + budget - edits)
        after = text[pe : pe + room]
        costs = _edge_costs(search[je:], after, budget - edits)
        if costs is None:
            return None
        candidates = [(length, cost) for length, cost in enumerate(costs) if cost <= budget - edits]
        if not candidates:
            return None
        clean = {
            length
            for length, _ in candidates
            if pe + length == len(text)
            or not (_kind(text[pe + length - 1]) == "w" == _kind(text[pe + length]))
        }
        length = _pick(candidates, clean)
        if length is None:
            return None
        edits += costs[length]
        end = pe + length
    if end <= start:
        return None
    return start, end, edits


def _fuzzy(search: str, text: str, threshold: float) -> tuple[int, int] | str:
    """The ``(start, end)`` in ``text`` of the one passage close to ``search``, or the
    reason there is none."""
    n = len(search)
    budget = int(n * (1 - threshold) + 1e-9)
    if budget < 1:
        return NOT_FOUND
    anchors = _anchors(search, text)
    if not anchors:
        return NOT_FOUND
    # Anchors of one passage lie on nearly one diagonal (text position minus search
    # position); a gap wider than the budget starts another candidate passage.
    anchors.sort(key=lambda a: a[1] - a[0])
    groups: list[list[tuple[int, int]]] = [[anchors[0]]]
    for a in anchors[1:]:
        prev = groups[-1][-1]
        if (a[1] - a[0]) - (prev[1] - prev[0]) > budget:
            groups.append([a])
        else:
            groups[-1].append(a)
    groups.sort(key=len, reverse=True)
    fits = []
    for group in groups[:4]:
        fit = _fit(search, text, group, budget)
        if fit is None:
            continue
        start, end, edits = fit
        if edits <= (1 - threshold) * max(n, end - start) + 1e-9:
            fits.append((start, end))
    fits = sorted(set(fits))
    if not fits:
        return NOT_FOUND
    if len(fits) > 1:
        return AMBIGUOUS
    return fits[0]


def locate(text: str, search: str, threshold: float = 0.9) -> Span | str:
    """The :class:`Span` of ``text`` that ``search`` means, or why there is none
    (:data:`NOT_FOUND`, :data:`AMBIGUOUS` or :data:`NUMBER_DIFFERS`)."""
    if search and search in text:
        start = text.find(search)
        if text.find(search, start + 1) >= 0:
            return AMBIGUOUS
        return Span(start, start + len(search))
    core = search.strip()
    if not core:
        return NOT_FOUND
    lead = search[: len(search) - len(search.lstrip())]
    trail = search[len(search.rstrip()) :]

    folded_text, where = _folded(text)
    folded_core = _folded(core)[0]
    pos = folded_text.find(folded_core)
    if pos >= 0:
        if folded_text.find(folded_core, pos + 1) >= 0:
            return AMBIGUOUS
        span: tuple[int, int] | str = (pos, pos + len(folded_core))
    elif len(folded_core) < MIN_FUZZY_LENGTH:
        return NOT_FOUND
    else:
        span = _fuzzy(folded_core, folded_text, threshold)
        # A close match may differ in a letter, never in a number: "2021" for a
        # passage that says "2020" is a different fact, not a typo.
        if not isinstance(span, str):
            passage = text[where[span[0]] : where[span[1] - 1] + 1]
            if _numbers_of(passage) != _numbers_of(core):
                return NUMBER_DIFFERS
    if isinstance(span, str):
        return span
    start, end = where[span[0]], where[span[1] - 1] + 1

    # Whitespace at the search's ends counts only where the text has the same
    # characters beside the passage; the rest is reported, not taken from the text.
    taken = 0
    while taken < len(lead) and start > 0 and text[start - 1] == lead[-1 - taken]:
        start, taken = start - 1, taken + 1
    lead_left = lead[: len(lead) - taken]
    taken = 0
    while taken < len(trail) and end < len(text) and text[end] == trail[taken]:
        end, taken = end + 1, taken + 1
    trail_left = trail[taken:]
    return Span(start, end, lead_left, trail_left)
