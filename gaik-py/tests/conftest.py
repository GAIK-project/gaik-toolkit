"""Pytest configuration and shared fixtures for GAIK tests."""

import pytest
from gaik.extract import ExtractionRequirements, FieldSpec


@pytest.fixture
def sample_field_spec():
    """Create a sample FieldSpec for testing."""
    return FieldSpec(
        field_name="test_field",
        field_type="str",
        description="A test field",
        required=True,
    )


@pytest.fixture
def sample_extraction_requirements():
    """Create sample ExtractionRequirements for testing."""
    return ExtractionRequirements(
        use_case_name="TestExtraction",
        fields=[
            FieldSpec(
                field_name="name",
                field_type="str",
                description="Name field",
                required=True,
            ),
            FieldSpec(
                field_name="age",
                field_type="int",
                description="Age field",
                required=False,
            ),
        ],
    )


@pytest.fixture
def mock_llm_client(mocker):
    """Create a mock LLM client for testing without API calls."""
    mock_client = mocker.Mock()
    mock_client.invoke.return_value = mocker.Mock(content='{"name": "test", "age": 25}')
    return mock_client
