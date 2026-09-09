"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class document_kpi_extraction_Extraction(BaseModel):
    """Extraction model for document_kpi_extraction"""

    model_config = ConfigDict(extra="forbid")

    document_name: str | None = Field(default=None, description="Name or title of the document")
    document_number: str | None = Field(
        default=None, description="Identifier or reference number of the document"
    )
    change_in_annual_revenue: float | None = Field(
        default=None,
        description="Change in annual revenue, likely expressed as a percentage or numeric difference",
    )
    net_income: OptionalDecimalField = Field(
        default=None, description="Net income amount, typically a monetary value"
    )
    active_customers: int | None = Field(default=None, description="Number of active customers")
    customer_retention_rate: float | None = Field(
        default=None, description="Customer retention rate, typically a percentage"
    )
    net_promoter_score: float | None = Field(
        default=None, description="Net Promoter Score (NPS) value"
    )
    total_employees: int | None = Field(default=None, description="Total number of employees")
    employees_satisfaction_index: float | None = Field(
        default=None, description="Employee satisfaction index or score"
    )
    key_milestones_achieved: list[str] | None = Field(
        default=None, description="Few keyword-style descriptions of key milestones achieved"
    )
