"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class document_metrics_extraction_Extraction(BaseModel):
    """Extraction model for document_metrics_extraction"""

    model_config = ConfigDict(extra="forbid")

    document_name: str = Field(description="Document name")
    document_number: str = Field(description="Document number")
    change_in_annual_revenue: float | None = Field(
        default=None, description="Change in annual revenue (percent, as a number)"
    )
    net_income: OptionalDecimalField = Field(default=None, description="Net income")
    active_customers: int | None = Field(default=None, description="Active customers")
    customer_retention_rate: float | None = Field(
        default=None, description="Customer retention rate (percent, as a number)"
    )
    net_promoter_score: float | None = Field(default=None, description="Net promoter score")
    total_employees: int | None = Field(default=None, description="Total employees")
    employee_satisfaction_index: float | None = Field(
        default=None, description="Employee satisfaction index"
    )
    key_milestones_achieved: list[str] = Field(
        default=[], description="Key milestones achieved (a list of short phrases)"
    )
