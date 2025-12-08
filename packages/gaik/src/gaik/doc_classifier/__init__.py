"""Document Classification

Classify documents into predefined categories using LLM analysis of the first page.

This module provides document classification capabilities by extracting and analyzing
the first page of documents (PDFs, Word documents, or images) and categorizing them
using LLM-based classification with structured outputs.

Main Classes:
    - DocumentClassifier: Classify documents into user-provided categories

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Features:
    - Single-label classification (one class per document)
    - Automatic parser selection based on file type
    - Support for PDFs, Word docs (.docx, .doc), and images (.png, .jpg, .jpeg)
    - Confidence scores and reasoning for each classification
    - Batch processing of directories
    - "unknown" fallback category for uncertain classifications

Example - Single File:
    >>> from gaik.doc_classifier import DocumentClassifier, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> classifier = DocumentClassifier(config=config)
    >>> result = classifier.classify(
    ...     file_or_dir="invoice.pdf",
    ...     classes=["invoice", "receipt", "contract", "report"]
    ... )
    >>> print(result)
    {
        "invoice.pdf": {
            "class": "invoice",
            "confidence": 0.95,
            "reasoning": "Contains invoice number, billing address, and line items"
        }
    }

Example - Directory:
    >>> results = classifier.classify(
    ...     file_or_dir="documents/",
    ...     classes=["invoice", "receipt", "contract", "report"]
    ... )
    >>> for filename, classification in results.items():
    ...     print(f"{filename}: {classification['class']} "
    ...           f"(confidence: {classification['confidence']:.2f})")
    invoice_001.pdf: invoice (confidence: 0.95)
    receipt_042.pdf: receipt (confidence: 0.88)
    contract_2024.pdf: contract (confidence: 0.92)
    unknown_doc.pdf: unknown (confidence: 0.30)

Example - Custom Parser:
    >>> # Use vision parser for better accuracy on complex layouts
    >>> result = classifier.classify(
    ...     file_or_dir="complex_document.pdf",
    ...     classes=["invoice", "receipt"],
    ...     parser="vision"
    ... )
"""

from gaik.config import get_openai_config, create_openai_client
from .classifier import DocumentClassifier

__all__ = [
    "DocumentClassifier",
    "get_openai_config",
    "create_openai_client",
]

__version__ = "0.1.0"
