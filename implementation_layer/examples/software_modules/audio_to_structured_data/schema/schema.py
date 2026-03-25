"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class standard_medical_consultation_summary_Extraction(BaseModel):
    """Extraction model for standard_medical_consultation_summary"""
    model_config = ConfigDict(extra='forbid')

    patient_name: str = Field(description="Patient Name")
    date_of_birth: str = Field(description="Date of Birth in this format: dd-mm-yyyy")
    consultation_date: str = Field(description="Consultation Date in this format: dd.mm.yyyy")
    symptoms: list[str] = Field(description="Symptoms")
    symptom_duration: str = Field(description="Symptom Duration")
    medical_history: str = Field(description="Medical History")
    examinations_performed: list[str] = Field(description="Examinations Performed")
    clinical_findings: str = Field(description="Clinical Findings")
    diagnosis: str = Field(description="Diagnosis")
    treatment_prescribed: str = Field(description="Treatment Prescribed")
    follow_up_instructions: str = Field(description="Follow-up Instructions")
    referrals: list[str] = Field(description="Referrals")
    attachments: list[str] = Field(description="Attachments")
