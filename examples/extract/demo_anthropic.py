"""
GAIK Anthropic Demo - Simple examples you can comment out as needed

This demo uses LangChain's with_structured_output() under the hood.
It guarantees that LLM responses match your Pydantic schema exactly.

SchemaExtractor parameters:
    user_description: str | None = None
        Natural language description of what to extract (required if requirements not provided)

    provider: "openai" | "anthropic" | "google" | "azure" = "openai"
        LLM provider to use

    model: str | None = None
        Model name (uses provider default if not specified)

    api_key: str | None = None
        API key (uses environment variable if not specified)

    client: BaseChatModel | None = None
        Custom LangChain client (overrides provider/model/api_key)

    requirements: ExtractionRequirements | None = None
        Pre-defined schema (skips LLM parsing if provided)
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

    # extract_one() uses LangChain's with_structured_output() internally
    # Returns guaranteed dict matching the schema
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

    # extract() calls with_structured_output() for each document
    # All results guaranteed to match schema
    results = extractor.extract(docs)
    for i, result in enumerate(results, 1):
        print(f"{i}. {result}")


# =============================================================================
# 6. CUSTOM REQUIREMENTS (Pre-defined schema)
# =============================================================================
def demo_custom_requirements():
    print("\n6. Custom Requirements")
    print("-" * 40)

    from gaik.extract import ExtractionRequirements, FieldSpec

    # Define your own schema instead of natural language
    # Skips LLM parsing = faster & cheaper
    requirements = ExtractionRequirements(
        use_case_name="Invoice",
        fields=[
            FieldSpec(
                field_name="invoice_number",
                field_type="str",
                description="Invoice number",
                required=True,
            ),
            FieldSpec(
                field_name="amount",
                field_type="float",
                description="Total amount",
                required=True,
            ),
        ],
    )

    # Pass requirements directly - skips LLM parsing step
    # No user_description needed when requirements provided
    extractor = SchemaExtractor(provider="anthropic", requirements=requirements)

    print(f"Fields: {extractor.field_names}")

    # Still uses with_structured_output() for extraction
    result = extractor.extract_one("Invoice #INV-001, amount: $1,500")
    print(f"Result: {result}")


# =============================================================================
# RUN DEMOS - Comment out any you don't want to run
# =============================================================================
if __name__ == "__main__":
    demo_basic()
    demo_custom_model()
    demo_schema()
    demo_custom_client()
    demo_batch()
    demo_custom_requirements()

    print("\n✅ Demo complete!")
