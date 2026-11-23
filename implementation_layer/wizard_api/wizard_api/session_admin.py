"""Operator commands for sessions, run in the api pod.

    python -m wizard_api.session_admin list <owner id or e-mail>
    python -m wizard_api.session_admin delete <session id> --reason data-subject-request
    python -m wizard_api.session_admin protect <session id> [--off]
    python -m wizard_api.session_admin export <owner id or e-mail> --out <folder>
    python -m wizard_api.session_admin purge [--older-than <days>] [--apply]
    python -m wizard_api.session_admin prune-runs [--keep <n>] [--apply]
    python -m wizard_api.session_admin owner-id <e-mail>
    python -m wizard_api.session_admin move-owners [--apply]

Sessions are owned by an owner id (``wizard_api.owner_id``), not the e-mail
address. ``list`` and ``export`` take either: given an address, they look under
its owner id, which needs the web app's key in the environment
(``WIZARD_PSEUDONYM_KEY``, else ``NEXT_SERVER_ACTIONS_ENCRYPTION_KEY``), and
under the address itself for sessions not yet moved. ``owner-id`` prints the id
for an address. ``move-owners`` lists the sessions still saved under an address
and, with ``--apply``, moves each to its owner id; it needs the key, since an id
made with another key would hide the sessions from their owner. The web app
also moves a user's sessions on their first request, so this is for the ones
whose owners have not been back.

``delete`` goes through the running API, because that process owns the live
agents: it refuses a session in mid-turn and ends the agent before removing it.

``purge`` lists the sessions nobody has changed for the retention period
(``WIZARD_SESSION_RETENTION_DAYS``, 90 days unless set) and leaves protected
ones out. It only lists them unless ``--apply`` is given; then each goes through
the same API delete as ``delete``, with the reason ``retention``. A session the
API refuses (in mid-turn, protected meanwhile) is reported and left for the
next purge.

``prune-runs`` keeps the sessions volume from filling up with test runs. In each
session it keeps the newest ``--keep`` run folders (3 unless given) and the run
the session points to as its latest, and lists the older ones; ``--apply``
removes them. A removed run's log and output files are gone; the session, its
package and its latest result stay.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from wizard_api import config, owner_id
from wizard_api.db import SessionLocal
from wizard_api.models import WizardSession
from wizard_api.ownership import USER_HEADER
from wizard_api.schemas.session import SessionUpdate
from wizard_api.security import SERVICE_TOKEN_HEADER
from wizard_api.services import run_context, session_export, session_removal, session_service

REASONS = ("data-subject-request", "owner-left", "other")
RETENTION_REASON = "retention"
RETENTION_ENV = "WIZARD_SESSION_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 90


def retention_days() -> int:
    """The days a session is kept after its last change; a bad value is the default."""
    try:
        days = int(os.getenv(RETENTION_ENV, ""))
    except ValueError:
        return DEFAULT_RETENTION_DAYS
    return days if days > 0 else DEFAULT_RETENTION_DAYS


def _api_url() -> str:
    return os.getenv("WIZARD_API_LOCAL_URL", "http://127.0.0.1:8100").rstrip("/")


def _find(db, session_id: str):
    session = session_service.get_session(db, uuid.UUID(session_id))
    if session is None:
        sys.exit(f"no session {session_id}")
    return session


def _key_or_exit() -> str:
    key = owner_id.owner_key()
    if not key:
        sys.exit(
            "set WIZARD_PSEUDONYM_KEY (or NEXT_SERVER_ACTIONS_ENCRYPTION_KEY) to the web app's key"
        )
    return key


def owners_for(user: str) -> list[str]:
    """The user ids to look under: an owner id as given; for an address, its
    owner id (when the key is set) and the address itself (not yet moved)."""
    if not owner_id.is_address(user):
        return [user]
    key = owner_id.owner_key()
    if not key:
        print("no key set: only sessions not yet moved to an owner id are shown", file=sys.stderr)
        return [user]
    return [owner_id.owner_id(user, key), user]


def _sessions_of(db, user: str) -> list[WizardSession]:
    found: list[WizardSession] = []
    for owner in owners_for(user):
        found.extend(session_service.list_sessions(db, owner))
    return found


def list_sessions(user_id: str) -> None:
    with SessionLocal() as db:
        sessions = _sessions_of(db, user_id)
        for session in sessions:
            kept = " protected" if session_removal.is_protected(session) else ""
            updated = session.updated_at.date().isoformat()
            title = session.session_metadata.get("title", "")
            print(f"{session.id}  {updated}{kept}  {title}")
        print(f"{len(sessions)} session(s)")


def _send_delete(session_id: str, owner: str, reason: str) -> str | None:
    """Asks the running API to delete the session; the refusal, if it refused."""
    query = urllib.parse.urlencode({"reason": reason})
    headers = {USER_HEADER: owner}
    token = config.get_service_token()
    if token:
        headers[SERVICE_TOKEN_HEADER] = token
    request = urllib.request.Request(
        f"{_api_url()}/sessions/{session_id}?{query}", method="DELETE", headers=headers
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        opener.open(request, timeout=120).close()
    except urllib.error.HTTPError as exc:
        return f"{exc.code} {exc.read().decode(errors='replace')[:300]}"
    return None


def delete(session_id: str, reason: str) -> None:
    with SessionLocal() as db:
        owner = _find(db, session_id).user_id
    refused = _send_delete(session_id, owner, reason)
    if refused:
        sys.exit(f"not deleted: {refused}")
    print(f"deleted {session_id}")


def due_for_removal(db, days: int, now: datetime | None = None) -> list[WizardSession]:
    """Unprotected sessions last changed more than ``days`` ago, oldest first."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    stmt = (
        select(WizardSession)
        .where(WizardSession.updated_at < cutoff)
        .order_by(WizardSession.updated_at)
    )
    return [s for s in db.scalars(stmt).all() if not session_removal.is_protected(s)]


def purge(days: int, apply: bool) -> None:
    # Only the id and the date are printed: the output may end up in a job log.
    with SessionLocal() as db:
        due = [(str(s.id), s.user_id, s.updated_at.date()) for s in due_for_removal(db, days)]
    refused = 0
    for session_id, owner, updated in due:
        if not apply:
            print(f"{session_id}  {updated}  due")
            continue
        problem = _send_delete(session_id, owner, RETENTION_REASON)
        if problem:
            refused += 1
            print(f"{session_id}  {updated}  not deleted: {problem}")
        else:
            print(f"{session_id}  {updated}  deleted")
    done = "deleted" if apply else "due (nothing deleted without --apply)"
    print(f"{len(due) - refused} session(s) {done}, older than {days} days")
    if refused:
        sys.exit(f"{refused} session(s) not deleted; the next purge tries them again")


def protect(session_id: str, on: bool) -> None:
    with SessionLocal() as db:
        session = _find(db, session_id)
        session_service.update_session(
            db, session, SessionUpdate(metadata={session_removal.PROTECTED_KEY: on})
        )
    print(f"{session_id} protected={on}")


def export(user_id: str, out: str) -> None:
    """One zip per session of the user, for a request to see their data."""
    os.makedirs(out, exist_ok=True)
    with SessionLocal() as db:
        sessions = _sessions_of(db, user_id)
        for session in sessions:
            with open(os.path.join(out, f"session-{session.id}.zip"), "wb") as target:
                session_export.write_archive(session, target)
    print(f"{len(sessions)} session(s) exported to {out}")


def legacy_owners(db) -> list[str]:
    """The e-mail addresses sessions are still saved under."""
    users = db.scalars(select(WizardSession.user_id).distinct()).all()
    return sorted(u for u in users if owner_id.is_address(u))


def move_owners(apply: bool) -> None:
    # Addresses are not printed: the output may end up in a job log.
    key = _key_or_exit()
    moved = 0
    with SessionLocal() as db:
        legacy = legacy_owners(db)
        for user in legacy:
            owner = owner_id.owner_id(user, key)
            if apply:
                count = session_service.move_owner(db, user, owner)
            else:
                count = len(session_service.list_sessions(db, user))
            print(f"{owner}  {count} session(s) {'moved' if apply else 'to move'}")
            moved += count
    done = "moved" if apply else "to move (nothing moved without --apply)"
    print(f"{moved} session(s) of {len(legacy)} user(s) {done}")


def _size(path: str) -> int:
    total = 0
    for folder, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(folder, name)).st_size
            except OSError:
                pass
    return total


def runs_to_prune(session: WizardSession, keep: int) -> list[str]:
    """The session's run folders past the newest ``keep``, never its latest run."""
    runs = os.path.join(session.output_dir, run_context.RUNS_DIR)
    try:
        entries = [e for e in os.scandir(runs) if e.is_dir(follow_symlinks=False)]
    except FileNotFoundError:
        return []
    entries.sort(key=lambda e: e.stat(follow_symlinks=False).st_mtime, reverse=True)
    latest = session.session_metadata.get("latest_run")
    return [e.path for e in entries[keep:] if e.name != latest]


def prune_runs(keep: int, apply: bool) -> None:
    removed = freed = 0
    with SessionLocal() as db:
        sessions = list(db.scalars(select(WizardSession)).all())
        for session in sessions:
            old = runs_to_prune(session, keep)
            if not old:
                continue
            size = sum(_size(path) for path in old)
            if apply:
                for path in old:
                    shutil.rmtree(path, ignore_errors=True)
            state = "removed" if apply else "to remove"
            print(f"{session.id}  {len(old)} run(s) {state}, {size // 1024} KiB")
            removed += len(old)
            freed += size
    done = "removed" if apply else "to remove (nothing removed without --apply)"
    print(
        f"{removed} run folder(s) {done}, {freed // (1024 * 1024)} MiB, keeping {keep} per session"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="session_admin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list").add_argument("user_id")
    delete_args = commands.add_parser("delete")
    delete_args.add_argument("session_id")
    delete_args.add_argument("--reason", choices=REASONS, required=True)
    protect_args = commands.add_parser("protect")
    protect_args.add_argument("session_id")
    protect_args.add_argument("--off", action="store_true")
    export_args = commands.add_parser("export")
    export_args.add_argument("user_id")
    export_args.add_argument("--out", required=True)
    purge_args = commands.add_parser("purge")
    purge_args.add_argument("--older-than", type=int, default=None, metavar="DAYS")
    purge_args.add_argument("--apply", action="store_true")
    prune_args = commands.add_parser("prune-runs")
    prune_args.add_argument("--keep", type=int, default=3)
    prune_args.add_argument("--apply", action="store_true")
    commands.add_parser("owner-id").add_argument("email")
    commands.add_parser("move-owners").add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "owner-id":
        print(owner_id.owner_id(args.email, _key_or_exit()))
        return
    if args.command == "move-owners":
        move_owners(args.apply)
        return
    if args.command == "list":
        list_sessions(args.user_id)
    elif args.command == "delete":
        delete(args.session_id, args.reason)
    elif args.command == "export":
        export(args.user_id, args.out)
    elif args.command == "prune-runs":
        if args.keep < 1:
            parser.error("--keep must be at least 1")
        prune_runs(args.keep, args.apply)
    elif args.command == "purge":
        days = args.older_than if args.older_than is not None else retention_days()
        if days < 1:
            parser.error("--older-than must be at least 1")
        purge(days, args.apply)
    else:
        protect(args.session_id, not args.off)


if __name__ == "__main__":
    main()
