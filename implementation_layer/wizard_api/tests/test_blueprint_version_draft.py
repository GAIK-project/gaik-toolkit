"""Every blueprint version keeps the full draft it was made from, when there is one.

The reduced blueprint (``content``) is what the API serves; the agent's full draft
(``use_case.blueprint.json``) holds everything the reduction drops. Undo, version
restore and the backfill need the full draft of each version, so it is stored next
to the content.
"""

import copy
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from helpers import requires_postgres
from sqlalchemy import create_engine, inspect, make_url, text
from test_artifact_sync import DRAFT, write_draft
from wizard_api import config as wizard_config
from wizard_api.services import artifact_sync, blueprint_service, session_service

pytestmark = requires_postgres

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def _session(client, db_session):
    created = client.post("/sessions", json={"user_id": "draft-user", "title": "Drafts"}).json()
    return session_service.get_session(db_session, uuid.UUID(created["id"]))


def test_an_adopted_agent_draft_is_stored_with_its_version(client, db_session) -> None:
    session = _session(client, db_session)
    write_draft(session.output_dir, DRAFT)

    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is True

    active = blueprint_service.get_active_version(db_session, session)
    assert active.version == 2
    assert active.draft == DRAFT
    assert blueprint_service.get_active_draft(db_session, session) == DRAFT


def test_a_draft_passed_in_is_the_one_stored(client, db_session) -> None:
    session = _session(client, db_session)
    draft = copy.deepcopy(DRAFT)
    draft["use_case"]["name"] = "Passed in"

    assert artifact_sync.sync_blueprint_from_draft(db_session, session, draft) is True

    assert blueprint_service.get_active_draft(db_session, session) == draft


def test_a_version_without_a_draft_keeps_null(client, db_session) -> None:
    session = _session(client, db_session)
    seed = blueprint_service.get_active_version(db_session, session)
    assert seed.draft is None

    content = {**seed.content, "name": "Edited by the user"}
    version = blueprint_service.add_version(db_session, session, note="edit", content=content)
    db_session.commit()
    db_session.refresh(version)

    assert version.draft is None
    assert blueprint_service.get_active_draft(db_session, session) is None
    # SQL NULL, not a JSON null: "versions with a draft" is a ``draft IS NOT NULL`` query.
    stored = db_session.execute(
        text("SELECT draft IS NULL FROM blueprint_versions WHERE id = :id"), {"id": version.id}
    ).scalar_one()
    assert stored is True


def test_add_version_stores_the_draft_given(client, db_session) -> None:
    session = _session(client, db_session)
    seed = blueprint_service.get_active_version(db_session, session)

    version = blueprint_service.add_version(
        db_session, session, note="with draft", content=seed.content, draft=DRAFT
    )
    db_session.commit()
    db_session.refresh(version)

    assert version.draft == DRAFT


def test_no_active_version_has_no_draft(client, db_session) -> None:
    session = _session(client, db_session)
    session.active_version = 99
    db_session.commit()

    assert blueprint_service.get_active_draft(db_session, session) is None
    assert blueprint_service.get_previous_draft_version(db_session, session) is None


def test_the_previous_draft_version_skips_versions_without_a_draft(client, db_session) -> None:
    session = _session(client, db_session)  # v1: the seed, no draft
    content = blueprint_service.get_active_version(db_session, session).content
    first = {**DRAFT, "use_case": {**DRAFT["use_case"], "name": "First"}}
    blueprint_service.add_version(db_session, session, note="v2", content=content, draft=first)
    db_session.commit()
    blueprint_service.add_version(db_session, session, note="v3", content=content)
    db_session.commit()
    blueprint_service.add_version(db_session, session, note="v4", content=content, draft=DRAFT)
    db_session.commit()

    previous = blueprint_service.get_previous_draft_version(db_session, session)
    assert previous is not None
    assert previous.version == 2
    assert previous.draft == first

    # Nothing older than v2 carries a draft.
    session.active_version = 2
    db_session.commit()
    assert blueprint_service.get_previous_draft_version(db_session, session) is None


def test_the_migration_adds_and_drops_the_column(monkeypatch) -> None:
    """Runs Alembic in a throwaway schema of its own, created and dropped here.

    The suite's own tables come from ``Base.metadata.create_all``, so the
    migrations never run against them; the schema this test migrates is named
    in the connection's search_path and removed at the end.
    """
    base_url = make_url(wizard_config.get_database_url())
    schema = f"wizard_migration_{uuid.uuid4().hex[:12]}"
    url = base_url.update_query_dict({"options": f"-csearch_path={schema}"})
    admin = create_engine(base_url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url)
    monkeypatch.setattr(
        wizard_config, "get_database_url", lambda: url.render_as_string(hide_password=False)
    )
    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(ALEMBIC_DIR))

    def columns() -> set[str]:
        return {c["name"] for c in inspect(engine).get_columns("blueprint_versions", schema)}

    try:
        command.upgrade(alembic_config, "004")
        assert "draft" in columns()
        draft = next(
            c
            for c in inspect(engine).get_columns("blueprint_versions", schema)
            if c["name"] == "draft"
        )
        assert draft["nullable"] is True

        command.downgrade(alembic_config, "003")
        assert "draft" not in columns()
        assert "content" in columns()
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
