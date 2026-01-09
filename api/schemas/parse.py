"""Parse endpoint schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ParseResponse(BaseModel):
    """Document parsing response."""

    filename: str = Field(..., description="Original filename")
    parser: str = Field(..., description="Parser used (pymupdf/docx/vision)")
    text_content: str = Field(..., description="Extracted text content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "filename": "invoice.pdf",
                "parser": "pymupdf",
                "text_content": "Invoice #12345\nTotal: $1,500.00...",
                "metadata": {"word_count": 250, "pages": 2},
            }
        }
    }
