"""Form field label cleanup endpoint.

Thin HTTP wrapper around
``gaik.software_components.form_understander.FormUnderstander``.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from gaik.software_components.form_understander import FormUnderstander
from pydantic import BaseModel

from implementation_layer.api.config import get_form_config
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


class UnderstoodLabel(BaseModel):
    id: str
    label: str
    """The cleaned label."""
    pageLabel: str  # noqa: N815 - public JSON field, camelCase like the request
    """The label the page itself gave the field, trimmed."""
    changed: bool
    """True when ``label`` has other words than ``pageLabel``: show both."""
    truncated: bool = False
    """True when ``label`` is ``pageLabel`` cut to 60 characters: show both."""


class UnderstandResponse(BaseModel):
    mapping: dict[str, str]
    """Each id's cleaned label, as before; ``labels`` adds the page's own label."""
    labels: list[UnderstoodLabel] = []


@router.post(
    "/",
    response_model=UnderstandResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Clean up form-field labels into human-readable names",
    description=(
        "Given a list of form-field identifiers with their raw labels and "
        "optional parent HTML snippets, returns a short cleaned label per id. "
        "Useful when a form (e.g. Sympa HR) uses generated identifiers that "
        "users cannot read. `labels` gives, in input order, each cleaned label "
        "with the page's own label and whether the model changed its words; "
        "show `pageLabel` beside `label` when `changed` or `truncated` is true."
    ),
)
async def understand_form(payload: UnderstandRequest):
    if not payload.fields:
        return UnderstandResponse(mapping={})
    repeated = sorted(i for i, n in Counter(f.id for f in payload.fields).items() if n > 1)
    if repeated:
        # One label comes back per id, so two fields with one id cannot both be named.
        raise HTTPException(
            status_code=422, detail=f"Field ids must be unique; repeated: {repeated}"
        )

    try:
        config = get_form_config()
        understander = FormUnderstander(config=config)
        described = understander.describe_labels(
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
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Label cleanup failed: {exc}") from exc
    return UnderstandResponse(
        mapping={d.id: d.label for d in described},
        labels=[
            UnderstoodLabel(
                id=d.id,
                label=d.label,
                pageLabel=d.original,
                changed=d.changed,
                truncated=d.truncated,
            )
            for d in described
        ],
    )
