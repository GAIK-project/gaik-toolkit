"""Document and PDF Parsers

This module provides multiple document parsing options:

Vision-based Parsing:
    - VisionParser: Convert PDFs to Markdown using OpenAI vision models (GPT-4V)
    - OpenAIConfig: Configuration for OpenAI/Azure OpenAI
    - get_openai_config: Helper to get OpenAI configuration

Local Parsing:
    - PyMuPDFParser: Fast local PDF text extraction using PyMuPDF
    - parse_pdf: Convenience function for PyMuPDF parsing
    - DocxParser: Fast local Word document (.docx, .doc) text extraction using python-docx
    - parse_docx: Convenience function for DOCX parsing

Advanced Parsing:
    - DoclingParser: Advanced document parsing with OCR, table extraction, and multi-format support
    - parse_document: Convenience function for Docling parsing
    - VisionPlusParser: Docling + vision parsing that returns markdown + metadata (no chunking)
    - parse_document_with_vision_plus: Convenience wrapper for VisionPlusParser

Multi-provider Parsing:
    - MultimodalParser: PDF-to-markdown using OpenAI, Claude, or Google Gemini
    - ParseResult: Dataclass with raw_markdown, clean_markdown, and optional html

Remote Client Parsing:
    - DoclingApiClientParser: Client parser for remote Docling parsing service
    - parse_document_via_api: Convenience wrapper for remote parsing calls
"""

__all__ = []

# Vision-based parsing (requires openai)
try:
    from .vision import OpenAIConfig, VisionParser, get_openai_config

    __all__.extend(["VisionParser", "OpenAIConfig", "get_openai_config"])
except Exception:
    pass

# Local PDF parsing (requires PyMuPDF)
try:
    from .pymypdf import PyMuPDFParser, parse_pdf

    __all__.extend(["PyMuPDFParser", "parse_pdf"])
except Exception:
    pass

# Local DOCX parsing (requires python-docx)
try:
    from .docx_parser import DocxParser, parse_docx

    __all__.extend(["DocxParser", "parse_docx"])
except Exception:
    pass

# Advanced parsing (requires docling)
try:
    from .docling import DoclingParser, parse_document

    __all__.extend(["DoclingParser", "parse_document"])
except Exception:
    pass

# Vision+ advanced parsing (requires docling + openai)
try:
    from .visionPlus import VisionPlusParser, parse_document_with_vision_plus

    __all__.extend(["VisionPlusParser", "parse_document_with_vision_plus"])
except Exception:
    pass

# Remote client parsing (requires requests)
try:
    from .docling_api_client import DoclingApiClientParser, parse_document_via_api

    __all__.extend(["DoclingApiClientParser", "parse_document_via_api"])
except Exception:
    pass

# Multi-provider PDF parsing (requires anthropic, google-auth, markdown-it-py)
try:
    from .multimodal_parser import MultimodalParser, ParseResult

    __all__.extend(["MultimodalParser", "ParseResult"])
except ImportError:
    pass
