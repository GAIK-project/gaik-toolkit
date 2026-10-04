"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class laboratory_test_results_Extraction(BaseModel):
    """Extraction model for laboratory_test_results"""

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(description="Name of the laboratory test.")
    measured_value: float | None = Field(
        default=None, description="Measured test value, numeric when possible."
    )
    unit: str | None = Field(
        default=None, description="Unit of the measured test value; can be null if not shown."
    )
    reference_range_minimum: float | None = Field(
        default=None,
        description="Reference-range minimum, numeric when possible; can be null if not shown.",
    )
    reference_range_maximum: float | None = Field(
        default=None,
        description="Reference-range maximum, numeric when possible; can be null if not shown.",
    )
    interpretation: Literal["", "low", "normal", "high", "abnormal", "unknown"] = Field(
        default="",
        description="Interpretation stated in the report. Must be low, normal, high, abnormal, or unknown; do not provide a medical interpretation beyond what the report states.",
    )


class laboratory_report_patient_and_report_information_Extraction(BaseModel):
    """Extraction model for laboratory_report_patient_and_report_information with repeated test_results"""

    model_config = ConfigDict(extra="forbid")

    patient_name: str = Field(description="Patient name from the laboratory report.")
    patient_identifier: str = Field(description="Patient identifier from the laboratory report.")
    date_of_birth: str = Field(description="Patient date of birth.")
    sample_collection_date: str = Field(description="Sample collection date.")
    report_date: str = Field(description="Report date.")
    laboratory_name: str = Field(description="Laboratory name.")
    requesting_physician: str | None = Field(
        default=None, description="Requesting physician; can be null if not provided."
    )
    test_results: list[laboratory_test_results_Extraction] = Field(
        description="Laboratory test result records, each containing test name, measured value, unit, reference-range minimum, reference-range maximum, and interpretation."
    )
