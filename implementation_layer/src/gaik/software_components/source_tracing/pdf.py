"""Reading a PDF's own text layer: the words on each page and where they sit.

Needs PyMuPDF (``pip install gaik[source-tracing]``); it is imported only here, so the
rest of the component works without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matching import (
    as_number,
    date_parts,
    date_run,
    find_run,
    spelling_run,
    tokens,
    value_status,
)

Box = tuple[float, float, float, float]


@dataclass
class PageWords:
    """The words of one page in one reading order, each with the box of the word it came from."""

    width: float
    height: float
    tokens: list[str]
    boxes: list[Box]
    # The word of the PDF each token came from, as written (``6,000`` for tokens 6 and 000).
    originals: list[str]


def read_pages(path: str | Path) -> list[list[PageWords]]:
    """Each page's words, in two reading orders.

    The order the PDF stores its text and the order on the page (top to bottom, left
    to right) disagree in tables whose cells wrap: one of them reads a row as a row.
    A quote only has to be found in one.
    """
    try:
        import pymupdf  # PyMuPDF
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "Checking quotes in a PDF needs PyMuPDF: pip install 'gaik[source-tracing]'"
        ) from error

    pages: list[list[PageWords]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            readings: list[PageWords] = []
            for sort in (False, True):
                words: list[str] = []
                boxes: list[Box] = []
                originals: list[str] = []
                for x0, y0, x1, y1, word, *_ in page.get_text("words", sort=sort):
                    for token in tokens(word):
                        words.append(token)
                        boxes.append((x0, y0, x1, y1))
                        originals.append(word)
                readings.append(
                    PageWords(page.rect.width, page.rect.height, words, boxes, originals)
                )
            pages.append(readings)
    return pages


def rects(page: PageWords, start: int, length: int) -> list[dict]:
    """Boxes of the matched words, as fractions of the page, one per word."""
    seen: list[Box] = []
    for box in page.boxes[start : start + length]:
        if box not in seen:
            seen.append(box)
    return [
        {
            "x": x0 / page.width,
            "y": y0 / page.height,
            "w": (x1 - x0) / page.width,
            "h": (y1 - y0) / page.height,
        }
        for x0, y0, x1, y1 in seen
    ]


def value_span(page: PageWords, start: int, length: int, value: Any) -> tuple[int, int] | None:
    """Where the value sits inside the matched quote, in page tokens."""
    window = page.tokens[start : start + length]
    if as_number(value) is not None:
        # Compare with the words as written: 6,000 is two tokens but one number.
        for index in range(length):
            if value_status(value, page.originals[start + index]) == "match":
                same = 1
                while (
                    index + same < length
                    and page.boxes[start + index + same] == page.boxes[start + index]
                ):
                    same += 1
                return start + index, same
        return None
    text = str(value)
    parts = date_parts(text)
    if parts is not None:
        # The date in another format: the shortest run of words that holds all its parts.
        run = date_run(window, parts)
    else:
        wanted = tokens(text)
        found = find_run(window, wanted)
        # The same characters with other separators (7200-4453-21 for 7200445321).
        run = (found, len(wanted)) if found is not None else spelling_run(window, "".join(wanted))
    if run is None or run[1] >= length:
        return None
    return start + run[0], run[1]
