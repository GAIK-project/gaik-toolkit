"""Unit tests for gaik.extract module."""

import pytest

from gaik.extract import FieldSpec, create_extraction_model, sanitize_model_name


class TestFieldSpec:
    """Tests for FieldSpec model."""

    def test_field_spec_creation(self, sample_field_spec):
        """Test FieldSpec can be created with valid parameters."""
        assert sample_field_spec.field_name == "test_field"
        assert sample_field_spec.field_type == "str"
        assert sample_field_spec.description == "A test field"
        assert sample_field_spec.required is True

    def test_field_spec_optional(self):
        """Test FieldSpec with optional field."""
        field = FieldSpec(
            field_name="optional_field",
            field_type="int",
            description="Optional",
            required=False,
        )
        assert field.required is False


class TestExtractionRequirements:
    """Tests for ExtractionRequirements model."""

    def test_extraction_requirements_creation(self, sample_extraction_requirements):
        """Test ExtractionRequirements can be created."""
        assert sample_extraction_requirements.use_case_name == "TestExtraction"
        assert len(sample_extraction_requirements.fields) == 2

    def test_extraction_requirements_fields(self, sample_extraction_requirements):
        """Test fields in ExtractionRequirements."""
        fields = sample_extraction_requirements.fields
        assert fields[0].field_name == "name"
        assert fields[0].required is True
        assert fields[1].field_name == "age"
        assert fields[1].required is False


class TestModelCreation:
    """Tests for dynamic model creation utilities."""

    def test_sanitize_model_name_basic(self):
        """Test basic model name sanitization."""
        assert sanitize_model_name("Simple Name") == "Simple_Name"
        assert sanitize_model_name("test-name") == "test-name"  # Hyphens are allowed

    def test_sanitize_model_name_special_chars(self):
        """Test sanitization removes special characters."""
        assert sanitize_model_name("Test! Name@") == "Test_Name"
        assert sanitize_model_name("Name#With$Symbols") == "Name_With_Symbols"

    def test_create_extraction_model(self, sample_extraction_requirements):
        """Test dynamic model creation."""
        model = create_extraction_model(sample_extraction_requirements)

        # Check model name
        assert model.__name__ == "TestExtraction_Extraction"

        # Check model can be instantiated
        instance = model(name="John Doe", age=30)
        assert instance.name == "John Doe"
        assert instance.age == 30

    def test_create_extraction_model_required_field(self, sample_extraction_requirements):
        """Test model enforces required fields."""
        model = create_extraction_model(sample_extraction_requirements)

        # Should raise validation error when required field missing
        with pytest.raises(Exception):  # Pydantic ValidationError
            model(age=30)  # Missing required 'name' field

    def test_create_extraction_model_optional_field(self, sample_extraction_requirements):
        """Test model allows optional fields to be omitted."""
        model = create_extraction_model(sample_extraction_requirements)

        # Should work without optional 'age' field
        instance = model(name="Jane Doe")
        assert instance.name == "Jane Doe"
        assert instance.age is None  # Optional field default


class TestProviderIntegration:
    """Integration tests for provider functionality."""

    def test_provider_registry_exists(self):
        """Test that provider registry is accessible."""
        from gaik.providers import PROVIDERS

        assert isinstance(PROVIDERS, dict)
        assert len(PROVIDERS) > 0

    def test_get_provider_openai(self):
        """Test getting OpenAI provider."""
        from gaik.providers import get_provider

        provider = get_provider("openai")
        assert provider is not None
        assert hasattr(provider, "default_model")
        assert hasattr(provider, "create_chat_model")

    def test_all_expected_providers_exist(self):
        """Test all expected providers are registered."""
        from gaik.providers import PROVIDERS

        expected_providers = ["openai", "anthropic", "google", "azure"]
        for provider_name in expected_providers:
            assert provider_name in PROVIDERS, f"Provider {provider_name} not found"
