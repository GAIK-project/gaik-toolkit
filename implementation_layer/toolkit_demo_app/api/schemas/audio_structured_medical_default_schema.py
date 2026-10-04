"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class medical_audio_extraction_Extraction(BaseModel):
    """Extraction model for medical_audio_extraction"""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(description="Date.")
    patient_date_of_birth: str = Field(description="Patient's date of birth.")
    symptoms: list[str] = Field(default=[], description="Symptoms (in few keywords).")
    medical_history: str = Field(description="Medical history (in few keywords).")
    examination_description: str = Field(description="Examination description (in few keywords).")
    body_temperature: float | None = Field(default=None, description="Body temperature.")
    heart_rate: float | None = Field(default=None, description="Heart Rate.")
    oxygen_saturation: float | None = Field(default=None, description="Oxygen saturation.")
    procedure_performed: str = Field(description="Procedure performed (in few keywords).")
    diagnosis: str = Field(description="Diagnosis (in few keywords).")
    prescription: str = Field(description="Prescription (in few keywords).")
    follow_up: str = Field(description="Follow-up (in few keywords).")
