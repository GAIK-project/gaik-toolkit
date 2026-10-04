"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class residential_lease_charges_Extraction(BaseModel):
    """Extraction model for residential_lease_charges"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the charge in addition to the rent.")
    amount_per_month: OptionalDecimalField = Field(
        default=None,
        description="Amount of the charge per month, numeric and in euros. Can be null if the tenant pays the supplier directly.",
    )
    is_included_in_rent: bool | None = Field(
        default=None, description="Whether the charge is included in the rent."
    )


class residential_lease_agreement_Extraction(BaseModel):
    """Extraction model for residential_lease_agreement with repeated charges"""

    model_config = ConfigDict(extra="forbid")

    landlord: str = Field(description="Landlord of the residential lease agreement.")
    tenant: str = Field(description="Tenant of the residential lease agreement.")
    apartment_address: str = Field(description="Address of the leased apartment.")
    size: float | None = Field(default=None, description="Size of the apartment in square metres.")
    lease_type: Literal["", "fixed_term", "open_ended"] = Field(
        default="", description="Lease type: fixed_term or open_ended."
    )
    start_date: str = Field(description="Start date of the lease.")
    end_date: str | None = Field(
        default=None, description="End date of the lease; return null for an open-ended lease."
    )
    monthly_rent: OptionalDecimalField = Field(
        default=None, description="Monthly rent as a numeric monetary amount in euros."
    )
    security_deposit: OptionalDecimalField = Field(
        default=None, description="Security deposit as a numeric monetary amount in euros."
    )
    tenant_notice_period: str = Field(description="Tenant's notice period.")
    smoking_allowed: bool | None = Field(default=None, description="Whether smoking is allowed.")
    pets_allowed: bool | None = Field(
        default=None,
        description="Whether pets are allowed. Pets are allowed only if the text says so without a condition.",
    )
    charges: list[residential_lease_charges_Extraction] = Field(
        description="Charges in addition to the rent, each with a name, monthly amount in euros, and whether it is included in the rent."
    )
