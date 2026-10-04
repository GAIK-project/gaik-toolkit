"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal, Optional

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class availability_record_Extraction(BaseModel):
    """Extraction model for availability_record"""

    model_config = ConfigDict(extra="forbid")

    day: Optional[Literal["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]] = Field(
        default=None,
        description="Day of the week for the marked cell in the weekly availability grid: Mon, Tue, Wed, Thu, Fri, Sat, Sun.",
    )
    part_of_day: Optional[Literal["", "morning", "afternoon", "evening"]] = Field(
        default=None,
        description="Part of the day for the marked cell in the weekly availability grid: morning, afternoon, evening.",
    )


class education_history_Extraction(BaseModel):
    """Extraction model for education_history"""

    model_config = ConfigDict(extra="forbid")

    level: str | None = Field(default=None, description="Education level.")
    school_name: str | None = Field(default=None, description="Name of the school.")
    location: str | None = Field(default=None, description="Location of the school.")
    years_attended: str | None = Field(default=None, description="Years attended.")
    graduated: bool | None = Field(
        default=None, description="Whether the applicant graduated, expressed as true or false."
    )
    diploma_or_degree: str | None = Field(default=None, description="Diploma or degree.")


class employment_history_Extraction(BaseModel):
    """Extraction model for employment_history"""

    model_config = ConfigDict(extra="forbid")

    employer: str | None = Field(
        default=None, description="Employer for the employment history record."
    )
    position: str | None = Field(
        default=None, description="Position held for the employment history record."
    )
    start_date: str | None = Field(
        default=None, description="Employment start date (MM/YYYY, as written)."
    )
    end_date: str | None = Field(
        default=None, description="Employment end date (MM/YYYY, as written)."
    )
    start_pay: OptionalDecimalField = Field(
        default=None, description="Start pay per hour, expressed as a numeric value."
    )
    end_pay: OptionalDecimalField = Field(
        default=None, description="End pay per hour, expressed as a numeric value."
    )
    reason_for_leaving: str | None = Field(
        default=None, description="Reason for leaving the employment."
    )


class references_Extraction(BaseModel):
    """Extraction model for references"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="Name of the reference.")
    relationship: str | None = Field(
        default=None, description="Reference's relationship to the applicant."
    )
    phone_number: str | None = Field(default=None, description="Phone number of the reference.")
    years_known: int | None = Field(
        default=None,
        description="Number of years the applicant has known the reference, as a numeric value.",
    )


class employment_application_form_Extraction(BaseModel):
    """Extraction model for employment_application_form with repeated availability, education_history, employment_history, references"""

    model_config = ConfigDict(extra="forbid")

    application_date: str | None = Field(
        default=None, description="Date of the application, in MM/DD/YYYY format."
    )
    position_applied_for: str | None = Field(
        default=None, description="Position the applicant applied for."
    )
    applicant_full_name: str | None = Field(default=None, description="Applicant's full name.")
    applicant_phone: str | None = Field(default=None, description="Applicant's phone number.")
    applicant_email: str | None = Field(default=None, description="Applicant's email address.")
    street_address: str | None = Field(default=None, description="Applicant's street address.")
    city: str | None = Field(default=None, description="City in the applicant's address.")
    state: str | None = Field(default=None, description="State in the applicant's address.")
    zip_code: str | None = Field(default=None, description="ZIP code in the applicant's address.")
    desired_pay_rate_per_hour: OptionalDecimalField = Field(
        default=None, description="Applicant's desired pay rate per hour, as a numeric value."
    )
    date_available_to_start: str | None = Field(
        default=None, description="Date the applicant is available to start, in MM/DD/YYYY format."
    )
    eligible_to_work_in_us: bool | None = Field(
        default=None,
        description="Whether the applicant is eligible to work in the U.S.; return true or false according to the ticked box.",
    )
    previously_employed_here: bool | None = Field(
        default=None,
        description="Whether the applicant was previously employed here; return true or false according to the ticked box.",
    )
    skills_and_qualifications: str | None = Field(
        default=None, description="Skills and qualifications text exactly as written."
    )
    at_least_18_years_of_age: bool | None = Field(
        default=None,
        description="Answer to whether the applicant is at least 18 years of age, as true or false.",
    )
    can_work_weekends_and_holidays: bool | None = Field(
        default=None,
        description="Answer to whether the applicant can work weekends and holidays, as true or false.",
    )
    can_lift_25_lbs: bool | None = Field(
        default=None,
        description="Answer to whether the applicant can lift 25 lbs, as true or false.",
    )
    has_reliable_transportation: bool | None = Field(
        default=None,
        description="Answer to whether the applicant has reliable transportation, as true or false.",
    )
    employed_under_another_name: bool | None = Field(
        default=None,
        description="Answer to whether the applicant was employed under another name, as true or false.",
    )
    emergency_contact_name: str | None = Field(
        default=None, description="Emergency contact's name."
    )
    emergency_contact_relationship: str | None = Field(
        default=None, description="Emergency contact's relationship to the applicant."
    )
    emergency_contact_phone: str | None = Field(
        default=None, description="Emergency contact's phone number."
    )
    applicant_signature_name: str | None = Field(
        default=None, description="Name in the applicant's signature."
    )
    applicant_signature_date: str | None = Field(
        default=None, description="Date of the applicant's signature, in MM/DD/YYYY format."
    )
    interviewed_by: str | None = Field(
        default=None, description="Interviewer identified in the office-use section."
    )
    interview_date: str | None = Field(
        default=None, description="Interview date in the office-use section, in MM/DD/YYYY format."
    )
    decision: str | None = Field(
        default=None, description="Decision recorded in the office-use section."
    )
    availability: list[availability_record_Extraction] = Field(
        description="One structured record for each marked weekly-grid cell, containing day and part of day."
    )
    education_history: list[education_history_Extraction] = Field(
        description="Education rows containing level, school name, location, years attended, graduation status, and diploma or degree."
    )
    employment_history: list[employment_history_Extraction] = Field(
        description="Employment rows containing employer, position, start and end dates, start and end hourly pay, and reason for leaving."
    )
    references: list[references_Extraction] = Field(
        description="Reference records containing name, relationship, phone number, and years known."
    )
