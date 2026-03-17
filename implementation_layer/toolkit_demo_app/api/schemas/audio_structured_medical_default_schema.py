"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class medical_audio_extraction_Extraction(BaseModel):
    """Extraction model for medical_audio_extraction"""

    model_config = ConfigDict(extra="forbid")

    date: str | None = Field(None, description="Date of the encounter mentioned in the audio")
    patient_date_of_birth: str | None = Field(None, description="Patient's date of birth")
    symptoms: list[str] | None = Field(
        None, description="Patient symptoms summarized in a few keywords"
    )
    medical_history: list[str] | None = Field(
        None, description="Relevant medical history summarized in a few keywords"
    )
    examination_description: list[str] | None = Field(
        None, description="Key findings from the physical examination in a few keywords"
    )
    body_temperature: float | None = Field(None, description="Measured body temperature")
    heart_rate: int | None = Field(None, description="Measured heart rate")
    oxygen_saturation: int | None = Field(None, description="Measured oxygen saturation percentage")
    procedure_performed: list[str] | None = Field(
        None, description="Procedures performed, in a few keywords"
    )
    diagnosis: list[str] | None = Field(None, description="Diagnosis terms in a few keywords")
    prescription: list[str] | None = Field(
        None, description="Prescribed medications or treatments in a few keywords"
    )
    follow_up: list[str] | None = Field(
        None, description="Follow-up plan or instructions in a few keywords"
    )
