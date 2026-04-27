"""Multi-provider extraction with the same Pydantic model.

Runs the same extraction prompt through Azure OpenAI, Anthropic Claude, and
Google Gemini using ``DataExtractor`` and a hand-built Pydantic schema, so
schema generation does not need to itself support every provider.

Set the env vars for the providers you want to test; missing providers are
skipped automatically. ``GOOGLE_API_KEY`` (or ``GEMINI_API_KEY``) enables
Google, ``ANTHROPIC_API_KEY`` enables Anthropic, and the usual
``AZURE_API_KEY`` + ``AZURE_ENDPOINT`` enable Azure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from datetime import date  # noqa: E402

from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from gaik.software_components.extractor import DataExtractor  # noqa: E402
from gaik.software_components.extractor.schema import ExtractionRequirements, FieldSpec  # noqa: E402
from gaik.software_components.llm import get_llm_config  # noqa: E402


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(description="Project title")
    acronym: str = Field(description="Project acronym")
    lead_institution: str = Field(description="Lead institution")
    total_funding_eur: float = Field(description="Total funding in EUR")
    start_date: date = Field(description="Project start date")
    status: str = Field(description="ongoing or completed")


REQUIREMENTS = ExtractionRequirements(
    use_case_name="research_project",
    fields=[
        FieldSpec(field_name="title", field_type="str", description="Project title"),
        FieldSpec(field_name="acronym", field_type="str", description="Project acronym"),
        FieldSpec(field_name="lead_institution", field_type="str", description="Lead institution"),
        FieldSpec(field_name="total_funding_eur", field_type="float", description="Funding (EUR)"),
        FieldSpec(field_name="start_date", field_type="date", description="Start date"),
        FieldSpec(
            field_name="status",
            field_type="str",
            description="Project status",
            enum=["ongoing", "completed"],
        ),
    ],
)

DOCUMENTS = [
    """
    Project Report
    Title: Advanced AI Research Initiative
    Acronym: AIRI
    Lead Institution: University of Helsinki
    Total Funding: 2500000 euros
    Status: Ongoing
    Start Date: 2024-01-15
    """,
]


def run_one(provider: str) -> None:
    print("\n" + "=" * 70)
    print(f"Provider: {provider}")
    print("=" * 70)
    config = get_llm_config(provider)
    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=Project,
        requirements=REQUIREMENTS,
        user_requirements="Extract the research project metadata.",
        documents=DOCUMENTS,
    )
    for record in results:
        print(record)


def main() -> None:
    candidates: list[str] = []
    if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_ENDPOINT"):
        candidates.append("azure")
    elif os.getenv("OPENAI_API_KEY"):
        candidates.append("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        candidates.append("anthropic")
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        candidates.append("google")

    if not candidates:
        print("No provider env vars set. Set at least one of: AZURE_API_KEY, "
              "OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY.")
        return

    for provider in candidates:
        try:
            run_one(provider)
        except Exception as exc:
            print(f"  [SKIP] {provider}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
