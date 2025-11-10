"""General AI Kit (GAIK) - AI/ML toolkit for Python.

Multi-provider LLM support with structured data extraction.

Modules:
    - gaik.extract: Structured data extraction
    - gaik.providers: LLM provider interface (OpenAI, Anthropic, Azure, Google)
    - gaik.parsers: PDF to Markdown parsing (vision models)

Example:
    >>> from gaik.extract import SchemaExtractor
    >>> extractor = SchemaExtractor("Extract name and age", provider="anthropic")
    >>> results = extractor.extract(["Alice is 25"])
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("gaik")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = ["__version__"]
