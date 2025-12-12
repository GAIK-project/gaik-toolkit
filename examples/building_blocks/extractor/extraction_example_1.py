"""
Example 1: End-to-end dynamic schema generation and extraction.

This script demonstrates how to:
1. Configure the OpenAI/Azure client.
2. Generate a schema from natural-language requirements using SchemaGenerator.
3. Extract structured data from sample documents and save the results.
"""

import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
# sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from gaik.building_blocks.extractor import DataExtractor, SchemaGenerator, get_openai_config

if __name__ == "__main__":
    # Simple example showing how to use the SchemaGenerator class
    print("=" * 80)
    print("SCHEMA GENERATOR - EXAMPLE USAGE")
    print("=" * 80)

    # Configure OpenAI client (Azure or standard OpenAI)
    # Set use_azure=True for Azure OpenAI, or use_azure=False for standard OpenAI
    config = get_openai_config(use_azure=True)

    # Example: Extract project information
    user_requirements = """
    Extract project information from research grant documents.
    For each project, extract:
    - Project title (string)
    - Project acronym (string)
    - Lead institution (string)
    - Total funding in EUR (number)
    - Start date (date)
    - Project status (enum: ongoing or completed)
    """

    sample_document = [
        """
        Project Report

        Title: Advanced AI Research Initiative
        Acronym: AIRI
        Lead Institution: University of Helsinki
        Total Funding: 2500000 euros
        Partners: Finland, Sweden, Norway, Denmark
        Status: Ongoing
        Start Date: 2024-01-15
        """,
        """
        Project Summary

        Project Name: Green Energy Solutions
        Short Name: GES
        Lead: Technical University of Munich
        Budget: 1800000 EUR
        Participating Countries: Germany, Austria, Switzerland
        Current Status: Completed
        Started: 2023-06-01
        """,
    ]

    # Step 1: Generate schema
    generator = SchemaGenerator(config=config)

    print("\nStep 1: Generating schema...")
    print("-" * 80)

    schema = generator.generate_schema(user_requirements=user_requirements)
    print(f"\n[OK] Generated schema: {schema.__name__}")
    print(f"  Structure: {generator.structure_analysis.structure_type}")
    print(f"  Fields: {[f.field_name for f in generator.item_requirements.fields]}")

    # Step 2: Extract data using generated schema
    print("\nStep 2: Extracting data...")
    print("-" * 80)

    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=schema,
        requirements=generator.item_requirements,
        user_requirements=user_requirements,
        documents=sample_document,
        save_json=True,
        json_path="extraction_results.json",
    )

    # Display results
    print("\n" + "=" * 80)
    print("EXTRACTION RESULTS")
    print("=" * 80)
    import json

    print(json.dumps(results, indent=2, default=str))

