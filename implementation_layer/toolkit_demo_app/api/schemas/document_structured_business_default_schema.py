"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class document_kpi_extraction_Extraction(BaseModel):
    """Extraction model for document_kpi_extraction"""
    model_config = ConfigDict(extra='forbid')

    document_name: str | None = Field(None, description="Name or title of the document")
    document_number: str | None = Field(None, description="Identifier or reference number of the document")
    change_in_annual_revenue: float | None = Field(None, description="Change in annual revenue, likely expressed as a percentage or numeric difference")
    net_income: decimal.Decimal | None = Field(None, description="Net income amount, typically a monetary value")
    active_customers: int | None = Field(None, description="Number of active customers")
    customer_retention_rate: float | None = Field(None, description="Customer retention rate, typically a percentage")
    net_promoter_score: float | None = Field(None, description="Net Promoter Score (NPS) value")
    total_employees: int | None = Field(None, description="Total number of employees")
    employees_satisfaction_index: float | None = Field(None, description="Employee satisfaction index or score")
    key_milestones_achieved: list[str] | None = Field(None, description="Few keyword-style descriptions of key milestones achieved")
