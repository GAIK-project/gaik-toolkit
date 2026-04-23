"""Form field label cleanup endpoint.

Thin HTTP wrapper around
``gaik.software_components.form_understander.FormUnderstander``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from gaik.software_components.form_understander import FormUnderstander
from pydantic import BaseModel

from implementation_layer.api.config import get_openai_config
from implementation_layer.api.dependencies import verify_api_key

router = APIRouter()

LanguageHint = Literal["fi", "en"]


class UnderstandField(BaseModel):
    id: str
    label: str
    type: str | None = None
    htmlType: str | None = None
    parentHtmlSnippet: str | None = None


class UnderstandRequest(BaseModel):
    fields: list[UnderstandField]
    languageHint: LanguageHint | None = None


class UnderstandResponse(BaseModel):
    mapping: dict[str, str]


@router.post(
    "/",
    response_model=UnderstandResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Clean up form-field labels into human-readable names",
    description=(
        "Given a list of form-field identifiers with their raw labels and "
        "optional parent HTML snippets, returns a short cleaned label per id. "
        "Useful when a form (e.g. Sympa HR) uses generated identifiers that "
        "users cannot read."
    ),
)
async def understand_form(payload: UnderstandRequest):
    if not payload.fields:
        return UnderstandResponse(mapping={})

    try:
        config = get_openai_config()
        understander = FormUnderstander(config=config)
        mapping = understander.clean_labels(
            fields=[
                {
                    "id": f.id,
                    "raw": f.label,
                    "type": f.type,
                    "htmlType": f.htmlType,
                    "parent": f.parentHtmlSnippet,
                }
                for f in payload.fields
            ],
            language_hint=payload.languageHint,
        )
        return UnderstandResponse(mapping=mapping)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Label cleanup failed: {exc}") from exc
