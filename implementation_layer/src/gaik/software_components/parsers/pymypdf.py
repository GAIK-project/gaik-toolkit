"""
PyMuPDF-based PDF parser for fast, local PDF text extraction.

This module uses PyMuPDF (fitz) to extract text from PDF files without
requiring external APIs or heavy ML models.
"""

import logging
import os
from typing import Any

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError as exc:
    PYMUPDF_AVAILABLE = False
    raise ImportError(
        "PyMuPDFParser requires the 'PyMuPDF' package. "
        "Install extras with 'pip install gaik[parser]'"
    ) from exc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PyMuPDFParser:
    """
    A fast PDF parser using PyMuPDF library for text extraction.

    Features:
    - Fast local PDF parsing without external APIs
    - Simple text extraction or structured output with positioning
    - Support for multi-page documents
    - No ML models or OCR (fast but limited for scanned documents)
    """

    def __init__(self):
        """
        Initialize the PyMuPDFParser.

        Raises:
            ImportError: If PyMuPDF is not installed
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF is not available. Install it with: pip install gaik[parser]")

        self.supported_extensions = [".pdf"]

    def parse_pdf(self, file_path: str, use_markdown: bool = True) -> str:
        """
        Parse PDF file and extract text content.

        Args:
            file_path: Path to the PDF file
            use_markdown: If True, returns simple text. If False, returns structured text with positioning

        Returns:
            Extracted text content as string

        Raises:
            FileNotFoundError: If file does not exist
            Exception: If PDF parsing fails
        """  # noqa: E501
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            doc = fitz.open(file_path)

            if use_markdown:
                # Simple text extraction
                text_content = ""
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    text_content += str(page.get_text())
                    text_content += "\n\n"  # Add page separator
            else:
                # Structured extraction preserving layout
                text_content = self._extract_structured_pdf(doc)

            doc.close()
            return text_content.strip()

        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {e}")
            raise

    def parse_document(self, file_path: str, use_markdown: bool = True) -> dict[str, Any]:
        """
        Parse a PDF document and return its content with metadata.

        Args:
            file_path: Path to the PDF file
            use_markdown: If True, returns simple text. If False, returns structured text

        Returns:
            Dictionary containing:
                - file_path: Original file path
                - file_name: File name
                - file_extension: File extension (.pdf)
                - text_content: Parsed document content
                - content_length: Length of parsed content
                - word_count: Number of words in content
                - parsing_method: 'pymupdf'
                - format_used: 'markdown' or 'structured'

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file is not a PDF
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_extension = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)

        if file_extension != ".pdf":
            raise ValueError(
                f"Unsupported file type: {file_extension}. Only PDF files are supported."
            )

        format_type = "markdown" if use_markdown else "structured"
        logger.info(f"Parsing document: {file_name} (format: {format_type})")

        # Extract text
        text_content = self.parse_pdf(file_path, use_markdown)

        if not text_content:
            logger.warning(f"No text content extracted from {file_name}")

        return {
            "file_path": file_path,
            "file_name": file_name,
            "file_extension": file_extension,
            "text_content": text_content,
            "content_length": len(text_content),
            "word_count": len(text_content.split()) if text_content else 0,
            "parsing_method": "pymupdf",
            "format_used": format_type,
        }

    def is_supported_file(self, file_path: str) -> bool:
        """Check if file format is supported (PDF only)."""
        extension = os.path.splitext(file_path)[1].lower()
        return extension in self.supported_extensions

    def _extract_structured_pdf(self, doc) -> str:
        """
        Extract text from PDF preserving layout and structure with positioning information.

        Args:
            doc: PyMuPDF document object

        Returns:
            Structured text with positioning markers
        """
        text_parts = []

        for page_num in range(doc.page_count):
            page = doc[page_num]

            # Add page header
            text_parts.append(f"=== PAGE {page_num + 1} ===")

            # Extract text blocks with positioning
            blocks = page.get_text("dict")

            for block in blocks.get("blocks", []):
                if "lines" in block:
                    block_text = []
                    for line in block["lines"]:
                        line_text = []
                        for span in line["spans"]:
                            if span["text"].strip():
                                # Add positioning info for structured extraction
                                x, y = span["bbox"][0], span["bbox"][1]
                                line_text.append(f"[x:{x:.0f},y:{y:.0f}] {span['text']}")
                        if line_text:
                            block_text.append(" ".join(line_text))
                    if block_text:
                        text_parts.append("\n".join(block_text))

            text_parts.append("")  # Page separator

        return "\n".join(text_parts)


def parse_pdf(file_path: str, use_markdown: bool = True, output_path: str = None) -> dict[str, Any]:
    """
    Convenience function to parse a PDF with minimal setup.

    This function provides a simple interface to parse PDF files using PyMuPDF.
    Fast local parsing without external APIs or ML models.

    Args:
        file_path: Path to the PDF file
        use_markdown: Return simple text (True) or structured text with positioning (False)
        output_path: Optional path to save the parsed content

    Returns:
        Dictionary with parsed document content and metadata

    Raises:
        ImportError: If PyMuPDF is not installed
        FileNotFoundError: If file does not exist
        ValueError: If file is not a PDF

    Example:
        >>> from pymupdf_parser import parse_pdf
        >>> result = parse_pdf("document.pdf")
        >>> print(result['text_content'])
        >>>
        >>> # Save to file
        >>> result = parse_pdf("document.pdf", output_path="output.txt")
        >>>
        >>> # Get structured output with positioning
        >>> result = parse_pdf("document.pdf", use_markdown=False)
    """
    # Initialize parser
    parser = PyMuPDFParser()

    # Parse document
    result = parser.parse_document(file_path, use_markdown=use_markdown)

    # Save to file if output path provided
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result["text_content"])
        logger.info(f"Parsed content saved to: {output_path}")

    return result
