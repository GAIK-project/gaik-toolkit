"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class site_safety_inspection_checklist_record_Extraction(BaseModel):
    """Extraction model for site_safety_inspection_checklist_record"""

    model_config = ConfigDict(extra="forbid")

    section_heading: str | None = Field(
        default=None, description="The section heading the checklist item is under."
    )
    item_text: str | None = Field(default=None, description="The checklist item text.")
    result: Optional[Literal["", "ok", "not_ok", "not_applicable"]] = Field(
        default=None,
        description="The checklist item result: ok, not_ok, or not_applicable, according to the ticked box.",
    )
    remark: str | None = Field(
        default=None, description="The checklist item remark. The remark can be null."
    )


class site_safety_inspection_findings_and_corrective_action_Extraction(BaseModel):
    """Extraction model for site_safety_inspection_findings_and_corrective_actions"""

    model_config = ConfigDict(extra="forbid")

    number: str | None = Field(
        default=None, description="Number identifying the finding and corrective action record."
    )
    finding: str | None = Field(
        default=None, description="Finding recorded in the findings and corrective actions record."
    )
    severity: Optional[Literal["", "low", "medium", "high"]] = Field(
        default=None, description="Severity of the finding: low, medium, or high."
    )
    person_or_party_responsible: str | None = Field(
        default=None,
        description="Person or party responsible for the finding and corrective action.",
    )
    due_date: str | None = Field(default=None, description="Due date for the corrective action.")
    status: str | None = Field(
        default=None, description="Status of the finding and corrective action."
    )


class Site_safety_inspection_report_Extraction(BaseModel):
    """Extraction model for Site safety inspection report with repeated checklist, findings_and_corrective_actions"""

    model_config = ConfigDict(extra="forbid")

    report_number: str | None = Field(default=None, description="Report number.")
    report_type: str | None = Field(default=None, description="Report type.")
    form_number: str | None = Field(default=None, description="Form number.")
    revision: str | None = Field(default=None, description="Form revision.")
    company: str | None = Field(default=None, description="Company.")
    site: str | None = Field(default=None, description="Site.")
    project_number: str | None = Field(default=None, description="Project number.")
    inspection_date: str | None = Field(default=None, description="Inspection date.")
    start_time: str | None = Field(default=None, description="Inspection start time.")
    end_time: str | None = Field(default=None, description="Inspection end time.")
    inspector: str | None = Field(default=None, description="Inspector.")
    site_manager: str | None = Field(default=None, description="Site manager.")
    main_contractor: str | None = Field(default=None, description="Main contractor.")
    construction_phase: str | None = Field(default=None, description="Construction phase.")
    number_of_workers_on_site: int | None = Field(
        default=None, description="Number of workers on site."
    )
    number_of_subcontractors: int | None = Field(
        default=None, description="Number of subcontractors."
    )
    areas_covered: list[str] | None = Field(
        default=None, description="Areas covered by the inspection."
    )
    weather: str | None = Field(default=None, description="Weather.")
    previous_report_number: str | None = Field(default=None, description="Previous report number.")
    number_of_items_checked: int | None = Field(
        default=None, description="Summary number of items checked."
    )
    number_ok: int | None = Field(default=None, description="Summary number of items marked OK.")
    number_not_ok: int | None = Field(
        default=None, description="Summary number of items marked not OK."
    )
    safety_index: float | None = Field(
        default=None, description="Safety index in percent (numeric)."
    )
    overall_result: Optional[Literal["", "approved", "approved_with_remarks", "work_stopped"]] = (
        Field(
            default=None,
            description="Overall result; must be approved, approved_with_remarks, or work_stopped, according to the box that is ticked.",
        )
    )
    next_inspection_date: str | None = Field(
        default=None, description="Date of the next inspection."
    )
    inspector_signature_date: str | None = Field(
        default=None, description="Signature date of the inspector."
    )
    site_manager_signature_date: str | None = Field(
        default=None, description="Signature date of the site manager."
    )
    checklist: list[site_safety_inspection_checklist_record_Extraction] = Field(
        description="Checklist records, each containing section heading, item text, result (ok, not_ok, or not_applicable according to the ticked box), and remark."
    )
    findings_and_corrective_actions: list[
        site_safety_inspection_findings_and_corrective_action_Extraction
    ] = Field(
        description="Finding and corrective action records, each containing number, finding, severity (low, medium, or high), person or party responsible, due date, and status."
    )
