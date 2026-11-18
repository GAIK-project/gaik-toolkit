"""The user's diagram layout: stored per drawing mode, applied over every redraw.

The diagram is drawn again from the blueprint each time, so the positions the
user gave shapes on the canvas are kept apart from it, in
``session_metadata["bpmn_layout"]``, and laid over the drawing by ``GET /bpmn``.
"""

import json
import math
import uuid
import xml.etree.ElementTree as ET

import pytest
from helpers import requires_postgres
from test_blueprint_operations_api import _create, _versions
from wizard_api.ownership import USER_HEADER
from wizard_api.services import agent_service, bpmn_layout, bpmn_service, session_service

pytestmark = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "omgdc": "http://www.omg.org/spec/DD/20100524/DC",
    "omgdi": "http://www.omg.org/spec/DD/20100524/DI",
}

BLUEPRINT = {
    "name": "Invoices",
    "description": "Test",
    "goal": "Book invoices",
    "steps": [
        {"id": "upload", "name": "Upload invoice", "type": "io"},
        {"id": "extract", "name": "Extract fields", "type": "ai", "component": "extractor"},
        {"id": "approve", "name": "Approve invoice", "type": "human_review"},
    ],
}


def _xml(include_data_objects: bool = True) -> str:
    return bpmn_service.generate_bpmn_xml(
        BLUEPRINT, session_id="s1", include_data_objects=include_data_objects
    )


def _bounds(xml: str) -> dict[str, tuple[float, float, float, float]]:
    root = ET.fromstring(xml)
    out = {}
    for shape in root.iter(f"{{{NS['bpmndi']}}}BPMNShape"):
        b = shape.find("omgdc:Bounds", NS)
        out[shape.get("bpmnElement")] = tuple(
            float(b.get(k)) for k in ("x", "y", "width", "height")
        )
    return out


def _label_bounds(xml: str) -> dict[str, tuple[float, float]]:
    root = ET.fromstring(xml)
    out = {}
    for shape in root.iter(f"{{{NS['bpmndi']}}}BPMNShape"):
        b = shape.find("bpmndi:BPMNLabel/omgdc:Bounds", NS)
        if b is not None:
            out[shape.get("bpmnElement")] = (float(b.get("x")), float(b.get("y")))
    return out


def _waypoints(xml: str) -> dict[str, list[tuple[float, float]]]:
    root = ET.fromstring(xml)
    return {
        edge.get("bpmnElement"): [
            (float(p.get("x")), float(p.get("y"))) for p in edge.findall("omgdi:waypoint", NS)
        ]
        for edge in root.iter(f"{{{NS['bpmndi']}}}BPMNEdge")
    }


def _ends(xml: str) -> dict[str, tuple[str, str]]:
    """Each sequence flow's source and target."""
    root = ET.fromstring(xml)
    return {
        f.get("id"): (f.get("sourceRef"), f.get("targetRef"))
        for f in root.iter(f"{{{NS['bpmn']}}}sequenceFlow")
    }


def _tasks(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    tags = ("task", "userTask", "serviceTask", "sendTask", "manualTask", "scriptTask")
    return [el.get("id") for tag in tags for el in root.iter(f"{{{NS['bpmn']}}}{tag}")]


def _on_border(point, rect) -> bool:
    px, py = point
    x, y, w, h = rect
    inside = x - 0.5 <= px <= x + w + 0.5 and y - 0.5 <= py <= y + h + 0.5
    near = min(abs(px - x), abs(px - x - w), abs(py - y), abs(py - y - h)) <= 0.5
    return inside and near


# ---------------------------------------------------------------------------
# apply_layout
# ---------------------------------------------------------------------------


def test_apply_layout_moves_the_shape_and_keeps_its_size() -> None:
    xml = _xml()
    task = _tasks(xml)[0]
    before = _bounds(xml)[task]

    moved = bpmn_layout.apply_layout(xml, {"shapes": {task: {"x": 900.5, "y": 640}}})

    assert _bounds(moved)[task] == (900.5, 640.0, before[2], before[3])
    assert "<!DOCTYPE" not in moved
    assert "bpmn:definitions" in moved


def test_a_moved_shapes_label_moves_with_it() -> None:
    xml = _xml()
    labels = _label_bounds(xml)
    assert labels, "the generator labels its events"
    element = next(iter(labels))
    bx, by = _bounds(xml)[element][:2]
    lx, ly = labels[element]

    moved = bpmn_layout.apply_layout(xml, {"shapes": {element: {"x": bx + 30, "y": by - 20}}})

    assert _label_bounds(moved)[element] == (lx + 30, ly - 20)


def test_edges_of_a_moved_shape_are_rerouted_with_right_angles() -> None:
    xml = _xml()
    task = _tasks(xml)[1]
    touching = [f for f, ends in _ends(xml).items() if task in ends]
    assert touching
    before = _waypoints(xml)

    moved = bpmn_layout.apply_layout(xml, {"shapes": {task: {"x": 700, "y": 520}}})

    bounds, points = _bounds(moved), _waypoints(moved)
    ends = _ends(moved)
    for flow in touching:
        assert points[flow] != before[flow], flow
        src, tgt = ends[flow]
        assert _on_border(points[flow][0], bounds[src]), (flow, points[flow])
        assert _on_border(points[flow][-1], bounds[tgt]), (flow, points[flow])
        for a, b in zip(points[flow], points[flow][1:]):
            assert a[0] == b[0] or a[1] == b[1], (flow, points[flow])
    # The data associations of the task follow it too.
    for edge, wps in points.items():
        for a, b in zip(wps, wps[1:]):
            assert a[0] == b[0] or a[1] == b[1], (edge, wps)


def test_stored_waypoints_replace_the_edges_route() -> None:
    xml = _xml()
    flow = next(iter(_ends(xml)))
    route = [[10, 20], [10, 400], [333.5, 400]]
    task = _ends(xml)[flow][1]

    moved = bpmn_layout.apply_layout(
        xml, {"shapes": {task: {"x": 1000, "y": 1000}}, "edges": {flow: route}}
    )

    assert _waypoints(moved)[flow] == [tuple(p) for p in route]


def test_unknown_ids_are_ignored() -> None:
    xml = _xml()
    root = ET.fromstring(xml)
    lane = next(root.iter(f"{{{NS['bpmn']}}}lane")).get("id")
    participant = next(root.iter(f"{{{NS['bpmn']}}}participant")).get("id")
    layout = {
        "shapes": {
            "Activity_gone": {"x": 1, "y": 2},
            lane: {"x": 500, "y": 500},
            participant: {"x": 500, "y": 500},
        },
        "edges": {"Flow_gone": [[0, 0], [10, 0]]},
    }

    out = bpmn_layout.apply_layout(xml, layout)

    assert _bounds(out) == _bounds(xml)
    assert _waypoints(out) == _waypoints(xml)


def test_an_empty_layout_leaves_the_diagram_as_it_is() -> None:
    xml = _xml()
    assert bpmn_layout.apply_layout(xml, {}) == xml
    assert bpmn_layout.apply_layout(xml, {"shapes": {}, "edges": {}}) == xml


# ---------------------------------------------------------------------------
# clean_layout
# ---------------------------------------------------------------------------


def test_clean_layout_keeps_a_valid_layout_as_floats() -> None:
    raw = {"shapes": {"Activity_a": {"x": 1, "y": 2.5}}, "edges": {"Flow_1": [[0, 0], [5, 0]]}}
    assert bpmn_layout.clean_layout(raw) == {
        "shapes": {"Activity_a": {"x": 1.0, "y": 2.5}},
        "edges": {"Flow_1": [[0.0, 0.0], [5.0, 0.0]]},
    }
    assert bpmn_layout.clean_layout({}) == {"shapes": {}, "edges": {}}


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"other": {}},
        {"shapes": []},
        {"shapes": {"bad id": {"x": 1, "y": 1}}},
        {"shapes": {"a" * 101: {"x": 1, "y": 1}}},
        {"shapes": {"A": {"x": 1}}},
        {"shapes": {"A": {"x": 1, "y": 1, "w": 3}}},
        {"shapes": {"A": {"x": "1", "y": 1}}},
        {"shapes": {"A": {"x": True, "y": 1}}},
        {"shapes": {"A": {"x": math.inf, "y": 1}}},
        {"shapes": {"A": {"x": math.nan, "y": 1}}},
        {"shapes": {"A": {"x": 100_001, "y": 1}}},
        {"edges": {"F": [[0, 0]]}},
        {"edges": {"F": [[0, 0], [1]]}},
        {"edges": {"F": [[0, 0], [1, -math.inf]]}},
        {"edges": {"F": [[0, 0]] * 101}},
        {"shapes": {f"S{i}": {"x": 0, "y": 0} for i in range(600)}}
        | {"edges": {f"E{i}": [[0, 0], [1, 0]] for i in range(401)}},
    ],
    ids=[
        "not-an-object",
        "unknown-key",
        "shapes-not-an-object",
        "id-with-space",
        "id-too-long",
        "missing-y",
        "extra-key",
        "string-number",
        "bool-number",
        "infinite",
        "nan",
        "too-far",
        "one-waypoint",
        "short-point",
        "infinite-waypoint",
        "too-many-waypoints",
        "over-1000-entries",
    ],
)
def test_oversized_or_non_finite_layouts_are_refused(raw) -> None:
    with pytest.raises(ValueError):
        bpmn_layout.clean_layout(raw)


# ---------------------------------------------------------------------------
# PUT /sessions/{id}/bpmn/layout and GET /bpmn
# ---------------------------------------------------------------------------


def _put(client, sid: str, body, *, data_objects: int | None = None, headers=None):
    params = {} if data_objects is None else {"data_objects": data_objects}
    return client.put(
        f"/sessions/{sid}/bpmn/layout",
        content=json.dumps(body) if not isinstance(body, str | bytes) else body,
        params=params,
        headers={"content-type": "application/json", **(headers or {})},
    )


def _stored(db_session, sid: str) -> dict:
    db_session.expire_all()
    session = session_service.get_session(db_session, uuid.UUID(sid))
    return session.session_metadata.get("bpmn_layout")


@pytest.fixture
def busy(monkeypatch):
    """Layout is accepted while the agent replies: it touches no blueprint."""
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)


@requires_postgres
def test_a_moved_shape_keeps_its_position_after_a_redraw(client, db_session, busy) -> None:
    created = _create(client)
    sid = created["id"]
    full = client.get(f"/sessions/{sid}/bpmn").text
    task = _tasks(full)[0]
    width, height = _bounds(full)[task][2:]

    res = _put(client, sid, {"shapes": {task: {"x": 1234, "y": 567}}})

    assert res.status_code == 204, res.text
    again = client.get(f"/sessions/{sid}/bpmn")
    assert again.status_code == 200
    assert again.headers["X-AI-Generated"] == "true"
    assert "<bpmn:definitions" in again.text
    assert _bounds(again.text)[task] == (1234.0, 567.0, width, height)
    assert _bounds(client.get(f"/sessions/{sid}/bpmn", params={"data_objects": 1}).text)[task] == (
        1234.0,
        567.0,
        width,
        height,
    )
    # The compact drawing has its own layout.
    compact = client.get(f"/sessions/{sid}/bpmn", params={"data_objects": 0}).text
    assert _bounds(compact)[task][:2] != (1234.0, 567.0)
    # No version: the blueprint did not change.
    assert len(_versions(db_session, sid)) == 1


@requires_postgres
def test_a_compact_position_does_not_move_the_full_drawing(client, db_session, busy) -> None:
    created = _create(client)
    sid = created["id"]
    full_before = client.get(f"/sessions/{sid}/bpmn").text
    task = _tasks(full_before)[0]

    assert (
        _put(client, sid, {"shapes": {task: {"x": 42, "y": 43}}}, data_objects=0).status_code == 204
    )

    compact = client.get(f"/sessions/{sid}/bpmn", params={"data_objects": 0}).text
    assert _bounds(compact)[task][:2] == (42.0, 43.0)
    assert _bounds(client.get(f"/sessions/{sid}/bpmn").text) == _bounds(full_before)
    assert _stored(db_session, sid) == {
        "compact": {"shapes": {task: {"x": 42.0, "y": 43.0}}, "edges": {}}
    }


@requires_postgres
def test_puts_merge_and_null_removes_an_entry(client, db_session, busy) -> None:
    sid = _create(client)["id"]

    assert (
        _put(client, sid, {"shapes": {"A": {"x": 1, "y": 1}, "B": {"x": 2, "y": 2}}}).status_code
        == 204
    )
    assert (
        _put(
            client, sid, {"shapes": {"B": {"x": 3, "y": 3}}, "edges": {"F": [[0, 0], [9, 0]]}}
        ).status_code
        == 204
    )
    assert _stored(db_session, sid)["full"] == {
        "shapes": {"A": {"x": 1.0, "y": 1.0}, "B": {"x": 3.0, "y": 3.0}},
        "edges": {"F": [[0.0, 0.0], [9.0, 0.0]]},
    }

    assert _put(client, sid, {"shapes": {"A": None}, "edges": {"F": None}}).status_code == 204
    assert _stored(db_session, sid)["full"] == {
        "shapes": {"B": {"x": 3.0, "y": 3.0}},
        "edges": {},
    }


@requires_postgres
def test_a_merge_over_1000_entries_is_refused(client, db_session, busy) -> None:
    sid = _create(client)["id"]
    first = {"shapes": {f"S{i}": {"x": 0, "y": 0} for i in range(600)}}
    second = {"shapes": {f"T{i}": {"x": 0, "y": 0} for i in range(401)}}
    assert _put(client, sid, first).status_code == 204

    res = _put(client, sid, second)

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_layout"
    assert len(_stored(db_session, sid)["full"]["shapes"]) == 600


@requires_postgres
@pytest.mark.parametrize(
    "body",
    [
        "not json",
        [],
        {"shapes": {"A": {"x": "NaN", "y": 0}}},
        {"shapes": {"A": {"x": 1e300, "y": 0}}},
        {"shapes": {"bad id": None}},
        {"edges": {"F": [[0, 0]]}},
    ],
    ids=["not-json", "array", "string-number", "too-far", "bad-null-id", "one-waypoint"],
)
def test_an_invalid_layout_answers_422(client, db_session, busy, body) -> None:
    sid = _create(client)["id"]

    res = _put(client, sid, body)

    assert res.status_code == 422, res.text
    assert res.json()["detail"]["error"] == "invalid_layout"
    assert _stored(db_session, sid) is None


@requires_postgres
def test_a_layout_over_64_kb_is_refused(client, db_session, busy) -> None:
    sid = _create(client)["id"]

    res = _put(client, sid, json.dumps({"shapes": {}}) + " " * 70_000)

    assert res.status_code == 413
    assert res.json()["detail"]["error"] == "too_large"
    assert _stored(db_session, sid) is None


@requires_postgres
def test_another_users_layout_is_not_found(client, db_session) -> None:
    alice = {USER_HEADER: "alice@example.com"}
    bob = {USER_HEADER: "bob@example.com"}
    sid = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Layout"}, headers=alice
    ).json()["id"]

    res = _put(client, sid, {"shapes": {"A": {"x": 1, "y": 1}}}, headers=bob)

    assert res.status_code == 404
    assert _stored(db_session, sid) is None


@requires_postgres
def test_a_broken_stored_layout_is_not_applied(client, db_session) -> None:
    created = _create(client)
    sid = created["id"]
    before = client.get(f"/sessions/{sid}/bpmn").text
    db_session.expire_all()
    session = session_service.get_session(db_session, uuid.UUID(sid))
    session.session_metadata = {
        **session.session_metadata,
        "bpmn_layout": {"full": {"shapes": "nonsense"}},
    }
    db_session.commit()

    res = client.get(f"/sessions/{sid}/bpmn")

    assert res.status_code == 200
    assert _bounds(res.text) == _bounds(before)


@requires_postgres
def test_two_saves_at_once_keep_each_others_entries(
    client, db_session, db_engine, monkeypatch
) -> None:
    """The merge runs under the row lock: the second save waits and merges into the first."""
    import threading
    import time

    from sqlalchemy.orm import sessionmaker

    sid = _create(client)["id"]
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    real_merge = bpmn_layout.merge_layout
    first_in = threading.Event()

    def slow_merge(stored, update):
        if "A" in (update.get("shapes") or {}):
            first_in.set()
            time.sleep(0.5)  # the second save arrives while this one holds the row
        return real_merge(stored, update)

    monkeypatch.setattr(bpmn_layout, "merge_layout", slow_merge)

    def save(update):
        db = factory()
        try:
            session = session_service.get_session(db, uuid.UUID(sid))
            bpmn_layout.save_layout(db, session, True, update)
        finally:
            db.close()

    first = threading.Thread(target=save, args=({"shapes": {"A": {"x": 1, "y": 1}}},))
    first.start()
    assert first_in.wait(5)
    save({"shapes": {"B": {"x": 2, "y": 2}}})
    first.join(5)

    assert set(_stored(db_session, sid)["full"]["shapes"]) == {"A", "B"}
