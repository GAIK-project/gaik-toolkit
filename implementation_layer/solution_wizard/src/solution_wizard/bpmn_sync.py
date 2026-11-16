"""Sync BPMN 2.0 XML canvas edits back into V2 simplified blueprint steps."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from xml.parsers import expat

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
# A canvas of a few hundred elements is well under 1 MB; anything larger is refused
# before it is parsed.
MAX_BPMN_XML_CHARS = 2_000_000
TASK_TAGS = {
    f"{{{BPMN_NS}}}userTask",
    f"{{{BPMN_NS}}}serviceTask",
    f"{{{BPMN_NS}}}task",
    f"{{{BPMN_NS}}}manualTask",
    f"{{{BPMN_NS}}}sendTask",
    f"{{{BPMN_NS}}}callActivity",
}
#: How deep the canvas XML may nest; a diagram needs a handful of levels.
MAX_BPMN_XML_DEPTH = 64
#: What a canvas edit may give the blueprint: ids are one token, names one line.
#: Used with fullmatch: with match, ``$`` also accepts an id that ends in a line
#: break, which the canvas XML can carry as ``&#10;``.
_ID_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]{0,99}")
MAX_NAME_CHARS = 200
# Synthetic generator tasks that should not become blueprint steps.
_SYNTHETIC_PREFIXES = (
    "Activity_submit_",
    "Activity_generate_pdf",
)


class _DepthLimitedBuilder(ET.TreeBuilder):
    """Builds the tree and refuses nesting deeper than any diagram needs."""

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0

    def start(self, tag, attrs):  # noqa: ANN001 - ElementTree's target protocol
        self._depth += 1
        if self._depth > MAX_BPMN_XML_DEPTH:
            raise ValueError(f"BPMN XML nests deeper than {MAX_BPMN_XML_DEPTH} levels")
        return super().start(tag, attrs)

    def end(self, tag):  # noqa: ANN001 - ElementTree's target protocol
        self._depth -= 1
        return super().end(tag)


def _refuse_declarations(*_args) -> None:
    raise ValueError("BPMN XML may not declare a DTD or entities")


def _qualified(name: str) -> str:
    """expat's ``uri}local`` as ElementTree's ``{uri}local``."""
    return "{" + name if "}" in name else name


def _parse(bpmn_xml: str) -> ET.Element:
    """Parse the canvas XML with no DTD, no entity declarations and a nesting limit.

    The expat parser refuses a document type or an entity declaration the
    moment it meets one, so no entity can expand, and the tree builder stops
    at MAX_BPMN_XML_DEPTH levels.
    """
    builder = _DepthLimitedBuilder()
    parser = expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = _refuse_declarations
    parser.EntityDeclHandler = _refuse_declarations
    parser.StartElementHandler = lambda tag, attrs: builder.start(
        _qualified(tag), {_qualified(k): v for k, v in attrs.items()}
    )
    parser.EndElementHandler = lambda tag: builder.end(_qualified(tag))
    parser.CharacterDataHandler = builder.data
    try:
        parser.Parse(bpmn_xml, True)
    except expat.ExpatError as exc:
        raise ET.ParseError(str(exc)) from exc
    return builder.close()


def _safe_id(raw: str, fallback: str = "step") -> str:
    """An id as the blueprint keeps it: one token of letters, digits and _ . -."""
    if _ID_RE.fullmatch(raw):
        return raw
    cleaned = re.sub(r"[^A-Za-z0-9_.\-]+", "_", raw).strip("_.-")[:100]
    return cleaned if cleaned and _ID_RE.fullmatch(cleaned) else fallback


def _safe_name(raw: str) -> str:
    """A label as the blueprint keeps it: one line, within MAX_NAME_CHARS."""
    return " ".join((raw or "").split())[:MAX_NAME_CHARS]


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _task_label(raw: str) -> str:
    """Strip optional ``[CODE]`` prefix / legacy caption suffixes from task names."""
    text = (raw or "").strip()
    if not text:
        return ""
    first = text.split("\n")[0].strip()
    # Legacy: "Name\n[Component]" or trailing " [Component]"
    first = re.sub(r"\s*\[[^\]]+\]\s*$", "", first).strip()
    # Official implementation style: "[STR] Transcribe Audio". A component code
    # is one to four capitals or digits (bpmn_generator._component_code); other
    # leading brackets ("[Beta] Upload") are part of the name the user gave.
    first = re.sub(r"^\[[A-Z0-9]{1,4}\]\s*", "", first).strip()
    return first or text.split("\n")[0].strip()


def _documentation_text(el: ET.Element) -> str:
    for child in el:
        if _local(child.tag) == "documentation" and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def _bpmn_id_to_step_id(bpmn_id: str) -> str:
    """Map generator activity ids back to blueprint step ids."""
    if bpmn_id.startswith("Activity_"):
        return bpmn_id[len("Activity_") :]
    if bpmn_id.startswith("Gateway_"):
        return bpmn_id[len("Gateway_") :]
    return bpmn_id


def _infer_v2_type(tag: str, bpmn_id: str, old_type: str | None) -> str:
    if old_type in ("io", "ai", "human_review"):
        # Preserve known types when the element still maps to an existing step.
        local = _local(tag)
        if local == "userTask" and old_type == "human_review":
            return "human_review"
        if local == "userTask" and old_type == "io":
            return "io"
        if local in ("serviceTask", "sendTask", "callActivity", "task") and old_type == "ai":
            return "ai"
    local = _local(tag)
    if local == "userTask":
        # Heuristic: review-ish ids/names stay human_review only via old_type;
        # new user tasks default to io.
        return "io"
    if local in ("serviceTask", "sendTask", "callActivity", "task", "manualTask"):
        return "ai"
    return old_type or "ai"


def _is_synthetic_task(bpmn_id: str) -> bool:
    return any(bpmn_id.startswith(p) for p in _SYNTHETIC_PREFIXES)


def _ordered_task_ids(root: ET.Element) -> list[str]:
    processes = [el for el in root.iter() if _local(el.tag) == "process"]
    if not processes:
        return []
    process = processes[0]

    nodes: dict[str, ET.Element] = {}
    for el in process.iter():
        if _local(el.tag) in {
            "startEvent",
            "endEvent",
            "userTask",
            "serviceTask",
            "task",
            "manualTask",
            "sendTask",
            "callActivity",
            "exclusiveGateway",
            "parallelGateway",
        }:
            if el.get("id"):
                nodes[el.get("id") or ""] = el

    outgoing: dict[str, list[str]] = {}
    for el in process.iter():
        if _local(el.tag) != "sequenceFlow":
            continue
        src = el.get("sourceRef")
        tgt = el.get("targetRef")
        if src and tgt:
            outgoing.setdefault(src, []).append(tgt)

    start_ids = [el.get("id") for el in process if _local(el.tag) == "startEvent" and el.get("id")]
    if not start_ids:
        return [
            el.get("id") or ""
            for el in process
            if el.tag in TASK_TAGS and el.get("id") and not _is_synthetic_task(el.get("id") or "")
        ]

    ordered: list[str] = []
    seen: set[str] = set()
    queue = list(start_ids)
    while queue:
        nid = queue.pop(0)
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        node = nodes[nid]
        if node.tag in TASK_TAGS and nid and not _is_synthetic_task(nid):
            ordered.append(nid)
        for tgt in outgoing.get(nid, []):
            if tgt not in seen:
                queue.append(tgt)

    return ordered


def _sync_data_object_names(root: ET.Element, v2_blueprint: dict[str, Any]) -> dict[str, str]:
    """Return artifact_id → label from BPMN dataObjectReference names (best-effort)."""
    mapping: dict[str, str] = {}
    for el in root.iter():
        if _local(el.tag) != "dataObjectReference":
            continue
        rid = el.get("id") or ""
        name = (el.get("name") or "").strip()
        if not rid or not name:
            continue
        # Generator ids: DataObjectRef_<artifact_id>
        if rid.startswith("DataObjectRef_"):
            art_id = rid[len("DataObjectRef_") :]
            if _ID_RE.fullmatch(art_id):
                mapping[art_id] = _safe_name(name)
    return mapping


def _humanize_artifact_id(artifact_id: str) -> str:
    """Default data-object label (must match bpmn_generator._data_object_label)."""
    from solution_wizard.bpmn_generator import _data_object_label

    return _data_object_label(artifact_id)


def _artifact_step_map(v2_blueprint: dict[str, Any]) -> dict[str, str]:
    """Rebuild the V2 adapter's artifact ids so data-object renames can map back to steps."""
    from solution_wizard.v2_adapter import _synthesize_artifacts_and_links

    mapping: dict[str, str] = {}
    _artifacts, workflow_steps = _synthesize_artifacts_and_links(
        list(v2_blueprint.get("steps") or [])
    )
    for ws in workflow_steps:
        outputs = list(ws.get("outputs") or [])
        if outputs:
            mapping[str(outputs[0])] = str(ws["id"])
    return mapping


def _sync_gateways(root: ET.Element) -> list[dict[str, Any]]:
    """Snapshot exclusive/parallel gateways from the canvas (#48)."""
    out: list[dict[str, Any]] = []
    for el in root.iter():
        local = _local(el.tag)
        if local not in ("exclusiveGateway", "parallelGateway"):
            continue
        gid = el.get("id") or ""
        if not gid:
            continue
        out.append(
            {
                "id": _safe_id(gid, "gateway"),
                "name": _safe_name(el.get("name") or ""),
                "type": "exclusive" if local == "exclusiveGateway" else "parallel",
            }
        )
    return out


def sync_v2_blueprint_from_bpmn_xml(
    v2_blueprint: dict[str, Any],
    bpmn_xml: str,
) -> dict[str, Any]:
    """Apply canvas edits to V2 blueprint steps.

    Supported:
    - rename tasks (strips ``[CODE]`` / legacy caption suffixes)
    - reorder steps from sequence-flow topology
    - add new tasks created on the canvas
    - remove steps whose activities were deleted from the canvas
    - sync ``bpmn:documentation`` → step.description when present
    - record data-object label edits under ``v2_blueprint[\"data_objects\"]``
    - snapshot gateway id/name/type under ``v2_blueprint[\"gateways\"]``
    """
    if len(bpmn_xml) > MAX_BPMN_XML_CHARS:
        raise ValueError(f"BPMN XML is longer than {MAX_BPMN_XML_CHARS} characters")
    # BPMN needs no DTD, and an entity declaration could make the parse expand
    # a short input far past the length cap above.
    if "<!DOCTYPE" in bpmn_xml or "<!ENTITY" in bpmn_xml:
        raise ValueError("BPMN XML may not declare a DTD or entities")
    root = _parse(bpmn_xml)
    processes = [el for el in root.iter() if _local(el.tag) == "process"]
    if not processes:
        return v2_blueprint

    process = processes[0]
    task_by_id: dict[str, ET.Element] = {}
    for el in process.iter():
        if el.tag in TASK_TAGS and el.get("id"):
            task_by_id[el.get("id") or ""] = el

    ordered_ids = _ordered_task_ids(root)
    if not ordered_ids:
        return v2_blueprint

    old_steps = list(v2_blueprint.get("steps") or [])
    old_by_id = {str(s.get("id")): s for s in old_steps if s.get("id")}

    new_steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for tid in ordered_ids:
        task_el = task_by_id.get(tid)
        label = _safe_name(_task_label(task_el.get("name") if task_el is not None else ""))
        docs = _documentation_text(task_el) if task_el is not None else ""
        step_id = _safe_id(_bpmn_id_to_step_id(tid))
        # Prefer exact blueprint id; fall back to Activity_-stripped id.
        old = old_by_id.get(step_id) or old_by_id.get(tid)
        resolved_id = str(old.get("id")) if old else step_id
        if resolved_id in seen_step_ids:
            continue
        seen_step_ids.add(resolved_id)

        if old:
            step = dict(old)
            if label:
                step["name"] = label
            if docs:
                step["description"] = docs
            elif task_el is not None and "description" in step and docs == "":
                # Keep existing description when BPMN has no documentation child.
                pass
            step["type"] = _infer_v2_type(
                task_el.tag if task_el is not None else "",
                tid,
                str(old.get("type") or "ai"),
            )
        else:
            step = {
                "id": resolved_id,
                "name": label or resolved_id,
                "type": _infer_v2_type(
                    task_el.tag if task_el is not None else "",
                    tid,
                    None,
                ),
                "description": docs or "Added from BPMN canvas",
            }
        new_steps.append(step)

    updated = dict(v2_blueprint)
    updated["steps"] = new_steps

    gateways = _sync_gateways(root)
    if gateways:
        updated["gateways"] = gateways

    data_labels = _sync_data_object_names(root, v2_blueprint)
    if data_labels:
        artifact_to_step = _artifact_step_map(v2_blueprint)
        old_step_names = {
            str(step.get("id")): str(step.get("name") or "")
            for step in list(v2_blueprint.get("steps") or [])
            if step.get("id")
        }
        # If the user renamed the data object that the generator synthesized from a
        # V2 step, mirror that label back to the producing step name as well.
        # But keep explicit task renames authoritative: data objects only update
        # steps that still match the original step name.
        step_label_updates: dict[str, str] = {}
        for artifact_id, label in data_labels.items():
            if artifact_id not in artifact_to_step or not label.strip():
                continue
            # Generator labels slug ids as Title Case (sy_te4 → Sy Te4). Only mirror
            # data-object edits back to steps when the canvas label is not that default.
            if label.strip() == _humanize_artifact_id(artifact_id):
                continue
            step_id = artifact_to_step[artifact_id]
            current = next(
                (
                    str(step.get("name") or "")
                    for step in updated["steps"]
                    if str(step.get("id")) == step_id
                ),
                "",
            )
            original = old_step_names.get(step_id, "")
            if current == original:
                step_label_updates[step_id] = label
        if step_label_updates:
            updated["steps"] = [
                {
                    **step,
                    "name": step_label_updates.get(str(step.get("id")), step.get("name", "")),
                }
                for step in updated["steps"]
            ]
        updated["data_objects"] = {
            **dict(v2_blueprint.get("data_objects") or {}),
            **data_labels,
        }

    return updated
