"""
Example 3: Using a manually defined schema instead of SchemaGenerator.

This demo shows how to:
1. Hand-write a strict Pydantic model for the fields you expect.
2. Manually construct the matching ExtractionRequirements metadata.
3. Run DataExtractor with those manual definitions.
"""

import sys
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Add src directory to path so we can import without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.extractor import (DataExtractor,  # noqa: E402  # noqa: E402
                            ExtractionRequirements, FieldSpec,
                            get_openai_config)


class ProjectInfo(BaseModel):
    """Static schema mirroring the project information fields."""

    model_config = ConfigDict(extra="forbid")

    project_title: str = Field(description="Project title")
    project_acronym: str = Field(description="Project acronym")
    lead_institution: str = Field(description="Lead institution")
    total_funding_eur: Decimal = Field(description="Total funding in EUR")
    start_date: str = Field(description="Start date")
    project_status: Literal["ongoing", "completed"] = Field(description="Project status")


manual_requirements = ExtractionRequirements(
    use_case_name="Project information",
    fields=[
        FieldSpec(field_name="project_title", field_type="str", description="Project title"),
        FieldSpec(field_name="project_acronym", field_type="str", description="Project acronym"),
        FieldSpec(field_name="lead_institution", field_type="str", description="Lead institution"),
        FieldSpec(
            field_name="total_funding_eur", field_type="decimal", description="Total funding in EUR"
        ),
        FieldSpec(field_name="start_date", field_type="date", description="Start date"),
        FieldSpec(
            field_name="project_status",
            field_type="str",
            description="Project status",
            enum=["ongoing", "completed"],
        ),
    ],
)


SAMPLE_DOCUMENTS = [
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


if __name__ == "__main__":
    print("=" * 80)
    print("MANUAL SCHEMA EXTRACTION EXAMPLE")
    print("=" * 80)

    config = get_openai_config(use_azure=True)
    extractor = DataExtractor(config=config)

    results = extractor.extract(
        extraction_model=ProjectInfo,
        requirements=manual_requirements,
        user_requirements=(
            "Manually supplied schema for project title, acronym, lead institution, "
            "total funding in EUR, start date, and project status (ongoing/completed)."
        ),
        documents=SAMPLE_DOCUMENTS,
        save_json=True,
        json_path="extraction_results_manual.json",
    )

    print("\nExtraction output:\n")
    import json as _json

    print(_json.dumps(results, indent=2, default=str))


