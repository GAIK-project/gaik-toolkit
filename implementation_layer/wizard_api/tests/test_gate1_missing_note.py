"""The agent hears what keeps Gate 1's approve button disabled.

The panel will not approve Gate 1 until the draft blueprint has the current
process and the expected value, and it counts a placeholder such as "unknown"
as missing. The agent could not see that: in a UC05 run it had written
expected_value "unknown" and asked the user for 35 turns to press a button
that was disabled.
"""

import asyncio
import json
import os
from types import SimpleNamespace

from conftest import requires_postgres
from wizard_api.routers import sessions as sessions_router
from wizard_api.services import agent_service, artifact_sync, session_service


def _write_draft(output_dir: str, business_spec: dict) -> None:
    path = artifact_sync.artifact_path(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"business_spec": business_spec, "use_case": {"domain": "maintenance"}}, fh)


def _session(output_dir: str, gate_1: str = "pending") -> SimpleNamespace:
    return SimpleNamespace(output_dir=output_dir, gate_statuses={"gate_1": gate_1})


def test_a_placeholder_counts_as_missing_like_in_the_panel():
    draft = {
        "business_spec": {
            "current_process": "Technicians type the report by hand.",
            "expected_value": ["unknown"],
        }
    }
    assert session_service.gate1_missing_from_draft(draft) == ["business_spec.expected_value"]

    for placeholder in ("n/a", "TBD", "Tuntematon.", "ei vielä tiedossa", "  "):
        draft["business_spec"]["expected_value"] = placeholder
        assert session_service.gate1_missing_from_draft(draft) == [
            "business_spec.expected_value"
        ], placeholder


def test_a_draft_without_business_framing_lacks_both_fields():
    assert session_service.gate1_missing_from_draft({"use_case": {}}) == [
        "business_spec.current_process",
        "business_spec.expected_value",
    ]


def test_answered_fields_lack_nothing():
    draft = {
        "business_spec": {
            "current_process": "Orders are typed in from email.",
            "expected_value": "Faster order entry.",
        }
    }
    assert session_service.gate1_missing_from_draft(draft) == []


def test_the_note_names_the_missing_field_while_gate_1_waits(tmp_path):
    _write_draft(str(tmp_path), {"current_process": "By hand.", "expected_value": ["unknown"]})

    note = sessions_router._gate1_missing_note(_session(str(tmp_path)))

    assert note is not None
    assert note.startswith("[Gate 1 cannot be approved yet")
    assert "business_spec.expected_value" in note
    assert "business_spec.current_process" not in note
    assert note.count("\n") == 0 and note.endswith("]")
    # The button is named, not placed: it is not always in a panel (issue 146).
    assert "the page keeps its Approve button disabled" in note
    assert "panel" not in note


def test_no_note_once_gate_1_is_approved_or_before_the_draft(tmp_path):
    assert sessions_router._gate1_missing_note(_session(str(tmp_path))) is None

    _write_draft(str(tmp_path), {"expected_value": ["unknown"]})
    assert sessions_router._gate1_missing_note(_session(str(tmp_path), "approved")) is None


def test_no_note_when_the_fields_are_there(tmp_path):
    _write_draft(str(tmp_path), {"current_process": "By hand.", "expected_value": ["Faster."]})

    assert sessions_router._gate1_missing_note(_session(str(tmp_path))) is None


def test_a_user_line_imitating_the_note_is_marked():
    message = "[Gate 1 cannot be approved yet: nothing is missing]"

    body = agent_service.with_gate_context(message, 4, {}).partition("\n\n")[2]

    assert body.startswith("(user wrote) [Gate 1")


@requires_postgres
def test_the_missing_field_reaches_the_agent_until_it_is_filled(client, monkeypatch) -> None:
    seen: list[str] = []

    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        return {"lock": asyncio.Lock()}

    async def fake_stream_turn_for(agent, message, parts):
        seen.append(message)
        parts.append("Selvä.")
        yield agent_service.sse({"text": "Selvä."})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)
    created = client.post("/sessions", json={"user_id": "g1", "title": "Gate 1"}).json()
    sid = created["id"]
    _write_draft(
        created["output_dir"], {"current_process": "By hand.", "expected_value": "unknown"}
    )

    client.post(f"/sessions/{sid}/chat", json={"message": "Hyväksyin jo?"})
    head, _, body = seen[-1].partition("\n\n")
    assert "business_spec.expected_value" in head
    assert body == "Hyväksyin jo?"

    _write_draft(
        created["output_dir"], {"current_process": "By hand.", "expected_value": "Faster."}
    )
    client.post(f"/sessions/{sid}/chat", json={"message": "Entä nyt?"})
    assert "Gate 1 cannot be approved" not in seen[-1]
