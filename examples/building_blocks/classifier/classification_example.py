"""Document Classifier Example

Demonstrates how to classify documents into predefined categories using the doc_classifier package.
"""

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.doc_classifier import DocumentClassifier, get_openai_config


def basic_classification():
    """Basic single file classification example."""
    print("=" * 60)
    print("Basic Single File Classification")
    print("=" * 60)

    # Setup
    config = get_openai_config(use_azure=True)
    classifier = DocumentClassifier(config=config)

    # Define categories
    classes = ["invoice", "receipt", "contract", "report", "memo", "article"]

    # Classify single file (use sample PDF from parsers folder)
    sample_pdf = Path(__file__).parent.parent / "parsers" / "WEF-page-10.pdf"
    result = classifier.classify(file_or_dir=str(sample_pdf), classes=classes)

    # Print results
    for filename, classification in result.items():
        print(f"\nDocument: {filename}")
        print(f"  Class: {classification['class']}")
        print(f"  Confidence: {classification['confidence']:.2f}")
        print(f"  Reasoning: {classification['reasoning']}")


def directory_classification():
    """Classify all documents in a directory."""
    print("\n" + "=" * 60)
    print("Directory Classification")
    print("=" * 60)

    # Setup
    config = get_openai_config(use_azure=True)
    classifier = DocumentClassifier(config=config)

    # Define categories
    classes = [
        "invoice",
        "receipt",
        "contract",
        "report",
        "memo",
        "purchase order",
        "bill of material",
    ]

    # Classify entire directory
    results = classifier.classify(
        file_or_dir=r"C:\Users\h02317\Downloads\test\multi-type with hierarchical relationships\Luvata",
        classes=classes,
    )

    # Print results summary
    print(f"\nClassified {len(results)} documents:\n")
    for filename, classification in results.items():
        print(
            f"{filename}: {classification['class']} "
            f"(confidence: {classification['confidence']:.2f})"
        )

    # Print detailed results
    print("\n" + "-" * 60)
    print("Detailed Results:")
    print("-" * 60)
    for filename, classification in results.items():
        print(f"\nDocument: {filename}")
        print(f"  Class: {classification['class']}")
        print(f"  Confidence: {classification['confidence']:.2f}")
        print(f"  Reasoning: {classification['reasoning']}")


def custom_parser_example():
    """Use a specific parser for classification."""
    print("\n" + "=" * 60)
    print("Custom Parser Example")
    print("=" * 60)

    # Setup
    config = get_openai_config(use_azure=True)
    classifier = DocumentClassifier(config=config)

    # Define categories
    classes = ["invoice", "receipt", "contract"]

    # Use vision parser for better accuracy on complex layouts
    result = classifier.classify(
        file_or_dir="complex_document.pdf",
        classes=classes,
        parser="vision",  # Override default PyMuPDF parser
    )

    # Print results
    for filename, classification in result.items():
        print(f"\nDocument: {filename}")
        print(f"  Class: {classification['class']}")
        print(f"  Confidence: {classification['confidence']:.2f}")
        print(f"  Reasoning: {classification['reasoning']}")


def mixed_file_types_example():
    """Classify directory with mixed file types (PDF, DOCX, images)."""
    print("\n" + "=" * 60)
    print("Mixed File Types Example")
    print("=" * 60)

    # Setup
    config = get_openai_config(use_azure=True)
    classifier = DocumentClassifier(config=config)

    # Define categories
    classes = ["invoice", "receipt", "contract", "form", "letter"]

    # Classify directory with mixed file types
    # PyMuPDF for PDFs, DocxParser for Word docs, VisionParser for images
    results = classifier.classify(file_or_dir="mixed_documents/", classes=classes)

    # Group by file type
    pdfs = {k: v for k, v in results.items() if k.endswith(".pdf")}
    docx = {k: v for k, v in results.items() if k.endswith((".docx", ".doc"))}
    images = {k: v for k, v in results.items() if k.endswith((".png", ".jpg", ".jpeg"))}

    print(f"\nPDFs: {len(pdfs)}")
    for filename, classification in pdfs.items():
        print(f"  {filename}: {classification['class']} ({classification['confidence']:.2f})")

    print(f"\nWord Documents: {len(docx)}")
    for filename, classification in docx.items():
        print(f"  {filename}: {classification['class']} ({classification['confidence']:.2f})")

    print(f"\nImages: {len(images)}")
    for filename, classification in images.items():
        print(f"  {filename}: {classification['class']} ({classification['confidence']:.2f})")


def error_handling_example():
    """Demonstrate error handling for various scenarios."""
    print("\n" + "=" * 60)
    print("Error Handling Example")
    print("=" * 60)

    # Setup
    config = get_openai_config(use_azure=True)
    classifier = DocumentClassifier(config=config)

    classes = ["invoice", "receipt", "contract"]

    # Example 1: Unsupported file format
    print("\n1. Unsupported file format:")
    try:
        result = classifier.classify(
            file_or_dir="document.txt",  # Unsupported format
            classes=classes,
        )
    except ValueError as e:
        print(f"   Error: {e}")

    # Example 2: Empty directory
    print("\n2. Empty directory:")
    try:
        classifier.classify(file_or_dir="empty_folder/", classes=classes)
    except ValueError as e:
        print(f"   Error: {e}")

    # Example 3: Corrupt file (will be caught during parsing)
    print("\n3. Corrupt file:")
    try:
        result = classifier.classify(file_or_dir="corrupt.pdf", classes=classes)
    except ValueError as e:
        print(f"   Error: {e}")

    # Example 4: Unknown classification
    print("\n4. Unknown classification (document doesn't match any class):")
    result = classifier.classify(file_or_dir="unclear_document.pdf", classes=classes)

    for filename, classification in result.items():
        if classification["class"] == "unknown":
            print(f"   Document: {filename}")
            print(f"   Class: {classification['class']}")
            print(f"   Confidence: {classification['confidence']:.2f}")
            print(f"   Reasoning: {classification['reasoning']}")


if __name__ == "__main__":
    # Run examples (comment out ones you don't want to run)

    ## Basic examples
    basic_classification()
    # directory_classification()

    ## Advanced examples
    # custom_parser_example()
    # mixed_file_types_example()

    ## Error handling
    # error_handling_example()


