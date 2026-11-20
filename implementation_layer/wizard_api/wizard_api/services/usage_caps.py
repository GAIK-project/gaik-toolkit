"""Spend caps per session, per user and per deployment month, and sessions per user.

The agent SDK reports what each query cost (its own estimate from its price
table, not the provider's bill). After every chat turn that cost is added to

- the session (``metadata["usage_cost_usd"]``), so it survives agent restarts;
- the user's row in ``usage_totals``, which a deleted session does not reduce;
- the deployment's row for the month (``usage_totals``, key ``YYYY-MM`` in UTC).

Before an agent is woken for a message, a cap that is already reached refuses
it (``check_chat``), and the agent is started with the smallest amount any cap
has left as its own budget (``remaining_budget``), so one long reply cannot run
far past a cap. Once a session or a user has used ``WIZARD_COST_WARN_RATIO`` of
its cap, the chat says so, once (``record_cost``).

Sessions per user are claimed before a session is created (``claim_session``):
one atomic statement that refuses past ``WIZARD_MAX_SESSIONS_PER_USER``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from wizard_api import config
from wizard_api.models import UsageTotal, WizardSession

logger = logging.getLogger(__name__)

USER = "user"
DEPLOYMENT = "deployment"

#: Session metadata keys, written by the server only (SERVER_OWNED_METADATA_KEYS).
SESSION_COST_KEY = "usage_cost_usd"
SESSION_WARNED_KEY = "usage_warned"

#: The refusals, in the words the API gives; the web app shows its own in the
#: user's language, chosen by ``scope``.
REFUSALS = {
    "session": (
        "This session has reached its usage limit. Its work is kept; start a new session to go on."
    ),
    USER: "Your account has reached its usage limit.",
    DEPLOYMENT: "The wizard has reached its usage limit for this month.",
}

#: Said once in the chat when most of a cap is used, in the session's language.
NOTICES = {
    "session": {
        "fi": (
            "ℹ︎ Tämän session käyttörajasta on käytetty yli {pct} %. Hyväksy portit ja "
            "aja testiajo, ennen kuin raja täyttyy."
        ),
        "en": (
            "ℹ︎ Over {pct} % of this session's usage limit is used. Approve the gates and "
            "run the test before it is full."
        ),
    },
    USER: {
        "fi": "ℹ︎ Tunnuksesi käyttörajasta on käytetty yli {pct} %.",
        "en": "ℹ︎ Over {pct} % of your account's usage limit is used.",
    },
}


class UsageCapError(RuntimeError):
    """A cap is reached. ``scope`` is ``session``, ``user`` or ``deployment``."""

    def __init__(self, scope: str, message: str | None = None):
        self.scope = scope
        super().__init__(message or REFUSALS[scope])


class SessionLimitError(RuntimeError):
    """The user has created as many sessions as they may."""


def month(now: datetime | None = None) -> str:
    """The deployment's counting period: the calendar month in UTC, ``YYYY-MM``."""
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def _spent(db: Session, scope: str, key: str) -> float:
    value = db.execute(
        select(UsageTotal.cost_usd).where(UsageTotal.scope == scope, UsageTotal.key == key)
    ).scalar_one_or_none()
    return float(value or 0.0)


def session_spent(session: WizardSession) -> float:
    try:
        return float((session.session_metadata or {}).get(SESSION_COST_KEY) or 0.0)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class _Cap:
    scope: str
    cap: float
    spent: float

    @property
    def left(self) -> float:
        return self.cap - self.spent


def _caps(db: Session, session: WizardSession, now: datetime | None = None) -> list[_Cap]:
    caps = []
    if (cap := config.session_max_cost_usd()) is not None:
        caps.append(_Cap("session", cap, session_spent(session)))
    if (cap := config.user_max_cost_usd()) is not None:
        caps.append(_Cap(USER, cap, _spent(db, USER, session.user_id)))
    if (cap := config.deployment_max_cost_usd()) is not None:
        caps.append(_Cap(DEPLOYMENT, cap, _spent(db, DEPLOYMENT, month(now))))
    return caps


def chat_budget(db: Session, session: WizardSession, now: datetime | None = None) -> float | None:
    """What the caps leave for this session's next message; None when no cap is on.

    Raises UsageCapError when a cap is reached. The deployment's cap is checked
    first: when it is reached, nobody's message goes through, and the user is
    told so rather than that their own cap is full.
    """
    caps = sorted(_caps(db, session, now), key=lambda c: c.scope != DEPLOYMENT)
    for cap in caps:
        if cap.left <= 0:
            raise UsageCapError(cap.scope)
    return min(cap.left for cap in caps) if caps else None


def claim_session(db: Session, user_id: str) -> None:
    """Count a new session for ``user_id``, or raise SessionLimitError at the limit.

    One statement, so two sessions created at the same moment cannot both take
    the last place. Committed at once: a session the caller then fails to create
    still counts, which errs on the side of the limit.
    """
    limit = config.max_sessions_per_user()
    statement = insert(UsageTotal).values(scope=USER, key=user_id, sessions_created=1)
    if limit is None:
        statement = statement.on_conflict_do_update(
            index_elements=[UsageTotal.scope, UsageTotal.key],
            set_={"sessions_created": UsageTotal.sessions_created + 1},
        )
    else:
        statement = statement.on_conflict_do_update(
            index_elements=[UsageTotal.scope, UsageTotal.key],
            set_={"sessions_created": UsageTotal.sessions_created + 1},
            where=UsageTotal.sessions_created < limit,
        )
    claimed = db.execute(statement.returning(UsageTotal.sessions_created)).scalar_one_or_none()
    db.commit()
    if claimed is None:
        raise SessionLimitError(
            f"You have started the {limit} sessions your account may have. Continue in one of them."
        )


def release_session(db: Session, user_id: str) -> None:
    """Give back a place claimed for a session that could then not be created."""
    db.rollback()
    db.execute(
        update(UsageTotal)
        .where(
            UsageTotal.scope == USER,
            UsageTotal.key == user_id,
            UsageTotal.sessions_created > 0,
        )
        .values(sessions_created=UsageTotal.sessions_created - 1)
    )
    db.commit()


def _add(db: Session, scope: str, key: str, cost: float) -> float:
    statement = insert(UsageTotal).values(scope=scope, key=key, cost_usd=cost)
    statement = statement.on_conflict_do_update(
        index_elements=[UsageTotal.scope, UsageTotal.key],
        set_={"cost_usd": UsageTotal.cost_usd + cost},
    )
    return float(db.execute(statement.returning(UsageTotal.cost_usd)).scalar_one())


def _warn_once(db: Session, scope: str, key: str) -> bool:
    """Mark the row warned; True only for the call that did it."""
    marked = db.execute(
        update(UsageTotal)
        .where(UsageTotal.scope == scope, UsageTotal.key == key, UsageTotal.warned.is_(False))
        .values(warned=True)
        .returning(UsageTotal.key)
    ).scalar_one_or_none()
    return marked is not None


def record_cost(
    db: Session,
    user_id: str,
    cost: float,
    *,
    session: WizardSession | None = None,
    now: datetime | None = None,
    warn: bool = True,
) -> list[str]:
    """Add one turn's ``cost`` everywhere it counts; return the scopes to tell the user of.

    ``session`` is None for a session deleted while its turn ran: the user's and
    the deployment's spend still grow. A scope is returned once, the first time
    its spend reaches ``WIZARD_COST_WARN_RATIO`` of its cap. The deployment's is
    logged instead, for whoever runs it. With ``warn`` false (a turn that did
    not complete, so nothing could be said) the spend is counted and no warning
    is marked as given, so the next turn gives it. Nothing is done for a cost
    that is not positive.
    """
    from wizard_api import ops_metrics
    from wizard_api.services import session_service

    if not cost or cost <= 0:
        return []
    ratio = config.cost_warn_ratio()
    notices: list[str] = []

    if session is not None:
        session_service.lock_fresh(db, session)
        metadata = dict(session.session_metadata or {})
        total = session_spent(session) + cost
        metadata[SESSION_COST_KEY] = round(total, 6)
        cap = config.session_max_cost_usd()
        if (
            warn
            and cap is not None
            and total >= ratio * cap
            and not metadata.get(SESSION_WARNED_KEY)
        ):
            metadata[SESSION_WARNED_KEY] = True
            notices.append("session")
        session.session_metadata = metadata

    user_total = _add(db, USER, user_id, cost)
    cap = config.user_max_cost_usd()
    if warn and cap is not None and user_total >= ratio * cap and _warn_once(db, USER, user_id):
        notices.append(USER)

    period = month(now)
    deployment_total = _add(db, DEPLOYMENT, period, cost)
    cap = config.deployment_max_cost_usd()
    if cap is not None and deployment_total >= ratio * cap and _warn_once(db, DEPLOYMENT, period):
        logger.warning(
            "the deployment has used %.0f %% of its monthly usage cap (%s)",
            100 * deployment_total / cap,
            period,
        )
        ops_metrics.usage_warnings.add(1, {"scope": DEPLOYMENT})
    db.commit()
    ops_metrics.usage_cost.add(cost)
    for scope in notices:
        ops_metrics.usage_warnings.add(1, {"scope": scope})
    return notices


def notice(scope: str, lang: str) -> str:
    """The chat's line for ``scope``, in ``lang`` (fi or en)."""
    texts = NOTICES[scope]
    pct = round(100 * config.cost_warn_ratio())
    return texts.get(lang, texts["en"]).format(pct=pct)
