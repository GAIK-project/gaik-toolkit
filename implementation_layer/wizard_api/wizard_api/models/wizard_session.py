import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from wizard_api.models.base import Base


def _default_gate_statuses() -> dict:
    return {
        "gate_1": "pending",
        "gate_2": "pending",
        "gate_3": "pending",
        "gate_4": "pending",
    }


class WizardSession(Base):
    """Persisted wizard session (S1-1).

    Gate keys: gate_1 … gate_4. Values: pending | approved | rejected.
    Step: 1–12 wizard phase index.
    """

    __tablename__ = "wizard_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gate_statuses: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=_default_gate_statuses,
    )
    session_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, name="metadata"
    )
    output_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("gate_statuses", _default_gate_statuses())
        kwargs.setdefault("session_metadata", {})
        kwargs.setdefault("step", 1)
        super().__init__(**kwargs)
