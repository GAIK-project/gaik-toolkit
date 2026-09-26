"""Data models for DraftReviewer results. Pydantic only."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Edit(BaseModel):
    """One search-and-replace correction proposed by the reviewer."""

    model_config = ConfigDict(extra="forbid")

    search: str = Field(
        description="Text to find in the draft, copied letter for letter. It must occur "
        "exactly once, so include enough surrounding words to make it unique."
    )
    replace: str = Field(description="Replacement text. An empty string deletes the passage.")
    reason: str = Field(description="Why the edit is needed, in one or two sentences.")


class ReviewResult(BaseModel):
    """The reviewed text and the edits behind it."""

    model_config = ConfigDict(extra="forbid")

    text: str
    applied: list[Edit]
    unresolved: list[Edit]
    """Edits whose search text still did not match exactly once after every attempt."""
