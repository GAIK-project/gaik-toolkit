"""Test gaik with real OpenAI API calls."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from gaik.schema import SchemaExtractor, dynamic_extraction_workflow


def test_simple_extraction():
    """Test simple extraction with SchemaExtractor."""
    print("Test 1: Simple person extraction")
    print("-" * 60)

    extractor = SchemaExtractor("""
    Extract from the text:
    - Person's name
    - Age (as number)
    - City where they live
    """)

    doc = "John Doe is 32 years old and lives in Helsinki."

    result = extractor.extract_one(doc)
    print(f"Input: {doc}")
    print(f"Result: {result}")
    print()


def test_workflow():
    """Test with dynamic_extraction_workflow."""
    print("Test 2: Invoice extraction with workflow")
    print("-" * 60)

    description = """
    Extract from invoices:
    - Invoice number
    - Total amount in euros (as number)
    - Vendor name
    """

    documents = [
        "Invoice #12345 from Acme Corp. Total: 1500 EUR",
        "INV-67890, Supplier: TechCo Ltd, Amount: 2750.00 euros"
    ]

    results = dynamic_extraction_workflow(description, documents, verbose=True)

    print("\nExtracted results:")
    for i, result in enumerate(results, 1):
        print(f"\nDocument {i}:")
        for key, value in result.items():
            print(f"  {key}: {value}")


def test_multiple_documents():
    """Test extracting from multiple documents with same schema."""
    print("\n" + "=" * 60)
    print("Test 3: Batch extraction")
    print("=" * 60)

    extractor = SchemaExtractor("""
    Extract:
    - Product name
    - Price in USD (as number)
    - Rating from 1-5 (as number)
    """)

    documents = [
        "The SuperWidget costs $29.99 and has a rating of 4.5 stars",
        "MegaTool is priced at $149 with 5-star reviews",
        "Budget Gadget - only $9.99, rated 3 out of 5"
    ]

    results = extractor.extract(documents)

    print("\nExtracted from 3 product reviews:")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result}")


if __name__ == "__main__":
    # Check if API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found in environment variables!")
        print("Please set it in .env file or export it:")
        print("  export OPENAI_API_KEY='sk-...'")
        exit(1)

    print("Testing gaik with real OpenAI API calls...")
    print("=" * 60)
    print()

    try:
        test_simple_extraction()
        test_workflow()
        test_multiple_documents()

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
