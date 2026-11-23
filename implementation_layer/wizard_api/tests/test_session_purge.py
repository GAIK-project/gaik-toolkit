"""Sessions nobody has changed for the retention period are removed, protected ones stay."""

import io
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from helpers import requires_postgres
from wizard_api import session_admin
from wizard_api.models import WizardSession
from wizard_api.ownership import USER_HEADER

ALICE = {USER_HEADER: "alice@example.com"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("WIZARD_AGENT_STATE_DIR", raising=False)
    return tmp_path


def _create(client, title: str) -> str:
    res = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": title}, headers=ALICE
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _last_changed(db_session, session_id: str, days_ago: int, **metadata) -> None:
    db_session.expire_all()
    row = db_session.get(WizardSession, uuid.UUID(session_id))
    if metadata:
        row.session_metadata = {**row.session_metadata, **metadata}
    db_session.commit()
    # Set apart from the metadata, which would move updated_at to now.
    row.updated_at = datetime.now(UTC) - timedelta(days=days_ago)
    db_session.commit()


class _Opener:
    def __init__(self, refuse: set[str] = frozenset()) -> None:
        self.sent = []
        self.refuse = refuse

    def open(self, request, timeout):
        self.sent.append(request)
        if any(sid in request.full_url for sid in self.refuse):
            raise session_admin.urllib.error.HTTPError(
                request.full_url, 409, "busy", {}, io.BytesIO(b"session_busy")
            )
        return SimpleNamespace(close=lambda: None)


@pytest.mark.parametrize(
    ("value", "days"),
    [(None, 90), ("30", 30), ("0", 90), ("-5", 90), ("ninety", 90)],
)
def test_the_retention_period_is_90_days_unless_set(monkeypatch, value, days) -> None:
    if value is None:
        monkeypatch.delenv(session_admin.RETENTION_ENV, raising=False)
    else:
        monkeypatch.setenv(session_admin.RETENTION_ENV, value)
    assert session_admin.retention_days() == days


def test_a_period_under_one_day_is_refused() -> None:
    with pytest.raises(SystemExit):
        session_admin.main(["purge", "--older-than", "0"])


@requires_postgres
def test_the_api_accepts_retention_as_the_reason(client, root) -> None:
    sid = _create(client, "old")
    res = client.delete(f"/sessions/{sid}?reason=retention", headers=ALICE)
    assert res.status_code == 204, res.text


@requires_postgres
def test_without_apply_the_due_sessions_are_listed_and_nothing_is_sent(
    client, db_session, root, monkeypatch, capsys
) -> None:
    old = _create(client, "old")
    kept = _create(client, "kept")
    recent = _create(client, "recent")
    _last_changed(db_session, old, 91)
    _last_changed(db_session, kept, 200, protected=True)
    _last_changed(db_session, recent, 89)
    opener = _Opener()
    monkeypatch.setattr(session_admin.urllib.request, "build_opener", lambda *_a: opener)

    session_admin.main(["purge"])

    out = capsys.readouterr().out
    assert old in out
    assert kept not in out and recent not in out
    assert "alice@example.com" not in out
    assert opener.sent == []


@requires_postgres
def test_with_apply_each_due_session_goes_through_the_api_delete(
    client, db_session, root, monkeypatch
) -> None:
    old = _create(client, "old")
    older = _create(client, "older")
    kept = _create(client, "kept")
    _last_changed(db_session, old, 40)
    _last_changed(db_session, older, 60)
    _last_changed(db_session, kept, 60, protected=True)
    opener = _Opener()
    monkeypatch.setattr(session_admin.urllib.request, "build_opener", lambda *_a: opener)

    session_admin.main(["purge", "--older-than", "30", "--apply"])

    urls = [r.full_url for r in opener.sent]
    assert [u.rsplit("/", 1)[1] for u in urls] == [
        f"{older}?reason=retention",
        f"{old}?reason=retention",
    ]
    assert all(r.get_method() == "DELETE" for r in opener.sent)
    assert opener.sent[0].get_header(USER_HEADER.capitalize()) == "alice@example.com"


@requires_postgres
def test_a_refused_session_is_reported_and_the_rest_still_go(
    client, db_session, root, monkeypatch, capsys
) -> None:
    busy = _create(client, "busy")
    idle = _create(client, "idle")
    _last_changed(db_session, busy, 100)
    _last_changed(db_session, idle, 95)
    opener = _Opener(refuse={busy})
    monkeypatch.setattr(session_admin.urllib.request, "build_opener", lambda *_a: opener)

    with pytest.raises(SystemExit):
        session_admin.main(["purge", "--apply"])

    assert len(opener.sent) == 2
    out = capsys.readouterr().out
    assert f"{busy}" in out and "not deleted: 409" in out
    assert f"{idle}" in out and "deleted" in out
