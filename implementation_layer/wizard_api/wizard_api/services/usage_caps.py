"""Spend caps per session, per user and per deployment month, and sessions per user.

The agent SDK reports what each query cost (its own estimate from its price
table, not the provider's bill). After every chat turn that cost is added to

- the session (``metadata["usage_cost_usd"]``), so it survives agent restarts;
- the user's row in ``usage_totals``, which a deleted session does not reduce;
- the deployment's row for the month (``usage_totals``, key ``YYYY-MM`` in UTC).

Before an agent is woken for a message, a cap that is already reached, or
leaves less than ``MIN_TURN_BUDGET_USD``, refuses it, and the agent is started
with the smallest amount any cap has left as its own budget (``reserve``), so
one long reply cannot run far past a cap. That budget is held against the
user's cap until the reply is charged, so replies in several sessions at once
cannot each spend what is left. Once a session or a user has used
``WIZARD_COST_WARN_RATIO`` of its cap, the chat says so, once (``record_cost``).

Sessions in progress per user are counted before a session is created
(``claim_session``), under a lock on the user's row, and refused past
``WIZARD_MAX_SESSIONS_PER_USER``. A finished session (Gate 4 approved) holds no
place; a removed one gives its place back, not its spend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from wizard_api import config
from wizard_api.models import UsageTotal, WizardSession
from wizard_api.session_state import GATE_KEYS

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


#: Below this much left, in USD, a message is refused as if the cap were reached:
#: a new agent's setup alone costs more, and the reply would stop at once.
MIN_TURN_BUDGET_USD = 0.1


class UsageCapError(RuntimeError):
    """A cap is reached. ``scope`` is ``session``, ``user`` or ``deployment``."""

    def __init__(self, scope: str, message: str | None = None):
        self.scope = scope
        super().__init__(message or REFUSALS[scope])


class UsageReservedError(RuntimeError):
    """What the user's cap leaves is held by their other replies still running."""

    def __init__(self) -> None:
        super().__init__(
            "Your other replies that are still running hold what is left of your usage "
            "limit. Send your message again when they are done."
        )


class SessionLimitError(RuntimeError):
    """The user has as many sessions as they may."""


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


def caps_left(db: Session, session: WizardSession, now: datetime | None = None) -> list[_Cap]:
    """The caps that are on, with what each has left; raises UsageCapError for a reached one.

    A cap leaving less than ``MIN_TURN_BUDGET_USD`` counts as reached. The
    deployment's cap is checked first: when it is reached, nobody's message
    goes through, and the user is told so rather than that their own cap is full.
    """
    caps = sorted(_caps(db, session, now), key=lambda c: c.scope != DEPLOYMENT)
    for cap in caps:
        if cap.left < MIN_TURN_BUDGET_USD:
            raise UsageCapError(cap.scope)
    return caps


def budget_of(caps: list[_Cap], reserved: float = 0.0) -> float | None:
    """The budget ``caps`` leave for a reply; None when no cap is on.

    ``reserved`` is what the user's other running replies were given and have
    not yet been charged for: it is taken off what the user's cap leaves.
    Raises UsageReservedError when that leaves too little while they run.
    """
    if not caps:
        return None
    lefts = []
    for cap in caps:
        left = cap.left - reserved if cap.scope == USER else cap.left
        if left < MIN_TURN_BUDGET_USD:
            raise UsageReservedError()
        lefts.append(left)
    return min(lefts)


def chat_budget(
    db: Session, session: WizardSession, now: datetime | None = None, *, reserved: float = 0.0
) -> float | None:
    """What the caps leave for this session's next message; None when no cap is on."""
    return budget_of(caps_left(db, session, now), reserved)


#: Budgets given to replies still running, by user, not yet charged (``reserve``).
#: In the process: one API process holds every live agent.
_RESERVED: dict[str, float] = {}


@dataclass
class Reservation:
    """The budget a reply was given, held against its user's cap until it is charged."""

    user_id: str
    amount: float
    budget: float | None
    released: bool = False

    def release(self) -> None:
        """Give the budget back; the reply's real cost is recorded by then. Safe to repeat."""
        if self.released or not self.amount:
            return
        self.released = True
        left = _RESERVED.get(self.user_id, 0.0) - self.amount
        if left > 1e-9:
            _RESERVED[self.user_id] = left
        else:
            _RESERVED.pop(self.user_id, None)


def reserve(user_id: str, caps: list[_Cap]) -> Reservation:
    """Give a reply its budget and hold it against ``user_id``'s cap.

    Called on the event loop with no await between reading what is held and
    holding more, so two messages at once cannot both get the same money; a
    reply whose agent is still starting is held like a running one. Release it
    once the reply's cost is recorded, or when the message is refused.
    """
    budget = budget_of(caps, _RESERVED.get(user_id, 0.0))
    amount = budget if budget is not None and any(c.scope == USER for c in caps) else 0.0
    if amount:
        _RESERVED[user_id] = _RESERVED.get(user_id, 0.0) + amount
    return Reservation(user_id, amount, budget)


def open_sessions(db: Session, user_id: str) -> int:
    """``user_id``'s sessions still in progress: every one with a gate not approved.

    A session is done only when all four gates are approved; one with a gate
    reopened, or approved out of order, still holds its place.
    """
    gates = WizardSession.gate_statuses
    finished = and_(
        *(func.coalesce(gates[key].astext, "pending") == "approved" for key in GATE_KEYS)
    )
    return int(
        db.scalar(
            select(func.count())
            .select_from(WizardSession)
            .where(WizardSession.user_id == user_id, not_(finished))
        )
        or 0
    )


def claim_session(db: Session, user_id: str) -> None:
    """Make room for a new session of ``user_id``, or raise SessionLimitError at the limit.

    The limit counts sessions in progress (``open_sessions``): one with all
    four gates approved is done and holds no place, until a gate of it is
    reopened. The limit is checked here, when a session starts: reopening a
    finished session is not refused, so a user can then have more in progress.
    The user's row is locked first and stays locked, uncommitted, until the
    caller has created the session and committed: a second session started at
    the same moment waits, then counts the first, so two cannot both take the
    last place. On a refusal nothing is left behind; a caller whose creation
    fails rolls back.
    """
    limit = config.max_sessions_per_user()
    statement = insert(UsageTotal).values(scope=USER, key=user_id, sessions_held=1)
    statement = statement.on_conflict_do_update(
        index_elements=[UsageTotal.scope, UsageTotal.key],
        set_={"sessions_held": UsageTotal.sessions_held + 1, "updated_at": func.now()},
    )
    db.execute(statement)
    if limit is not None and open_sessions(db, user_id) >= limit:
        db.rollback()
        raise SessionLimitError(
            f"Your account has {limit} sessions in progress, as many as it may. "
            "Finish one (approve its last gate) or remove one to start a new session."
        )


def release_session(db: Session, user_id: str) -> None:
    """Give back the place of a removed session, in the caller's transaction."""
    db.execute(
        update(UsageTotal)
        .where(
            UsageTotal.scope == USER,
            UsageTotal.key == user_id,
            UsageTotal.sessions_held > 0,
        )
        .values(sessions_held=UsageTotal.sessions_held - 1, updated_at=func.now())
    )


def move_user(db: Session, old_id: str, new_id: str) -> None:
    """Merge ``old_id``'s spend and sessions into ``new_id``, in the caller's transaction.

    For sessions moved to a new owner id (session_service.move_owner): the
    person is the same, so their spend and their places go with them.
    """
    row = db.execute(
        select(UsageTotal)
        .where(UsageTotal.scope == USER, UsageTotal.key == old_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or old_id == new_id:
        return
    statement = insert(UsageTotal).values(
        scope=USER,
        key=new_id,
        cost_usd=row.cost_usd,
        sessions_held=row.sessions_held,
        warned=row.warned,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[UsageTotal.scope, UsageTotal.key],
        set_={
            "cost_usd": UsageTotal.cost_usd + statement.excluded.cost_usd,
            "sessions_held": UsageTotal.sessions_held + statement.excluded.sessions_held,
            "warned": or_(UsageTotal.warned, statement.excluded.warned),
            "updated_at": func.now(),
        },
    )
    db.execute(statement)
    db.delete(row)


def _add(db: Session, scope: str, key: str, cost: float) -> float:
    statement = insert(UsageTotal).values(scope=scope, key=key, cost_usd=cost)
    statement = statement.on_conflict_do_update(
        index_elements=[UsageTotal.scope, UsageTotal.key],
        set_={"cost_usd": UsageTotal.cost_usd + cost, "updated_at": func.now()},
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


def usage_stats(db: Session, now: datetime | None = None) -> dict[str, float]:
    """For the ops gauges: the month's spend, users past the warning share but below
    their cap (near), and users at it (reached)."""
    stats = {"deployment_spent": _spent(db, DEPLOYMENT, month(now))}
    cap = config.user_max_cost_usd()
    if cap is not None:
        near = cap * config.cost_warn_ratio()
        reached = cap - MIN_TURN_BUDGET_USD
        for state, low, high in (("near", near, reached), ("reached", reached, None)):
            query = (
                select(func.count())
                .select_from(UsageTotal)
                .where(UsageTotal.scope == USER, UsageTotal.cost_usd >= low)
            )
            if high is not None:
                query = query.where(UsageTotal.cost_usd < high)
            stats[f"users_{state}"] = float(db.scalar(query) or 0)
    return stats


def notice(scope: str, lang: str) -> str:
    """The chat's line for ``scope``, in ``lang`` (fi or en)."""
    texts = NOTICES[scope]
    pct = round(100 * config.cost_warn_ratio())
    return texts.get(lang, texts["en"]).format(pct=pct)
