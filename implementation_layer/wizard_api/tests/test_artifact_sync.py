"""#141 — the agent's on-disk artifacts reach the session the UI reads."""

import asyncio
import json
import os
import uuid

import pytest
from helpers import requires_postgres
from wizard_api.services import agent_service, artifact_sync, bpmn_service, session_service

requires_solution_wizard = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

DRAFT = {
    "use_case": {
        "id": "incident_reports",
        "name": "Incident report generation",
        "description": "Turn maintenance notes into structured incident reports.",
        "domain": "maintenance",
    },
    "business_spec": {
        "current_process": "Technicians write free-form notes.",
        "poc_goal": "Show that a report can be produced from one note.",
    },
    "technical_spec": {"integration_targets": ["Maximo"]},
    "target_output_spec": {
        "schema_name": "IncidentReport",
        "fields": ["asset_id", "severity", "summary"],
        "field_types": {"asset_id": "str", "severity": "str", "summary": "str"},
        "required_fields": ["asset_id", "severity"],
        "optional_fields": ["summary"],
        "field_descriptions": {"asset_id": "Asset the incident concerns"},
        "allowed_values": {"severity": ["low", "high"]},
        "missing_value_policy": "leave_empty",
        "validation_rules": ["asset_id matches ^A-[0-9]+$"],
    },
    "workflow": {
        "steps": [
            {"id": "collect", "name": "Collect note", "type": "user_task"},
            {
                "id": "extract",
                "name": "Extract fields",
                "type": "automated_task",
                "component": "StructuredDataExtractor",
                "parameters": {"schema_ref": "schemas/output_schema.py", "retries": 2},
            },
            {"id": "review", "name": "Technician review", "type": "human_review"},
            {"id": "branch", "name": "Severity check", "type": "decision"},
        ]
    },
    "assumptions": [{"id": "a1", "text": "Notes are in Finnish", "status": "unconfirmed"}],
}


def write_draft(tmp_path, draft) -> str:
    path = os.path.join(tmp_path, artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(draft, fh)
    return str(tmp_path)


def test_reads_the_draft_and_maps_it_to_the_v2_blueprint(tmp_path) -> None:
    output_dir = write_draft(tmp_path, DRAFT)
    draft = artifact_sync.read_draft_blueprint(output_dir)
    assert draft is not None

    blueprint = artifact_sync.blueprint_from_draft(draft)
    assert blueprint is not None
    assert blueprint.name == "Incident report generation"
    assert blueprint.goal.startswith("Show that a report")
    assert blueprint.integration_targets == ["Maximo"]

    # V1 step types map onto the three V2 types; `decision` has no V2
    # equivalent and must still appear rather than vanish from the flow.
    assert [(s["id"], s["type"]) for s in blueprint.steps] == [
        ("collect", "io"),
        ("extract", "ai"),
        ("review", "human_review"),
        ("branch", "ai"),
    ]
    extract = blueprint.steps[1]
    assert extract["component"] == "StructuredDataExtractor"
    # Parameters become the settings the SME asked to see (SME-4), stringified.
    assert extract["settings"] == {"schema_ref": "schemas/output_schema.py", "retries": "2"}


def test_missing_or_malformed_draft_is_not_fatal(tmp_path) -> None:
    assert artifact_sync.read_draft_blueprint(str(tmp_path)) is None
    assert artifact_sync.read_draft_blueprint("") is None

    half_written = os.path.join(tmp_path, artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(half_written, "w", encoding="utf-8") as fh:
        fh.write('{"use_case": {"name": "Incid')
    assert artifact_sync.read_draft_blueprint(str(tmp_path)) is None


def test_a_draft_without_a_workflow_does_not_replace_the_blueprint(tmp_path) -> None:
    # Early drafts carry business framing only; adopting one would wipe the
    # blueprint to an empty flow.
    output_dir = write_draft(tmp_path, {"use_case": {"name": "Early"}, "business_spec": {}})
    draft = artifact_sync.read_draft_blueprint(output_dir)
    assert artifact_sync.blueprint_from_draft(draft) is None


def test_target_output_spec_comes_from_the_draft(tmp_path) -> None:
    draft = artifact_sync.read_draft_blueprint(write_draft(tmp_path, DRAFT))
    spec = artifact_sync.target_output_spec_from_draft(draft)
    assert spec is not None
    assert spec.schema_name == "IncidentReport"
    assert spec.fields == ["asset_id", "severity", "summary"]
    assert spec.required_fields == ["asset_id", "severity"]
    assert spec.allowed_values == {"severity": ["low", "high"]}
    assert spec.missing_value_policy == "leave_empty"

    # No fields agreed yet → nothing to show.
    empty = artifact_sync.read_draft_blueprint(
        write_draft(tmp_path, {"target_output_spec": {"schema_name": "X"}})
    )
    assert artifact_sync.target_output_spec_from_draft(empty) is None


@requires_postgres
def test_chat_turn_adopts_the_draft_blueprint(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "sync-user", "title": "Seeded"}).json()
    session_id = created["id"]
    assert created["blueprint"]["steps"][0]["id"] == "input"  # seed blueprint
    assert created["active_version"] == 1

    session = session_service.get_session(db_session, uuid.UUID(session_id))
    write_draft(session.output_dir, DRAFT)

    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is True

    detail = client.get(f"/sessions/{session_id}").json()
    assert detail["active_version"] == 2
    assert detail["blueprint"]["name"] == "Incident report generation"
    assert [s["id"] for s in detail["blueprint"]["steps"]] == [
        "collect",
        "extract",
        "review",
        "branch",
    ]
    # The Specification view's field schema and Gate 1's framing come from the
    # same draft, so they arrive with it.
    assert detail["target_output_spec"]["schema_name"] == "IncidentReport"
    assert detail["business_context"]["current_process"].startswith("Technicians")

    # An unchanged draft must not add a version per chat turn.
    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is False
    assert client.get(f"/sessions/{session_id}").json()["active_version"] == 2


def test_business_values_written_as_one_string_are_kept() -> None:
    """The blueprint template gives expected_value as a list, but the agent
    sometimes writes one sentence as a plain string. Dropping it left Gate 1
    saying "Puuttuu: Odotettu arvo" with the approve button disabled, while the
    conversation had answered it (found in a live UC02 run)."""
    ctx = session_service._business_context_from_draft(
        {
            "business_spec": {
                "expected_value": "Faster, more consistent order entry.",
                "pain_points": ["Manual entry is slow", "  "],
                "reviewers": "  ",
            }
        }
    )
    assert ctx is not None
    assert ctx.expected_value == ["Faster, more consistent order entry."]
    assert ctx.pain_points == ["Manual entry is slow"]
    assert ctx.reviewers == []


# ---------------------------------------------------------------------------
# The step follows the agent after Gate 1 (#169)
# ---------------------------------------------------------------------------


def _touch(root, relative: str) -> None:
    path = os.path.join(root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("x")


def test_the_artifacts_say_which_step_the_agent_has_reached(tmp_path) -> None:
    assert artifact_sync.step_reached(str(tmp_path)) is None

    bare = {**DRAFT, "workflow": {"steps": [{"id": "collect", "name": "Collect note"}]}}
    root = write_draft(tmp_path, bare)
    assert artifact_sync.step_reached(root) == artifact_sync.STEP_GATE_1

    _touch(root, "poc/schemas/output_schema_requirements.json")
    assert artifact_sync.step_reached(root) == artifact_sync.STEP_AFTER_SCHEMA

    write_draft(tmp_path, DRAFT)  # a step now names a component
    assert artifact_sync.step_reached(root) == artifact_sync.STEP_AFTER_COMPONENTS

    _touch(root, artifact_sync.WORKFLOW_BPMN_FILE)
    assert artifact_sync.step_reached(root) == artifact_sync.STEP_GATE_2

    _touch(root, "poc/run_poc.py")
    assert artifact_sync.step_reached(root) == artifact_sync.STEP_POC


@requires_postgres
def test_the_session_step_follows_the_agent_but_waits_at_a_pending_gate(client, db_session) -> None:
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    created = client.post("/sessions", json={"user_id": "follow", "title": "Follow"}).json()
    session_id = created["id"]
    write_draft(created["output_dir"], DRAFT)  # Gate 1 reviews the specification
    client.patch(f"/sessions/{session_id}", json={"gate_statuses": {"gate_1": "approved"}})
    client.patch(f"/sessions/{session_id}", json={"step": 5})
    session = session_service.get_session(db_session, uuid.UUID(session_id))

    # The agent has chosen components and drawn the BPMN: the session goes to Gate 2.
    root = write_draft(session.output_dir, DRAFT)
    _touch(root, artifact_sync.WORKFLOW_BPMN_FILE)
    _sync_artifacts_and_advance(db_session, session)
    assert client.get(f"/sessions/{session_id}").json()["step"] == 9

    # It writes the package too, but Gate 2 is pending: the session waits on the gate.
    _touch(root, "poc/run_poc.py")
    _sync_artifacts_and_advance(db_session, session)
    detail = client.get(f"/sessions/{session_id}").json()
    assert detail["step"] == 9
    assert detail["metadata"]["agent_step"] == 10

    # The user approves Gate 2, moves on, then steps back to review components.
    client.patch(f"/sessions/{session_id}", json={"gate_statuses": {"gate_2": "approved"}})
    client.patch(f"/sessions/{session_id}", json={"step": 6})
    db_session.refresh(session)
    # Nothing new from the agent: another turn must not push the user forward.
    _sync_artifacts_and_advance(db_session, session)
    assert client.get(f"/sessions/{session_id}").json()["step"] == 6


@requires_postgres
def test_gathering_still_ends_at_gate_1(client, db_session) -> None:
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    created = client.post("/sessions", json={"user_id": "follow", "title": "Gate 1"}).json()
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    root = write_draft(session.output_dir, DRAFT)
    _touch(root, artifact_sync.WORKFLOW_BPMN_FILE)  # even with more artifacts already there

    _sync_artifacts_and_advance(db_session, session)

    # Gate 1 is pending, so the session stops on it whatever the agent has written.
    assert client.get(f"/sessions/{created['id']}").json()["step"] == 4


# ---------------------------------------------------------------------------
# The user's own blueprint edits stay saved
# ---------------------------------------------------------------------------
#
# A save in the Blueprint form or the diagram changes the database only, never
# the agent's use_case.blueprint.json. The post-turn sync adopted that file
# whenever it differed from the active version, so the next chat message put the
# agent's older draft back over what the user had saved.

USER_STEP_NAME = "Poimi kentät lomakkeelta"


def _adopted_session(client, db_session, title: str):
    """A session whose blueprint is the agent's draft, as after a chat turn."""
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    created = client.post("/sessions", json={"user_id": "edits", "title": title}).json()
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    write_draft(session.output_dir, DRAFT)
    _sync_artifacts_and_advance(db_session, session)
    detail = client.get(f"/sessions/{created['id']}").json()
    assert detail["active_version"] == 2
    assert detail["versions"][-1]["note"] == "Agentin luonnos"
    return session, detail


def _save_user_edit(client, session_id: str, blueprint: dict) -> dict:
    """What the Blueprint form sends when the user renames a step and saves."""
    edited = json.loads(json.dumps(blueprint))
    edited["steps"][1]["name"] = USER_STEP_NAME
    res = client.patch(
        f"/sessions/{session_id}/blueprint",
        json={"content": edited, "note": "Blueprint päivitetty"},
    )
    assert res.status_code == 200
    return edited


@requires_postgres
def test_a_users_saved_blueprint_survives_the_next_chat_turn(client, db_session) -> None:
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    session, detail = _adopted_session(client, db_session, "User edit")
    _save_user_edit(client, detail["id"], detail["blueprint"])
    assert client.get(f"/sessions/{detail['id']}").json()["active_version"] == 3

    # The next chat turn: the agent has not touched its draft.
    _sync_artifacts_and_advance(db_session, session)

    after = client.get(f"/sessions/{detail['id']}").json()
    assert after["active_version"] == 3
    assert after["versions"][-1]["note"] == "Blueprint päivitetty"
    assert after["blueprint"]["steps"][1]["name"] == USER_STEP_NAME

    # Which draft was adopted is the server's record, not the caller's.
    res = client.patch(
        f"/sessions/{detail['id']}",
        json={"metadata": {artifact_sync.ADOPTED_DRAFT_KEY: "forged"}},
    )
    assert res.status_code == 422


@requires_postgres
def test_a_new_draft_from_the_agent_is_still_adopted_after_a_user_edit(client, db_session) -> None:
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    session, detail = _adopted_session(client, db_session, "Forward")
    _save_user_edit(client, detail["id"], detail["blueprint"])

    # The user asks for one more step in the chat and the agent writes a new draft.
    newer = json.loads(json.dumps(DRAFT))
    newer["workflow"]["steps"].append(
        {"id": "notify", "name": "Notify the supervisor", "type": "automated_task"}
    )
    write_draft(session.output_dir, newer)
    _sync_artifacts_and_advance(db_session, session)

    after = client.get(f"/sessions/{detail['id']}").json()
    assert after["active_version"] == 4
    assert after["versions"][-1]["note"] == "Agentin luonnos"
    assert [s["id"] for s in after["blueprint"]["steps"]][-1] == "notify"


@requires_postgres
def test_a_sync_holding_an_old_copy_does_not_adopt_an_adopted_draft_again(
    client, db_engine, db_session
) -> None:
    from sqlalchemy.orm import sessionmaker
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    session, detail = _adopted_session(client, db_session, "Two syncs")
    # A second sync loads the session before the first has adopted the new draft.
    other = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)()
    try:
        stale = session_service.get_session(other, session.id)
        assert artifact_sync.ADOPTED_DRAFT_KEY in stale.session_metadata

        newer = json.loads(json.dumps(DRAFT))
        newer["workflow"]["steps"].append(
            {"id": "notify", "name": "Notify the supervisor", "type": "automated_task"}
        )
        write_draft(session.output_dir, newer)
        _sync_artifacts_and_advance(db_session, session)
        adopted = client.get(f"/sessions/{detail['id']}").json()
        assert adopted["active_version"] == 3
        _save_user_edit(client, detail["id"], adopted["blueprint"])

        # What was adopted is read under the row lock, not from the old copy.
        assert artifact_sync.sync_blueprint_from_draft(other, stale) is False
    finally:
        other.close()

    after = client.get(f"/sessions/{detail['id']}").json()
    assert after["active_version"] == 4
    assert after["versions"][-1]["note"] == "Blueprint päivitetty"
    assert after["blueprint"]["steps"][1]["name"] == USER_STEP_NAME


@requires_postgres
def test_a_session_from_before_the_digest_keeps_the_users_version(client, db_session) -> None:
    from wizard_api.routers.sessions import _sync_artifacts_and_advance

    session, detail = _adopted_session(client, db_session, "Older session")
    # Sessions whose draft was adopted before the digest was kept have none.
    session.session_metadata = {
        k: v for k, v in session.session_metadata.items() if k != artifact_sync.ADOPTED_DRAFT_KEY
    }
    db_session.commit()
    _save_user_edit(client, detail["id"], detail["blueprint"])

    _sync_artifacts_and_advance(db_session, session)

    after = client.get(f"/sessions/{detail['id']}").json()
    assert after["active_version"] == 3
    assert after["blueprint"]["steps"][1]["name"] == USER_STEP_NAME
    assert after["metadata"][artifact_sync.ADOPTED_DRAFT_KEY]


def _fake_agent(monkeypatch, seen: list[str]) -> None:
    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        return {"lock": asyncio.Lock()}

    async def fake_stream_turn_for(agent, message, parts):
        seen.append(message)
        parts.append("Selvä.")
        yield agent_service.sse({"text": "Selvä."})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)


def _blueprint_note(message: str) -> str | None:
    server_lines = message.split("\n\n", 1)[0].split("\n")
    return next((line for line in server_lines if line.startswith("[The user changed")), None)


@requires_postgres
@requires_solution_wizard
def test_the_agent_hears_that_the_user_changed_the_blueprint(
    client, db_session, monkeypatch
) -> None:
    seen: list[str] = []
    _fake_agent(monkeypatch, seen)
    session, detail = _adopted_session(client, db_session, "Told")
    sid = detail["id"]

    # Nothing to tell while the blueprint is the agent's own draft.
    client.post(f"/sessions/{sid}/chat", json={"message": "Hei"})
    assert _blueprint_note(seen[-1]) is None

    # The form's save goes into the agent's draft (Task 10) ...
    edited = _save_user_edit(client, sid, detail["blueprint"])
    with open(
        os.path.join(session.output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE), encoding="utf-8"
    ) as fh:
        on_disk = json.load(fh)
    assert USER_STEP_NAME in [s["name"] for s in on_disk["workflow"]["steps"]]
    client.post(f"/sessions/{sid}/chat", json={"message": "Jatketaan"})

    # ... and the next turn names the change and the file it is in.
    note = _blueprint_note(seen[-1])
    assert note is not None
    assert USER_STEP_NAME in note
    assert artifact_sync.DRAFT_BLUEPRINT_FILE in note
    # The turn itself left the user's version in place.
    assert client.get(f"/sessions/{sid}").json()["active_version"] == 3

    # The agent goes on from its draft, which has the change: nothing new to
    # adopt, and nothing left to tell.
    client.post(f"/sessions/{sid}/chat", json={"message": "Kiitos"})
    after = client.get(f"/sessions/{sid}").json()
    assert after["active_version"] == 3
    assert after["blueprint"] == edited
    client.post(f"/sessions/{sid}/chat", json={"message": "Entä nyt?"})
    assert _blueprint_note(seen[-1]) is None


def test_a_session_file_is_readable_by_the_api_user_only(tmp_path) -> None:
    with artifact_sync._open_artifact(str(tmp_path), "probe.json", "w") as fh:
        fh.write("{}")

    assert (tmp_path / "probe.json").stat().st_mode & 0o077 == 0


@requires_postgres
def test_the_chat_sync_forgets_an_ai_step_the_agent_has_settled(client, db_session) -> None:
    """``ai_steps_without_component``: a step the user made an AI step is shown as
    one only while the agent's draft has it as an automated task without a
    component."""
    draft = json.loads(json.dumps(DRAFT))
    draft["workflow"]["steps"][2] = {"id": "review", "name": "Review", "type": "automated_task"}
    session, detail = _adopted_session_with(client, db_session, "AI steps", draft)
    session.session_metadata = {
        **session.session_metadata,
        artifact_sync.AI_STEPS_KEY: ["review"],
    }
    db_session.commit()

    # The agent gives it a component: an AI step by its own right, no longer remembered.
    draft["workflow"]["steps"][2]["component"] = "Classifier"
    write_draft(session.output_dir, draft)
    artifact_sync.sync_blueprint_from_draft(db_session, session)
    assert artifact_sync.AI_STEPS_KEY not in session.session_metadata

    # Taken away again, the step is plain automated work: io, not ai.
    del draft["workflow"]["steps"][2]["component"]
    write_draft(session.output_dir, draft)
    artifact_sync.sync_blueprint_from_draft(db_session, session)
    shown = client.get(f"/sessions/{detail['id']}").json()["blueprint"]
    assert {s["id"]: s["type"] for s in shown["steps"]}["review"] == "io"


@requires_postgres
def test_the_chat_sync_keeps_an_ai_step_the_agent_has_not_settled(client, db_session) -> None:
    draft = json.loads(json.dumps(DRAFT))
    draft["workflow"]["steps"][2] = {"id": "review", "name": "Review", "type": "automated_task"}
    session, detail = _adopted_session_with(client, db_session, "AI kept", draft)
    session.session_metadata = {**session.session_metadata, artifact_sync.AI_STEPS_KEY: ["review"]}
    db_session.commit()

    # The agent renames another step: the remembered one is still without a component.
    draft["workflow"]["steps"][0]["name"] = "Collect the note"
    write_draft(session.output_dir, draft)
    artifact_sync.sync_blueprint_from_draft(db_session, session)

    assert session.session_metadata[artifact_sync.AI_STEPS_KEY] == ["review"]
    shown = client.get(f"/sessions/{detail['id']}").json()["blueprint"]
    assert {s["id"]: s["type"] for s in shown["steps"]}["review"] == "ai"


def _adopted_session_with(client, db_session, title: str, draft: dict):
    created = client.post("/sessions", json={"user_id": "edits", "title": title}).json()
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    write_draft(session.output_dir, draft)
    artifact_sync.sync_blueprint_from_draft(db_session, session)
    return session, client.get(f"/sessions/{created['id']}").json()


def test_read_extraction_proposal_reads_prompt_and_generated_schema(tmp_path) -> None:
    assert artifact_sync.read_extraction_proposal(str(tmp_path)) is None

    poc = tmp_path / "poc"
    (poc / "prompts").mkdir(parents=True)
    prompt = poc / "prompts" / "extraction_requirements.md"
    prompt.write_text("# Poimintaohje\n\n- Kohde (location): halli tai laite\n", encoding="utf-8")

    proposal = artifact_sync.read_extraction_proposal(str(tmp_path))
    assert proposal is not None
    assert "Kohde (location)" in proposal.prompt_markdown
    assert proposal.schema_generated is False
    assert proposal.schema_code == ""

    (poc / "schemas").mkdir(parents=True)
    schema_py = poc / "schemas" / "output_schema.py"
    schema_py.write_text("class Ticket:\n    location: str\n", encoding="utf-8")
    generated = artifact_sync.read_extraction_proposal(str(tmp_path))
    assert generated is not None
    assert generated.schema_generated is True
    assert "class Ticket" in (generated.schema_code or "")

    prompt.write_text("# Updated extraction rules", encoding="utf-8")
    updated = schema_py.stat().st_mtime_ns + 1_000_000_000
    os.utime(prompt, ns=(updated, updated))
    revised = artifact_sync.read_extraction_proposal(str(tmp_path))
    assert revised is not None
    assert revised.prompt_markdown == "# Updated extraction rules"
    assert revised.schema_generated is False
    assert revised.schema_code == ""

    os.utime(schema_py, ns=(updated, updated))
    regenerated = artifact_sync.read_extraction_proposal(str(tmp_path))
    assert regenerated is not None
    assert regenerated.schema_generated is True
    assert "class Ticket" in regenerated.schema_code


def test_read_extraction_proposal_ignores_symlinks_outside_poc(tmp_path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read", encoding="utf-8")
    prompts_dir = tmp_path / "session" / "poc" / "prompts"
    prompts_dir.mkdir(parents=True)
    link = prompts_dir / "extraction_requirements.md"
    schemas_dir = prompts_dir.parent / "schemas"
    schemas_dir.mkdir()
    try:
        os.symlink(outside, link)
        os.symlink(outside, schemas_dir / "output_schema.py")
    except OSError:
        pytest.skip("symlinks unavailable in this environment")

    assert artifact_sync.read_extraction_proposal(str(tmp_path / "session")) is None
