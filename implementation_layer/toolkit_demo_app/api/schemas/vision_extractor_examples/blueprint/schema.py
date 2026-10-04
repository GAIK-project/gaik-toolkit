"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class general_construction_notes_Extraction(BaseModel):
    """Extraction model for general_construction_notes"""

    model_config = ConfigDict(extra="forbid")

    note_number: str | None = Field(
        default=None, description="Note number identifying the general construction note."
    )
    note_text: str | None = Field(
        default=None, description="Text of the general construction note."
    )
    compliance_category: Optional[
        Literal[
            "",
            "Dimensions",
            "Structural reference",
            "Utilities/fixtures",
            "Survey/benchmarks",
            "Specifications",
            "Safety/compliance",
            "Other",
        ]
    ] = Field(
        default=None,
        description="Compliance category: Dimensions, Structural reference, Utilities/fixtures, Survey/benchmarks, Specifications, Safety/compliance, Other.",
    )


class revision_history_Extraction(BaseModel):
    """Extraction model for revision_history"""

    model_config = ConfigDict(extra="forbid")

    revision_number: str | None = Field(default=None, description="Revision number.")
    revision_date: str | None = Field(
        default=None, description="Revision date, preserving the original date."
    )
    revision_description: str | None = Field(
        default=None, description="Revision description, preserving the original wording."
    )


class visible_dimensions_Extraction(BaseModel):
    """Extraction model for visible_dimensions"""

    model_config = ConfigDict(extra="forbid")

    dimension_value: str | None = Field(
        default=None, description="Dimension value exactly as written."
    )
    unit: str | None = Field(default=None, description="Unit of the visible dimension.")
    direction_or_orientation: str | None = Field(
        default=None, description="Direction or orientation of the visible dimension."
    )
    related_element_or_view: str | None = Field(
        default=None, description="Related element or view for the visible dimension."
    )


class elevation_references_Extraction(BaseModel):
    """Extraction model for elevation_references"""

    model_config = ConfigDict(extra="forbid")

    elevation_value: str | None = Field(
        default=None, description="Elevation value exactly as written."
    )
    related_element_or_section: str | None = Field(
        default=None, description="Related element or section."
    )


class material_and_legend_references_Extraction(BaseModel):
    """Extraction model for material_and_legend_references"""

    model_config = ConfigDict(extra="forbid")

    symbol_or_pattern_name: str | None = Field(default=None, description="Symbol or pattern name.")
    meaning: str | None = Field(default=None, description="Meaning.")
    location_or_view: str | None = Field(default=None, description="Location or view.")


class drawing_views_grid_lines_and_callouts_Extraction(BaseModel):
    """Extraction model for drawing_views_grid_lines_and_callouts"""

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(
        default=None, description="Label of the drawing view, grid line, or callout."
    )
    type: str | None = Field(
        default=None, description="Type of the drawing view, grid line, or callout."
    )
    view_title_or_related_drawing_element: str | None = Field(
        default=None, description="View title or related drawing element."
    )
    compliance_relevant_information_shown: str | None = Field(
        default=None,
        description="Compliance-relevant information shown in the drawing view, grid line, or callout.",
    )


class construction_blueprint_compliance_Extraction(BaseModel):
    """Extraction model for construction_blueprint_compliance with repeated general_construction_notes, revision_history, visible_dimensions, elevation_references, material_and_legend_references, drawing_views_grid_lines_and_callouts"""

    model_config = ConfigDict(extra="forbid")

    project_address: str | None = Field(default=None, description="Project address.")
    drawing_title: str | None = Field(default=None, description="Drawing title.")
    drawing_number: str | None = Field(default=None, description="Drawing number.")
    sheet_number: str | None = Field(default=None, description="Sheet number.")
    project_number: str | None = Field(default=None, description="Project number.")
    scale: str | None = Field(default=None, description="Drawing scale.")
    drawing_date: str | None = Field(default=None, description="Drawing date.")
    architect: str | None = Field(default=None, description="Architect.")
    general_contractor: str | None = Field(default=None, description="General contractor.")
    surveyor: str | None = Field(default=None, description="Surveyor.")
    general_construction_notes: list[general_construction_notes_Extraction] = Field(
        description="Repeated construction notes with note number, note text, and compliance category."
    )
    revision_history: list[revision_history_Extraction] = Field(
        description="Repeated revisions with revision number, revision date, and revision description."
    )
    visible_dimensions: list[visible_dimensions_Extraction] = Field(
        description="Repeated visible dimensions with dimension value exactly as written, unit, direction or orientation, and related element or view."
    )
    elevation_references: list[elevation_references_Extraction] = Field(
        description="Repeated elevation references with elevation value exactly as written and related element or section."
    )
    material_and_legend_references: list[material_and_legend_references_Extraction] = Field(
        description="Repeated material and legend references with symbol or pattern name, meaning, and location or view."
    )
    drawing_views_grid_lines_and_callouts: list[
        drawing_views_grid_lines_and_callouts_Extraction
    ] = Field(
        description="Repeated drawing views, grid lines, and callouts with label, type, view title or related drawing element, and compliance-relevant information shown."
    )
