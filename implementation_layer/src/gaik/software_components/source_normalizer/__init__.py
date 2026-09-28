"""Source Normalizer

Converts mixed source files (PDF, Word, spreadsheets, text, recordings and images) to
Markdown texts that keep their provenance. The first stage of the report writer: the
texts feed KnowledgeCurator, which cites them by file name.

Main Classes:
    - SourceNormalizer: Convert source files to Markdown texts
    - NormalizedSource: One file's text with its provenance
    - NormalizedSources: The texts of a set of files, saved and loaded as a folder

Example:
    >>> from gaik.software_components.source_normalizer import SourceNormalizer
    >>> sources = SourceNormalizer().normalize({"primary": ["notes.txt", "budget.xlsx"]})
    >>> sources.save("output/sources")
"""

from .models import NormalizedSource, NormalizedSources
from .source_normalizer import SourceNormalizer

__all__ = [
    "SourceNormalizer",
    "NormalizedSource",
    "NormalizedSources",
]

__version__ = "0.1.0"
