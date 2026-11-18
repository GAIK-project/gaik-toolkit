"""Typographic ligatures as the letters they stand for.

A PDF often stores "fi", "ff" and similar pairs as one ligature character, and PyMuPDF
returns it as is, so "Sofia" comes out as "Soﬁa" and a search or a match on "Sofia"
misses it. Only the Latin ligature block (U+FB00 to U+FB06) is expanded: a full NFKC
normalization would also rewrite superscripts, fractions and full-width forms.
"""

from __future__ import annotations

_LIGATURES = str.maketrans(
    {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "st",
        "ﬆ": "st",
    }
)


def expand_ligatures(text: str) -> str:
    """``text`` with each Latin ligature character written as its letters."""
    return text.translate(_LIGATURES)
