"""Auto-generated schema - do not edit manually."""

from decimal import Decimal
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

class security_advisory_extraction_Extraction(BaseModel):
    """Extraction model for security_advisory_extraction"""
    model_config = ConfigDict(extra='forbid')

    cve_identifier: str = Field(description='CVE identifier')
    affected_product: str = Field(description='Affected product')
    affected_versions: str = Field(description='Affected versions as stated')
    severity: Literal['', 'Critical', 'High', 'Medium', 'Low'] = Field(description='Severity', default='')
    cvss_score: Optional[float] = Field(description='CVSS score', default=None)
    attack_vector: Literal['', 'Network', 'Adjacent', 'Local', 'Physical'] = Field(description='Attack vector', default='')
    patch_available: Literal['', 'yes', 'no'] = Field(description='Patch available', default='')
    patched_version: Optional[str] = Field(description='Patched version', default=None)
    published_date: str = Field(description='Published date')
    summary: list[str] = Field(description='Summary in a few keywords separated by semicolons', default_factory=list)
