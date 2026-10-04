"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class additional_charges_Extraction(BaseModel):
    """Extraction model for additional_charges"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name of the charge in addition to the rent.")
    amount_per_month: OptionalDecimalField = Field(
        default=None,
        description="Amount per month, numeric and in euros. Can be null if the tenant pays the supplier directly.",
    )
    included_in_rent: bool | None = Field(
        default=None, description="Whether the charge is included in the rent."
    )


class residential_lease_agreement_Extraction(BaseModel):
    """Extraction model for residential_lease_agreement with repeated additional_charges"""

    model_config = ConfigDict(extra="forbid")

    landlord: str = Field(description="The landlord of the residential lease agreement.")
    tenant: str = Field(description="The tenant of the residential lease agreement.")
    apartment_address: str = Field(description="The apartment address.")
    size_in_square_metres: float | None = Field(
        default=None, description="The apartment size in square metres."
    )
    lease_type: Literal["", "fixed_term", "open_ended"] = Field(
        default="", description="The lease type: fixed_term or open_ended."
    )
    start_date: str = Field(description="The lease start date.")
    end_date: str | None = Field(
        default=None, description="The lease end date; should be null for an open-ended lease."
    )
    monthly_rent: OptionalDecimalField = Field(
        default=None, description="The monthly rent, numeric and in euros."
    )
    security_deposit: OptionalDecimalField = Field(
        default=None, description="The security deposit, numeric and in euros."
    )
    tenant_notice_period: str = Field(description="The tenant's notice period.")
    smoking_allowed: bool | None = Field(default=None, description="Whether smoking is allowed.")
    pets_allowed: bool | None = Field(
        default=None,
        description="Whether pets are allowed. Pets are allowed only if the text says so without a condition.",
    )
    additional_charges: list[additional_charges_Extraction] = Field(
        description="Charges in addition to the rent, each with its name, monthly amount in euros, and whether it is included in the rent. The monthly amount may be null if the tenant pays the supplier directly."
    )
