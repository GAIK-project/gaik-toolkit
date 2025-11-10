"""General AI Kit (GAIK) - Reusable AI/ML components for Python.

GAIK provides modular, production-ready tools for common AI/ML tasks including:
- Dynamic data extraction with structured outputs
- Multi-provider LLM support (OpenAI, Anthropic, Azure, Google)
- And more modules coming soon...

Available modules:
    - gaik.extract: Dynamic data extraction with LangChain structured outputs
    - gaik.providers: Multi-provider LLM interface (OpenAI, Anthropic, Azure, Google)
    - gaik.parsers: Vision-enabled PDF to Markdown parsing utilities

Example:
    >>> from gaik.extract import SchemaExtractor
    >>>
    >>> # Using default OpenAI provider
    >>> extractor = SchemaExtractor("Extract title and date from articles")
    >>> results = extractor.extract(documents)
    >>>
    >>> # Using Anthropic Claude
    >>> # IDE autocomplete shows: "openai" | "anthropic" | "google" | "azure"
    >>> extractor = SchemaExtractor(
    ...     "Extract name and age",
    ...     provider="anthropic"
    ... )
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("gaik")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = ["__version__"]
