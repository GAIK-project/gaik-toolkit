from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from wizard_api.models.base import Base


class UsageTotal(Base):
    """What one user, or the deployment in one month, has spent and started.

    ``scope`` is ``user`` (``key`` the user id) or ``deployment`` (``key`` the
    month, ``YYYY-MM``). Kept apart from the sessions, so removing a session
    does not give its spend back; it gives back its place in
    ``sessions_held`` (services/usage_caps.py).
    """

    __tablename__ = "usage_totals"

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Kept up to date but read by nothing: the session limit counts the user's
    #: sessions in progress itself (usage_caps.open_sessions). The user row is
    #: what claim_session locks.
    sessions_held: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The chat has said once that most of the cap is used.
    warned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
