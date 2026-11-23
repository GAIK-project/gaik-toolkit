"""Dev/test-only hooks — never enable outside controlled E2E (WIZARD_TEST_HOOKS=1)."""

import os

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/test", tags=["test"])


def _require_hooks() -> None:
    if os.getenv("WIZARD_TEST_HOOKS") != "1":
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/shutdown")
def shutdown() -> dict[str, bool]:
    """Exit the API process so Docker restart policy brings up a fresh instance."""
    _require_hooks()
    os._exit(0)
