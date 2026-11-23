"""Moving a user's sessions from their e-mail address to their owner id.

Sessions made before owner ids are saved under the address. On a user's first
request after the change, the web app asks for theirs to be moved: the header
names the owner id (``X-Wizard-User-Id``), the body the address the sessions
were saved under. The service token guards this route like every other; the
web app sends the address of the signed-in user only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from wizard_api.db import get_db
from wizard_api.owner_id import is_address, is_owner_id
from wizard_api.ownership import USER_HEADER, requesting_user
from wizard_api.services import session_service

router = APIRouter(prefix="/owners", tags=["owners"])


class ClaimLegacy(BaseModel):
    legacy_user_id: str = Field(min_length=3, max_length=255)

    @field_validator("legacy_user_id")
    @classmethod
    def an_address(cls, value: str) -> str:
        if not is_address(value):
            raise ValueError("legacy_user_id must be an e-mail address")
        return value


@router.post("/claim")
def claim_legacy_sessions(
    payload: ClaimLegacy,
    user_id: str | None = Depends(requesting_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if user_id is None or not is_owner_id(user_id):
        raise HTTPException(status_code=400, detail=f"{USER_HEADER} must be an owner id")
    return {"moved": session_service.move_owner(db, payload.legacy_user_id, user_id)}
