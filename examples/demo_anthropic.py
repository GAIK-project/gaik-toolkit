"""
GAIK Anthropic Demo - Simple examples you can comment out as needed
"""

from dotenv import load_dotenv
from gaik.extract import SchemaExtractor

load_dotenv()


# =============================================================================
# 1. BASIC EXTRACTION
# =============================================================================
def demo_basic():
    print("\n1. Basic Extraction")
    print("-" * 40)

    extractor = SchemaExtractor("Extract name and age from text", provider="anthropic")

    result = extractor.extract_one("Alice is 25 years old")
    print(f"Result: {result}")
    print(f"Model: {extractor.client.model}")


# =============================================================================
# 2. CUSTOM MODEL
# =============================================================================
def demo_custom_model():
    print("\n2. Custom Model Selection")
    print("-" * 40)

    extractor = SchemaExtractor(
        "Extract name and age from text",
        provider="anthropic",
        model="claude-opus-4-20250514",  # type: ignore
    )

    result = extractor.extract_one("Bob is 30 years old, engineer")
    print(f"Result: {result}")
    print(f"Model: {extractor.client.model}")


# =============================================================================
# 3. SCHEMA INSPECTION
# =============================================================================
def demo_schema():
    print("\n3. Schema Inspection")
    print("-" * 40)

    extractor = SchemaExtractor(
        """
        Extract from invoices:
        - Invoice number
        - Total amount in USD
        - Vendor name
    """,
        provider="anthropic",
    )

    print(f"Fields: {extractor.field_names}")

    result = extractor.extract_one("Invoice #INV-001 from Acme Corp. Total: $1,500")
    print(f"Result: {result}")


# =============================================================================
# 4. CUSTOM CLIENT
# =============================================================================
def demo_custom_client():
    print("\n4. Custom Client")
    print("-" * 40)

    from langchain_anthropic import ChatAnthropic

    client = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0.3)  # type: ignore

    extractor = SchemaExtractor("Extract product name and price", client=client)

    result = extractor.extract_one("MacBook Pro - $2,499")
    print(f"Result: {result}")
    print(f"Temperature: {extractor.client.temperature}")


# =============================================================================
# 5. BATCH EXTRACTION
# =============================================================================
def demo_batch():
    print("\n5. Batch Extraction")
    print("-" * 40)

    extractor = SchemaExtractor("Extract name and age", provider="anthropic")

    docs = ["Alice is 25 years old", "Bob is 30, engineer", "Charlie, age 28"]

    results = extractor.extract(docs)
    for i, result in enumerate(results, 1):
        print(f"{i}. {result}")


# =============================================================================
# RUN DEMOS - Comment out any you don't want to run
# =============================================================================
if __name__ == "__main__":
    demo_basic()
    demo_custom_model()
    demo_schema()
    demo_custom_client()
    demo_batch()

    print("\n✅ Demo complete!")
