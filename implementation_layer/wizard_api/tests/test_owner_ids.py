"""Sessions are owned by an owner id, not the e-mail address, and the old ones move over."""

import uuid

import pytest
from helpers import requires_postgres
from wizard_api import owner_id, session_admin
from wizard_api.models import WizardSession
from wizard_api.ownership import USER_HEADER

ADDRESS = "Alice.Example@Example.test"
KEY = "key-one"
# The same vector is in solution_wizard_v2/lib/owner-id.test.ts: the web app and
# the admin commands must give one address the same owner id.
VECTOR = "o_f1520e92ff2e1f898cf5595f579d3801"
OWNER = owner_id.owner_id(ADDRESS, KEY)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("WIZARD_AGENT_STATE_DIR", raising=False)
    for name in owner_id.KEY_ENVS:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _create(client, user: str, title: str = "Invoices") -> str:
    res = client.post(
        "/sessions", json={"user_id": user, "title": title}, headers={USER_HEADER: user}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _claim(client, owner: str, legacy: str):
    return client.post(
        "/owners/claim", json={"legacy_user_id": legacy}, headers={USER_HEADER: owner}
    )


def test_the_owner_id_matches_the_web_apps_and_holds_no_address() -> None:
    assert OWNER == VECTOR
    assert owner_id.owner_id("  alice.example@example.test ", KEY) == VECTOR
    assert owner_id.owner_id(ADDRESS, "key-two") != VECTOR
    assert owner_id.is_owner_id(VECTOR) and "alice" not in VECTOR
    assert owner_id.is_address(ADDRESS) and not owner_id.is_address(VECTOR)


@requires_postgres
def test_a_new_session_under_an_owner_id_keeps_the_address_out_of_its_row_and_folder(
    client, db_session, root
) -> None:
    session_id = _create(client, OWNER)
    row = db_session.get(WizardSession, uuid.UUID(session_id))
    assert row.user_id == OWNER
    assert "@" not in row.output_dir and OWNER in row.output_dir


@requires_postgres
def test_the_users_old_sessions_move_to_their_owner_id_and_keep_their_date(
    client, db_session, root
) -> None:
    mine = _create(client, ADDRESS)
    theirs = _create(client, "bob@example.test")
    db_session.expire_all()
    before = db_session.get(WizardSession, uuid.UUID(mine)).updated_at

    res = _claim(client, OWNER, ADDRESS)
    assert res.status_code == 200, res.text
    assert res.json() == {"moved": 1}

    listed = client.get("/sessions", params={"user_id": OWNER}, headers={USER_HEADER: OWNER})
    assert [s["id"] for s in listed.json()["sessions"]] == [mine]
    assert client.get(f"/sessions/{mine}", headers={USER_HEADER: OWNER}).status_code == 200
    assert client.get(f"/sessions/{mine}", headers={USER_HEADER: ADDRESS}).status_code == 404
    db_session.expire_all()
    assert db_session.get(WizardSession, uuid.UUID(mine)).updated_at == before
    assert db_session.get(WizardSession, uuid.UUID(theirs)).user_id == "bob@example.test"
    assert _claim(client, OWNER, ADDRESS).json() == {"moved": 0}


@requires_postgres
@pytest.mark.parametrize(
    ("owner", "legacy", "status"),
    [
        (ADDRESS, ADDRESS, 400),  # the header must be an owner id
        (None, ADDRESS, 400),
        (OWNER, "not-an-address", 422),
        (OWNER, VECTOR, 422),
    ],
)
def test_a_claim_needs_an_owner_id_and_an_address(client, root, owner, legacy, status) -> None:
    headers = {USER_HEADER: owner} if owner else {}
    res = client.post("/owners/claim", json={"legacy_user_id": legacy}, headers=headers)
    assert res.status_code == status, res.text


@requires_postgres
def test_move_owners_needs_the_key_and_moves_only_with_apply(
    client, db_session, root, monkeypatch, capsys
) -> None:
    session_id = _create(client, ADDRESS)
    with pytest.raises(SystemExit, match="WIZARD_PSEUDONYM_KEY"):
        session_admin.main(["move-owners", "--apply"])

    monkeypatch.setenv("WIZARD_PSEUDONYM_KEY", KEY)
    session_admin.main(["move-owners"])
    db_session.expire_all()
    assert db_session.get(WizardSession, uuid.UUID(session_id)).user_id == ADDRESS

    session_admin.main(["move-owners", "--apply"])
    db_session.expire_all()
    assert db_session.get(WizardSession, uuid.UUID(session_id)).user_id == OWNER
    out = capsys.readouterr().out
    assert "1 session(s) of 1 user(s) moved" in out
    assert "@" not in out.lower().replace("(s)", "")


@requires_postgres
def test_list_by_address_finds_moved_and_unmoved_sessions(
    client, db_session, root, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("WIZARD_PSEUDONYM_KEY", KEY)
    _create(client, OWNER, "Moved")
    _create(client, ADDRESS, "Not yet moved")
    session_admin.main(["list", ADDRESS])
    out = capsys.readouterr().out
    assert "Moved" in out and "Not yet moved" in out and "2 session(s)" in out

    session_admin.main(["owner-id", ADDRESS])
    assert capsys.readouterr().out.strip() == VECTOR
