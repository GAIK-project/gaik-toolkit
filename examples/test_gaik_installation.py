"""Test script to verify gaik package works correctly from Test PyPI.

This script tests the basic functionality without making actual API calls.
"""

from gaik.schema import (
    SchemaExtractor,
    FieldSpec,
    ExtractionRequirements,
    create_extraction_model,
    sanitize_model_name,
)


def test_imports():
    """Test that all imports work."""
    print("[PASS] All imports successful")


def test_field_spec():
    """Test FieldSpec creation."""
    field = FieldSpec(
        field_name="invoice_number",
        field_type="str",
        description="The invoice number",
        required=True,
    )
    assert field.field_name == "invoice_number"
    assert field.field_type == "str"
    assert field.required is True
    print("[PASS] FieldSpec creation works")


def test_extraction_requirements():
    """Test ExtractionRequirements creation."""
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
    assert requirements.use_case_name == "Invoice"
    assert len(requirements.fields) == 2
    print("[PASS] ExtractionRequirements creation works")


def test_sanitize_model_name():
    """Test model name sanitization."""
    assert sanitize_model_name("My Project! (2024)") == "My_Project_2024"
    assert sanitize_model_name("Test___Name") == "Test_Name"
    assert sanitize_model_name("_Start_End_") == "Start_End"
    print("[PASS] sanitize_model_name works")


def test_create_extraction_model():
    """Test dynamic model creation."""
    requirements = ExtractionRequirements(
        use_case_name="TestCase",
        fields=[
            FieldSpec(
                field_name="title",
                field_type="str",
                description="Document title",
                required=True,
            ),
            FieldSpec(
                field_name="count",
                field_type="int",
                description="Item count",
                required=False,
            ),
        ],
    )

    Model = create_extraction_model(requirements)

    assert Model.__name__ == "TestCase_Extraction"
    assert "title" in Model.model_fields
    assert "count" in Model.model_fields
    print("[PASS] create_extraction_model works")

    # Test creating an instance
    instance = Model(title="Test Title", count=5)
    assert instance.title == "Test Title"
    assert instance.count == 5
    print("[PASS] Dynamic model instantiation works")

    # Test optional field
    instance2 = Model(title="Test Title 2")
    assert instance2.title == "Test Title 2"
    assert instance2.count is None
    print("[PASS] Optional fields work")


def test_schema_extractor_init():
    """Test SchemaExtractor initialization (without API calls)."""
    # We can't test actual extraction without an API key and making real calls
    # But we can test that the class can be imported and has the right structure

    import os
    from openai import OpenAI

    requirements = ExtractionRequirements(
        use_case_name="Test",
        fields=[
            FieldSpec(
                field_name="test",
                field_type="str",
                description="Test field",
                required=True,
            )
        ],
    )

    # Create a mock client with a fake API key (won't make actual calls)
    fake_client = OpenAI(api_key="sk-fake-key-for-testing")

    # Initialize with pre-made requirements and mock client (no API call)
    extractor = SchemaExtractor("", client=fake_client, requirements=requirements)

    assert extractor.requirements == requirements
    assert len(extractor.field_names) == 1
    assert extractor.field_names[0] == "test"
    assert len(extractor.fields) == 1
    print("[PASS] SchemaExtractor initialization works")


def main():
    """Run all tests."""
    print("Testing gaik package from Test PyPI...\n")

    test_imports()
    test_field_spec()
    test_extraction_requirements()
    test_sanitize_model_name()
    test_create_extraction_model()
    test_schema_extractor_init()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
    print("\nThe gaik package is working correctly from Test PyPI.")
    print("\nTo test actual extraction (requires OpenAI API key):")
    print("  export OPENAI_API_KEY='your-key'")
    print("  python -c \"from gaik.schema import SchemaExtractor; ...")
    print("\nInstallation command:")
    print("  pip install -i https://test.pypi.org/simple/ \\")
    print("              --extra-index-url https://pypi.org/simple/ gaik")


if __name__ == "__main__":
    main()
