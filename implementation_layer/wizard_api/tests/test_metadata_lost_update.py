"""A session's metadata is one JSONB object; a writer must not undo another's key (#253).

Observed on s4: the PoC tab showed a sandbox run as succeeded, but the api answered
409 ``no_successful_run`` for the deployable package, and ``last_successful_run`` was
missing from the session's metadata. A chat turn loads the session, works for minutes
while the agent writes the package, and then writes the *whole* metadata object back
from the copy it loaded; a run recorded in between was written over.
"""

from helpers import requires_postgres
from sqlalchemy.orm import sessionmaker
from wizard_api.schemas.session import SessionCreate, SessionUpdate
from wizard_api.services import session_service


def _factory(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


def _new_session(db_session):
    return session_service.create_session(
        db_session, SessionCreate(user_id="alice@example.com", title="t")
    ).id


def _record_run_elsewhere(factory, session_id, run_id="run-1"):
    """What ``_record_successful_run`` does: its own database session, one key."""
    with factory() as other:
        row = session_service.get_session(other, session_id)
        session_service.update_session(
            other, row, SessionUpdate(metadata={"last_successful_run": run_id})
        )


def _stored(db_session, session_id):
    row = session_service.get_session(db_session, session_id)
    db_session.refresh(row)
    return row.session_metadata


@requires_postgres
def test_a_chat_turn_finishing_after_a_run_was_recorded_keeps_the_run(db_engine, db_session):
    factory = _factory(db_engine)
    sid = _new_session(db_session)

    turn = factory()
    stale = session_service.get_session(turn, sid)  # the turn's copy, loaded before the run
    assert "last_successful_run" not in stale.session_metadata

    _record_run_elsewhere(factory, sid)
    session_service.append_messages(turn, stale, "hei", "moi")  # the turn ends
    turn.close()

    stored = _stored(db_session, sid)
    assert stored["last_successful_run"] == "run-1"
    assert [m["role"] for m in stored["messages"]] == ["user", "assistant"]


@requires_postgres
def test_advancing_the_step_from_an_old_copy_keeps_the_run(db_engine, db_session):
    factory = _factory(db_engine)
    sid = _new_session(db_session)

    turn = factory()
    stale = session_service.get_session(turn, sid)
    _record_run_elsewhere(factory, sid)
    session_service.update_session(
        turn, stale, SessionUpdate(step=2)
    )  # the turn moves the session on
    turn.close()

    stored = _stored(db_session, sid)
    assert stored["last_successful_run"] == "run-1"
    assert stored["status"]  # the step change still wrote its own key


@requires_postgres
def test_two_turns_that_both_started_before_either_finished_keep_all_messages(
    db_engine, db_session
):
    factory = _factory(db_engine)
    sid = _new_session(db_session)

    first, second = factory(), factory()
    copy_a = session_service.get_session(first, sid)
    copy_b = session_service.get_session(second, sid)

    session_service.append_messages(first, copy_a, "a1", "a2")
    first.close()
    session_service.append_messages(second, copy_b, "b1", "b2")  # copy_b predates a's messages
    second.close()

    contents = [m["content"] for m in _stored(db_session, sid)["messages"]]
    assert contents == ["a1", "a2", "b1", "b2"]


@requires_postgres
def test_recording_a_run_changes_that_key_and_leaves_the_rest(db_engine, db_session):
    factory = _factory(db_engine)
    sid = _new_session(db_session)
    row = session_service.get_session(db_session, sid)
    session_service.append_messages(db_session, row, "hei", "moi")

    _record_run_elsewhere(factory, sid, "run-2")

    stored = _stored(db_session, sid)
    assert stored["last_successful_run"] == "run-2"
    assert len(stored["messages"]) == 2
    assert stored["title"] == "t"
