"""Document and PDF Parsers

This module provides multiple PDF parsing options:

Vision-based Parsing:
    - VisionParser: Convert PDFs to Markdown using OpenAI vision models (GPT-4V)
    - OpenAIConfig: Configuration for OpenAI/Azure OpenAI
    - get_openai_config: Helper to get OpenAI configuration

Local Parsing:
    - PyMuPDFParser: Fast local PDF text extraction using PyMuPDF
    - parse_pdf: Convenience function for PyMuPDF parsing

Advanced Parsing:
    - DoclingParser: Advanced document parsing with OCR, table extraction, and multi-format support
    - parse_document: Convenience function for Docling parsing

Example:
    >>> from gaik.parsers import VisionParser, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> parser = VisionParser(openai_config=config, clean_output=True)
    >>> pages = parser.convert_pdf("document.pdf")
"""

__all__ = []

# Vision-based parsing (requires openai)
try:
    from .vision import OpenAIConfig, VisionParser, get_openai_config
    __all__.extend(["VisionParser", "OpenAIConfig", "get_openai_config"])
except ImportError:
    pass

# Local parsing (requires PyMuPDF)
try:
    from .pymypdf import PyMuPDFParser, parse_pdf
    __all__.extend(["PyMuPDFParser", "parse_pdf"])
except ImportError:
    pass

# Advanced parsing (requires docling)
try:
    from .docling import DoclingParser, parse_document
    __all__.extend(["DoclingParser", "parse_document"])
except ImportError:
    pass
