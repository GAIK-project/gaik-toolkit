"""Output schema for the Manufacturing Knowledge Assistant PoC.

RAGAnswerRecord -- one record per query.

This schema was hand-authored by the wizard agent (not generated via GAIK
SchemaGenerator): SchemaGenerator is only invoked for extraction/structured-
output patterns (audio_to_structured, document_to_structured, vision_extraction).
This use case is `rag`, so Phase 4 of the wizard is skipped, but the user
specified an explicit structured output contract (a JSON record per query
with an access decision and citations), so it is captured here as a normal
Pydantic model.

Citation format: each citation is a two-element JSON array [file_name, page_number],
NOT an object -- represented with `tuple[str, int]`, which Pydantic serializes as a
JSON array.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

Role = Literal["employee", "manager"]
AccessDecision = Literal["allowed", "denied"]

# A citation is [file_name, page_number] -- a 1-based integer page number.
Citation = tuple[str, int]


class RAGAnswerRecord(BaseModel):
    """One answer record for one query in the batch."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    role: Role
    question: str
    access_decision: AccessDecision
    answer: str
    citations: list[Citation] = []
    refusal_reason: Optional[str] = None

    @model_validator(mode="after")
    def _check_access_rules(self) -> "RAGAnswerRecord":
        if self.access_decision == "denied":
            if self.citations:
                raise ValueError("A denied record must have an empty citations list.")
            if not self.refusal_reason:
                raise ValueError("A denied record requires a non-null refusal_reason.")
        return self
