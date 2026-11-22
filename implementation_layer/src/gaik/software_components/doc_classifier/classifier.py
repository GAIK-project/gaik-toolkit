"""
Document classification using LLM analysis.

This module provides document classification capabilities by analyzing the first page
of documents and categorizing them using LLM-based classification.
"""

import logging
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from gaik.software_components._log_names import error_text, file_tag
from gaik.software_components.file_type import detect_file_type
from gaik.software_components.input_limits import InputLimitError, InputLimits
from gaik.software_components.llm.base import FIT_TO_BOUNDS, ProviderClient
from gaik.software_components.llm.factory import build_compat_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.source_material import (
    SourceMaterial,
    source_material_messages,
)

from ..parsers.docx_parser import DocxParser
from ..parsers.pymypdf import PyMuPDFParser
from ..parsers.vision import VisionParser

logger = logging.getLogger(__name__)

_SUPPORTED_FORMATS = ".pdf, .docx, .png, .jpg, .jpeg"
# DocxParser reads a DOCX saved as .doc, not a Word 97-2003 document.
_DOC_FIX = "A Word 97-2003 .doc file is not read: save it as .docx first."


def _holds_docx(file_path: str) -> bool:
    try:
        return detect_file_type(file_path) == "docx"
    except OSError:
        return False


# System prompt for classification
SYSTEM_PROMPT = """You are a document classification expert.
Analyze the document content and classify it into one of the provided categories.
If you cannot confidently classify the document, use the 'unknown' category.
Provide a confidence score and brief reasoning for your classification."""


def _create_classification_model(classes: list[str]):
    """
    Create Pydantic model with Literal type for classes.

    Args:
        classes: List of classification categories

    Returns:
        Pydantic BaseModel class for classification results
    """
    # Create Literal type from classes
    ClassLiteral = Literal[tuple(classes)]  # type: ignore  # noqa: N806

    class ClassificationResult(BaseModel):
        document_class: ClassLiteral = Field(  # type: ignore
            ..., description="The classification category"
        )
        # The classifier's own score and explanation: a strict Claude tool cannot
        # carry their bounds, so an answer past one is fitted to it instead of failing.
        confidence: Annotated[float, FIT_TO_BOUNDS] = Field(
            ..., ge=0.0, le=1.0, description="Confidence score between 0 and 1"
        )
        reasoning: Annotated[str, FIT_TO_BOUNDS] = Field(
            ..., max_length=200, description="Brief explanation for the classification"
        )

    return ClassificationResult


class DocumentClassifier:
    """
    Classify documents into predefined categories using LLM analysis.

    This classifier extracts the first page from documents (PDF, DOCX, or images)
    and uses an LLM to categorize them into user-provided classes.

    A file over ``limits`` (size, image pixels; pages for the vision parser) is
    refused with :class:`~gaik.software_components.input_limits.InputLimitError`
    before it is parsed. The vision parser reads only the first page of a PDF.

    Attributes:
        config: OpenAI configuration dictionary
        model: Model name to use for classification
        client: OpenAI client instance
    """

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        limits: InputLimits | None = None,
        temperature: float | None = 0.0,
    ):
        """
        Initialize document classifier.

        Args:
            config: OpenAI config from get_openai_config()
            model: Optional model override. If not provided, uses config['model']
            limits: Input limits passed to the parsers; defaults to
                :class:`~gaik.software_components.input_limits.InputLimits`.
            temperature: Sampling temperature of the classification call on the
                OpenAI and Azure client. Defaults to ``0.0``. Pass ``None`` to
                leave it out, for a model that refuses an explicit temperature
                (its 400 would otherwise become ``unknown``). Other providers'
                clients are not sent a temperature, as before.

        Example:
            >>> from gaik.software_components.doc_classifier import (
            ...     DocumentClassifier, get_openai_config,
            ... )
            >>> config = get_openai_config(use_azure=True)
            >>> classifier = DocumentClassifier(config=config)
        """
        self.config = config
        self.model = model or config["model"]
        self.client = build_compat_client(config)
        self.limits = limits or InputLimits()
        self.temperature = temperature

    def classify(self, file_or_dir: str, classes: list[str], parser: str | None = None) -> dict:
        """
        Classify document(s) into predefined categories.

        Extraction behavior:
        - PDF files: Extracts first 1000 characters using PyMuPDFParser
        - DOCX files: Extracts first 1000 characters using DocxParser
        - Image files: Analyzes entire image using VisionParser

        Args:
            file_or_dir: Path to a single file or directory
            classes: List of classification categories (e.g., ["invoice", "receipt", "contract"])
                    'unknown' class is automatically added if not present
            parser: Optional parser override ('pymupdf', 'docx', 'vision')

        Returns:
            Dictionary mapping filenames to classification results:
            {
                "filename.pdf": {
                    "class": "invoice",
                    "confidence": 0.95,
                    "reasoning": "Contains invoice number and billing details"
                }
            }

        Raises:
            FileNotFoundError: If file_or_dir does not exist
            ValueError: If directory is empty or has no valid files
            ValueError: If file format is unsupported or corrupt

        Example:
            >>> results = classifier.classify(
            ...     file_or_dir="documents/",
            ...     classes=["invoice", "receipt", "contract"]
            ... )
            >>> for filename, result in results.items():
            ...     print(f"{filename}: {result['class']}")
        """
        # Validate input path
        path = Path(file_or_dir)
        if not path.exists():
            logger.error("Path does not exist: %s", file_tag(file_or_dir))
            raise FileNotFoundError(f"Path does not exist: {file_or_dir}")

        # Ensure 'unknown' class is included
        classes = self._validate_classes(classes)

        # Determine if single file or directory
        if path.is_file():
            filename = path.name
            result = self._classify_single_file(str(path), classes, parser)
            return {filename: result}
        elif path.is_dir():
            return self._classify_directory(str(path), classes, parser)
        else:
            logger.error("Invalid path type: %s", file_tag(file_or_dir))
            raise ValueError(f"Invalid path type: {file_or_dir}")

    def _classify_single_file(
        self, file_path: str, classes: list[str], parser_override: str | None
    ) -> dict:
        """
        Classify a single document file.

        Args:
            file_path: Path to the document file
            classes: List of classification categories
            parser_override: Optional parser specification

        Returns:
            Classification result dictionary with 'class', 'confidence', 'reasoning'

        Raises:
            ValueError: If file format is unsupported or corrupt
            InputLimitError: If the file is over one of ``limits``
        """
        logger.info("Classifying file: %s", file_tag(file_path))

        # Validate file format
        if not self._is_valid_file(file_path):
            logger.error("Unsupported file format: %s", file_tag(file_path))
            suffix = Path(file_path).suffix
            raise ValueError(
                f"Unsupported file format: {suffix}. Supported formats: {_SUPPORTED_FORMATS}"
                + (f". {_DOC_FIX}" if suffix.lower() == ".doc" else "")
            )

        try:
            # Determine parser to use
            parser_type = self._get_parser_for_file(file_path, parser_override)

            # Extract text (1000 chars for PDF/DOCX, full for images)
            text = self._extract_text(file_path, parser_type)

            if not text or len(text.strip()) == 0:
                logger.warning("No text extracted from %s", file_tag(file_path))
                return {
                    "class": "unknown",
                    "confidence": 0.0,
                    "reasoning": "No text content found in document",
                }

            # Classify with LLM
            result = self._classify_with_llm(text, classes)
            return result

        except InputLimitError:
            raise
        except Exception as e:
            logger.error("Error classifying %s: %s", file_tag(file_path), error_text(e, file_path))
            raise ValueError(f"Failed to classify {file_path}: {str(e)}")

    def _classify_directory(
        self, dir_path: str, classes: list[str], parser_override: str | None
    ) -> dict:
        """
        Classify all valid documents in a directory.

        Args:
            dir_path: Path to directory
            classes: List of classification categories
            parser_override: Optional parser specification

        Returns:
            Dictionary mapping filenames to classification results

        Raises:
            ValueError: If directory is empty or contains no valid files
        """
        dir_path_obj = Path(dir_path)
        results = {}

        # Find all valid files
        valid_files = [
            f for f in dir_path_obj.iterdir() if f.is_file() and self._is_valid_file(str(f))
        ]

        legacy_doc = sum(
            1
            for f in dir_path_obj.iterdir()
            if f.is_file() and f.suffix.lower() == ".doc" and f not in valid_files
        )
        if legacy_doc:
            logger.warning("Skipping %d .doc file(s). %s", legacy_doc, _DOC_FIX)

        if not valid_files:
            logger.error("No valid files found in the directory given")
            raise ValueError(
                f"Directory is empty or contains no valid files: {dir_path}\n"
                f"Supported formats: {_SUPPORTED_FORMATS}" + (f"\n{_DOC_FIX}" if legacy_doc else "")
            )

        logger.info(f"Found {len(valid_files)} valid files to classify")

        # Classify each file
        for file_path in valid_files:
            try:
                result = self._classify_single_file(str(file_path), classes, parser_override)
                results[file_path.name] = result
            except Exception as e:
                logger.error("Skipping %s: %s", file_tag(file_path), error_text(e, file_path))
                results[file_path.name] = {
                    "class": "unknown",
                    "confidence": 0.0,
                    "reasoning": f"Error: {str(e)[:100]}",
                }

        return results

    def _extract_text(self, file_path: str, parser_type: str) -> str:
        """
        Extract text from document using specified parser.
        For PDF/DOCX: extracts full text then truncates to 1000 chars.
        For images: uses VisionParser to analyze the entire image.

        Args:
            file_path: Path to document
            parser_type: Parser to use ('pymupdf', 'docx', 'vision')

        Returns:
            Extracted text content (max 1000 chars for PDF/DOCX)

        Raises:
            ValueError: If parser type is unsupported or extraction fails
        """
        if parser_type == "pymupdf":
            try:
                # Only the start of the text is used, so the page limit does not
                # apply here; the size limit does.
                parser = PyMuPDFParser(limits=replace(self.limits, max_pages=None))
                result = parser.parse_document(file_path)
                full_text = result["text_content"]
                # Return first 1000 characters
                return full_text[:1000]
            except InputLimitError:
                raise
            except Exception as e:
                raise ValueError(f"PyMuPDF extraction failed: {str(e)}")

        elif parser_type == "docx":
            try:
                parser = DocxParser(limits=self.limits)
                result = parser.parse_document(file_path)
                full_text = result["text_content"]
                # Return first 1000 characters
                return full_text[:1000]
            except InputLimitError:
                raise
            except Exception as e:
                raise ValueError(f"DOCX extraction failed: {str(e)}")

        elif parser_type == "vision":
            try:
                parser = VisionParser(openai_config=self.config, limits=self.limits)

                # Check if file is PDF or image
                file_type = self._detect_file_type(file_path)

                if file_type == "pdf":
                    # For PDFs via vision: convert the first page only
                    pages = parser.convert_pdf(
                        file_path, dpi=200, clean_output=False, first_pages=1
                    )
                    return pages[0] if pages else ""

                elif file_type == "image":
                    return parser.convert_image(file_path)

                else:
                    raise ValueError(f"Vision parser received unexpected file type: {file_type}")

            except InputLimitError:
                raise
            except Exception as e:
                raise ValueError(f"Vision extraction failed: {str(e)}")

        else:
            raise ValueError(f"Unsupported parser type: {parser_type}")

    def _classify_with_llm(self, text: str, classes: list[str]) -> dict:
        """
        Classify document text using LLM.

        Args:
            text: Document text to classify
            classes: List of classification categories

        Returns:
            Classification result with 'class', 'confidence', 'reasoning'
        """
        # Create classification model
        ClassificationModel = _create_classification_model(classes)  # noqa: N806

        # Create prompt
        classes_str = ", ".join(f"'{c}'" for c in classes if c != "unknown")

        # Truncate to 4000 chars (~1000 tokens) to prevent token limit errors.
        # The document is material, apart from the task: it cannot pick its class.
        document_block = SourceMaterial().wrap(text[:4000], label="document")
        user_prompt = f"""Classify the following document into one of \
these categories: {classes_str}

If the document does not clearly fit any category, classify it as 'unknown'.

Document content:
{document_block}

Provide your classification with:
1. The category that best matches
2. A confidence score (0.0 to 1.0)
3. Brief reasoning (max 200 characters)
"""

        messages = source_material_messages(SYSTEM_PROMPT, user_prompt)

        try:
            if isinstance(self.client, ProviderClient):
                parsed = self.client.chat_parsed(
                    messages=messages,
                    response_format=ClassificationModel,
                    model=self.model,
                )
            else:
                sampling = {} if self.temperature is None else {"temperature": self.temperature}
                response = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=messages,
                    response_format=ClassificationModel,
                    **normalize_chat_kwargs(self.model, sampling, config=self.config),
                    timeout=30,
                )
                parsed = response.choices[0].message.parsed

            return {
                "class": parsed.document_class,
                "confidence": parsed.confidence,
                "reasoning": parsed.reasoning,
            }

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                "class": "unknown",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)[:100]}",
            }

    def _detect_file_type(self, file_path: str) -> str:
        """
        Detect file type based on extension.

        Args:
            file_path: Path to file

        Returns:
            File type: 'pdf', 'docx', 'image', or 'unsupported'
        """
        suffix = Path(file_path).suffix.lower()

        if suffix == ".pdf":
            return "pdf"
        elif suffix in [".docx", ".doc"]:
            # A .doc gets here only when it holds a DOCX (see _is_valid_file).
            return "docx"
        elif suffix in [".png", ".jpg", ".jpeg"]:
            return "image"
        else:
            return "unsupported"

    def _get_parser_for_file(self, file_path: str, parser_override: str | None) -> str:
        """
        Determine which parser to use for a file.

        Args:
            file_path: Path to file
            parser_override: Optional parser specification

        Returns:
            Parser type: 'pymupdf', 'docx', or 'vision'
        """
        if parser_override:
            return parser_override

        # Auto-detect based on file type
        file_type = self._detect_file_type(file_path)

        if file_type == "pdf":
            return "pymupdf"
        elif file_type == "docx":
            return "docx"
        elif file_type == "image":
            return "vision"
        else:
            raise ValueError(f"Cannot determine parser for file type: {file_type}")

    @staticmethod
    def _validate_classes(classes: list[str]) -> list[str]:
        """
        Ensure 'unknown' class is included in the class list.

        Args:
            classes: Original list of classes

        Returns:
            Classes with 'unknown' added if not present
        """
        if "unknown" not in [c.lower() for c in classes]:
            return classes + ["unknown"]
        return classes

    @staticmethod
    def _is_valid_file(file_path: str) -> bool:
        """
        Check if file format is supported.

        Args:
            file_path: Path to file

        Returns:
            True if file format is supported, False otherwise
        """
        suffix = Path(file_path).suffix.lower()
        if suffix == ".doc":
            return _holds_docx(file_path)
        return suffix in [".pdf", ".docx", ".png", ".jpg", ".jpeg"]
