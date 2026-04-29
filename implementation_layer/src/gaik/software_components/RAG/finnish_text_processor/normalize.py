"""Light normalization helpers shared by every backend.

These run BEFORE the heavy NLP backend so the backend sees clean tokens.
"""

from __future__ import annotations

import re
import unicodedata

# Tokens are runs of letters / digits — drops punctuation, whitespace, dashes.
_TOKEN_RE = re.compile(r"[\wåäöÅÄÖ]+", flags=re.UNICODE)

# Finnish stopwords — short list of frequent function words. Conservative on
# purpose; aggressive stopword removal harms retrieval.
DEFAULT_FINNISH_STOPWORDS: frozenset[str] = frozenset(
    {
        "ja",
        "tai",
        "ei",
        "on",
        "olla",
        "se",
        "että",
        "kun",
        "mutta",
        "kuin",
        "tämä",
        "nämä",
        "ne",
        "joka",
        "jotka",
        "vai",
        "myös",
        "vielä",
        "jo",
        "niin",
        "noin",
        "näin",
    }
)


def tokenize(text: str) -> list[str]:
    """Split *text* into word-like tokens. No lowercasing — backends handle that."""
    return _TOKEN_RE.findall(text)


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization so combining diacritics collapse into single codepoints."""
    return unicodedata.normalize("NFC", text)


def remove_stopwords(tokens: list[str], stopwords: frozenset[str] | set[str]) -> list[str]:
    """Filter out *stopwords* from *tokens* (case-sensitive — apply lowercase first)."""
    return [t for t in tokens if t not in stopwords]
