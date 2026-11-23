"""The user's diagram layout, kept apart from the blueprint and laid over each drawing.

The diagram is drawn again from the blueprint every time (``bpmn_service``), so
where the user dragged a shape on the canvas would be lost at the next redraw.
Those positions are kept as an overlay in ``session_metadata["bpmn_layout"]``,
one per drawing mode: ``{"full": <layout>, "compact": <layout>}``, as a shape
sits elsewhere when the data objects are left out.

A layout is ``{"shapes": {id: {"x": float, "y": float}}, "edges": {id: [[x, y], ...]}}``,
keyed by the BPMN element ids of the drawing (the ids ``GET /bpmn/mapping``
lists). ``clean_layout`` checks one; ``merge_layout`` folds a ``PUT`` body into
the stored one, where ``null`` for an id removes it so the client can reset a
shape; ``apply_layout`` lays a layout over a drawing. Ids the drawing no longer
has are ignored when it is applied and may stay stored.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    from solution_wizard.bpmn_generator import route_edge
    from solution_wizard.bpmn_sync import _parse
except ImportError:  # pragma: no cover - optional in minimal installs
    route_edge = None  # type: ignore[assignment]
    _parse = None  # type: ignore[assignment]

#: Where a session keeps its layouts, one per drawing mode.
LAYOUT_KEY = "bpmn_layout"
FULL, COMPACT = "full", "compact"
#: Shapes and edges together, per drawing mode.
MAX_ENTRIES = 1000
#: How far from the origin a position may lie, in either direction.
MAX_COORDINATE = 100_000
#: Waypoints of one edge: a connection has at least two.
MIN_WAYPOINTS, MAX_WAYPOINTS = 2, 100
_ID_RE = re.compile(r"[A-Za-z0-9_.\-]{1,100}")
_SECTIONS = ("shapes", "edges")

_MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
_DC = "http://www.omg.org/spec/DD/20100524/DC"
_DI = "http://www.omg.org/spec/DD/20100524/DI"
# The generator's prefixes, so the XML that comes back reads as the one drawn.
for _prefix, _uri in (("bpmn", _MODEL), ("bpmndi", _BPMNDI), ("omgdc", _DC), ("omgdi", _DI)):
    ET.register_namespace(_prefix, _uri)

_SHAPE = f"{{{_BPMNDI}}}BPMNShape"
_EDGE = f"{{{_BPMNDI}}}BPMNEdge"
_LABEL = f"{{{_BPMNDI}}}BPMNLabel"
_BOUNDS = f"{{{_DC}}}Bounds"
_WAYPOINT = f"{{{_DI}}}waypoint"
#: Shapes the layout cannot move: they span the drawing.
_FIXED_KINDS = {f"{{{_MODEL}}}lane", f"{{{_MODEL}}}participant"}


def mode(include_data_objects: bool) -> str:
    """The layout key of a drawing mode."""
    return FULL if include_data_objects else COMPACT


def empty_layout() -> dict[str, dict]:
    return {"shapes": {}, "edges": {}}


# ---------------------------------------------------------------------------
# checking and merging
# ---------------------------------------------------------------------------


def _id(raw: Any) -> str:
    if not isinstance(raw, str) or not _ID_RE.fullmatch(raw):
        raise ValueError("an id is 1 to 100 letters, digits or _ . -")
    return raw


def _number(raw: Any) -> float:
    # abs() <= limit also refuses NaN and infinity, and an int too large for a float.
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not abs(raw) <= MAX_COORDINATE:
        raise ValueError(f"a coordinate is a finite number within ±{MAX_COORDINATE}")
    return float(raw)


def _position(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict) or set(raw) != {"x", "y"}:
        raise ValueError('a shape position is {"x": number, "y": number}')
    return {"x": _number(raw["x"]), "y": _number(raw["y"])}


def _waypoints(raw: Any) -> list[list[float]]:
    if not isinstance(raw, list) or not MIN_WAYPOINTS <= len(raw) <= MAX_WAYPOINTS:
        raise ValueError(f"an edge has {MIN_WAYPOINTS} to {MAX_WAYPOINTS} waypoints")
    points = []
    for point in raw:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("a waypoint is [x, y]")
        points.append([_number(point[0]), _number(point[1])])
    return points


def _sections(raw: Any) -> dict[str, dict]:
    if not isinstance(raw, dict):
        raise ValueError("a layout is an object")
    unknown = set(raw) - set(_SECTIONS)
    if unknown:
        raise ValueError(f"a layout has only {' and '.join(_SECTIONS)}")
    out = {}
    for section in _SECTIONS:
        value = raw.get(section, {})
        if not isinstance(value, dict):
            raise ValueError(f"{section} is an object keyed by element id")
        out[section] = value
    return out


def clean_layout(raw: Any) -> dict[str, dict]:
    """The layout ``raw`` as stored: positions and waypoints as floats.

    Raises ``ValueError`` for anything but
    ``{"shapes": {id: {"x", "y"}}, "edges": {id: [[x, y], ...]}}`` (both
    optional) with ids of ``[A-Za-z0-9_.-]{1,100}``, finite numbers within
    ``MAX_COORDINATE``, 2 to ``MAX_WAYPOINTS`` waypoints an edge and at most
    ``MAX_ENTRIES`` shapes and edges together.
    """
    sections = _sections(raw)
    if sum(len(v) for v in sections.values()) > MAX_ENTRIES:
        raise ValueError(f"a layout has at most {MAX_ENTRIES} shapes and edges")
    return {
        "shapes": {_id(k): _position(v) for k, v in sections["shapes"].items()},
        "edges": {_id(k): _waypoints(v) for k, v in sections["edges"].items()},
    }


def merge_layout(stored: Any, update: Any) -> dict[str, dict]:
    """``stored`` with ``update`` laid over it, entry by entry.

    An entry of ``update`` replaces the stored one of the same id; ``null``
    removes it. A stored layout that is not valid any more is started afresh.
    Raises ``ValueError`` when ``update`` is not a layout (``null`` allowed as
    a value) or the result would not be one, for example over ``MAX_ENTRIES``.
    """
    sections = _sections(update)
    removed = {
        section: {_id(k) for k, v in sections[section].items() if v is None}
        for section in _SECTIONS
    }
    given = clean_layout(
        {s: {k: v for k, v in sections[s].items() if v is not None} for s in _SECTIONS}
    )
    try:
        merged = clean_layout(stored) if stored is not None else empty_layout()
    except ValueError:
        logger.warning("a stored diagram layout was not valid and is replaced")
        merged = empty_layout()
    for section in _SECTIONS:
        entries = merged[section]
        entries.update(given[section])
        for key in removed[section]:
            entries.pop(key, None)
    return clean_layout(merged)


def stored_layout(metadata: dict[str, Any] | None, include_data_objects: bool) -> dict | None:
    """The valid layout a session keeps for a drawing mode, or None."""
    layouts = (metadata or {}).get(LAYOUT_KEY)
    if not isinstance(layouts, dict) or mode(include_data_objects) not in layouts:
        return None
    try:
        return clean_layout(layouts[mode(include_data_objects)])
    except ValueError:
        logger.warning("a stored diagram layout is not valid and is not applied")
        return None


def save_layout(db: Session, session: Any, include_data_objects: bool, update: Any) -> None:
    """Merge ``update`` into the session's layout of the drawing mode and commit.

    Under the session's row lock, so two saves at once each keep the other's
    entries. The blueprint is not touched: no version, no lock on the agent's
    draft, and a save is taken while the agent replies. Raises ``ValueError``
    (nothing stored) when the merge is no valid layout.
    """
    try:
        db.refresh(session, with_for_update=True)
        metadata = dict(session.session_metadata or {})
        layouts = metadata.get(LAYOUT_KEY)
        layouts = dict(layouts) if isinstance(layouts, dict) else {}
        key = mode(include_data_objects)
        layouts[key] = merge_layout(layouts.get(key), update)
        # A new dict, so the JSON column sees the change.
        session.session_metadata = {**metadata, LAYOUT_KEY: layouts}
        db.commit()
    except BaseException:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# applying
# ---------------------------------------------------------------------------


def _fmt(value: float) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{round(value, 2):g}"


def _rect(bounds: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(bounds.get(k) or 0) for k in ("x", "y", "width", "height"))  # type: ignore[return-value]


def _edge_ends(root: ET.Element) -> dict[str, tuple[str, str]]:
    """Each connection's source and target element, by its id."""
    ends: dict[str, tuple[str, str]] = {}
    for parent in root.iter():
        for el in parent:
            el_id = el.get("id")
            if not el_id:
                continue
            if el.get("sourceRef") and el.get("targetRef"):
                ends[el_id] = (el.get("sourceRef"), el.get("targetRef"))
            elif el.tag == f"{{{_MODEL}}}dataInputAssociation":
                ref = el.find(f"{{{_MODEL}}}sourceRef")
                if ref is not None and ref.text and parent.get("id"):
                    ends[el_id] = (ref.text.strip(), parent.get("id"))
            elif el.tag == f"{{{_MODEL}}}dataOutputAssociation":
                ref = el.find(f"{{{_MODEL}}}targetRef")
                if ref is not None and ref.text and parent.get("id"):
                    ends[el_id] = (parent.get("id"), ref.text.strip())
    return ends


def _set_waypoints(edge: ET.Element, points: list) -> None:
    indent = (edge.text or "\n        ") if len(edge) else "\n        "
    others = [child for child in edge if child.tag != _WAYPOINT]
    new = []
    for x, y in points:
        wp = ET.Element(_WAYPOINT, {"x": _fmt(x), "y": _fmt(y)})
        wp.tail = indent
        new.append(wp)
    closing = edge[-1].tail if len(edge) else "\n      "
    edge[:] = new + others
    edge.text = indent
    edge[-1].tail = closing


def _own_lanes(
    root: ET.Element, drawn: dict[str, tuple[float, float, float, float]]
) -> dict[str, tuple[float, float, float, float]]:
    """The box of the lane each element is listed in (``flowNodeRef``), the innermost one."""
    own: dict[str, tuple[float, float, float, float]] = {}
    for lane in root.iter(f"{{{_MODEL}}}lane"):
        box = drawn.get(lane.get("id") or "")
        if box is None:
            continue
        for ref in lane.findall(f"{{{_MODEL}}}flowNodeRef"):
            element = (ref.text or "").strip()
            if element and (
                element not in own or box[2] * box[3] < own[element][2] * own[element][3]
            ):
                own[element] = box
    return own


def _inside(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    x, y, w, h = box
    return x <= point[0] <= x + w and y <= point[1] <= y + h


#: How far a stored edge's first or last waypoint may lie outside its shape's bounds.
END_TOLERANCE = 3.0


def _touches(point: list, box: tuple[float, float, float, float] | None) -> bool:
    """Whether ``point`` lies on or in ``box``, give or take ``END_TOLERANCE``.

    bpmn-js docks a connection on the outline of the shape (a task's border, a
    gateway's diamond, an event's circle), which always lies within the bounds.
    """
    if box is None:
        return False
    x, y, w, h = box
    t = END_TOLERANCE
    return x - t <= point[0] <= x + w + t and y - t <= point[1] <= y + h + t


def apply_layout(xml: str, layout: dict) -> str:
    """The drawing ``xml`` with the shapes and edges of ``layout`` placed as stored.

    A shape is moved to its stored x and y with its width and height kept, and
    its label moves with it; lanes and pools are not moved. An edge with stored
    waypoints takes them; an edge that touches a moved shape and has none is
    drawn again with ``route_edge`` between the shapes' new bounds. Ids the
    drawing does not have are ignored.

    Stored waypoints are taken only when the first lies on the edge's current
    source shape and the last on its current target shape (``_touches``). The
    generator numbers flows and associations in order (``Flow_5``), so after a
    step is added, removed or moved the same id may name another connection,
    and a neighbour may have moved to another column: such a route is ignored
    and the edge is drawn as the generator draws it, or with ``route_edge``
    when one of its shapes was moved.

    A stored place whose middle lies outside the lane that lists the shape
    (``flowNodeRef``) is not applied: the step went to another lane in the
    blueprint, or lanes were added, since it was dragged. The shape stays
    where the drawing puts it, and the stored routes of its edges are not
    applied either; the entries stay stored. Without anything to change the XML is
    returned as it is; otherwise it is parsed with the hardened parser of
    ``bpmn_sync`` and written back without comments and without a DOCTYPE.
    """
    shapes = (layout or {}).get("shapes") or {}
    edges = (layout or {}).get("edges") or {}
    if not shapes and not edges:
        return xml
    root = _parse(xml)
    kinds = {el.get("id"): el.tag for el in root.iter() if el.get("id")}
    drawn = {
        shape.get("bpmnElement") or "": _rect(shape.find(_BOUNDS))
        for shape in root.iter(_SHAPE)
        if shape.find(_BOUNDS) is not None
    }
    own_lanes = _own_lanes(root, drawn)
    rects: dict[str, tuple[float, float, float, float]] = {}
    moved: set[str] = set()
    # Shapes whose stored place lies outside their own lane: left as drawn.
    kept_drawn: set[str] = set()
    changed = False
    for shape in root.iter(_SHAPE):
        element = shape.get("bpmnElement") or ""
        bounds = shape.find(_BOUNDS)
        if bounds is None:
            continue
        x, y, w, h = _rect(bounds)
        position = shapes.get(element)
        lane = own_lanes.get(element)
        if (
            position is not None
            and lane is not None
            and not _inside((position["x"] + w / 2, position["y"] + h / 2), lane)
        ):
            kept_drawn.add(element)
            position = None
        if position is not None and kinds.get(element) not in _FIXED_KINDS:
            dx, dy = position["x"] - x, position["y"] - y
            if dx or dy:
                x, y = position["x"], position["y"]
                bounds.set("x", _fmt(x))
                bounds.set("y", _fmt(y))
                for label in shape.findall(f"{_LABEL}/{_BOUNDS}"):
                    lx, ly, _, _ = _rect(label)
                    label.set("x", _fmt(lx + dx))
                    label.set("y", _fmt(ly + dy))
                moved.add(element)
                changed = True
        rects[element] = (x, y, w, h)
    ends = _edge_ends(root) if moved or kept_drawn or edges else {}
    for edge in root.iter(_EDGE):
        element = edge.get("bpmnElement") or ""
        route = edges.get(element)
        if route is not None and element in ends:
            src, tgt = ends[element]
            if (
                not kept_drawn.intersection((src, tgt))
                and _touches(route[0], rects.get(src))
                and _touches(route[-1], rects.get(tgt))
            ):
                _set_waypoints(edge, route)
                changed = True
                continue
        src, tgt = ends.get(element, ("", ""))
        if (src in moved or tgt in moved) and src in rects and tgt in rects:
            _set_waypoints(edge, route_edge(rects[src], rects[tgt]))
            changed = True
    if not changed:
        return xml
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
