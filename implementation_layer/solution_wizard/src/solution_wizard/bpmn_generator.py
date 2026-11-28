"""BPMN 2.0 generator -- produces a standards-based, Level-2 business-process
model (BPMN 2.0 XML + BPMNDI auto-layout) from a Blueprint.

Design contract (linked-by-derivation, one-directional):
  * The BPMN is *generated* from the blueprint JSON. It is never the source of
    truth and is never hand-edited. The agent keeps it in sync by editing the
    JSON and regenerating.
  * Every generated element carries a stable id that maps back to its blueprint
    object. The map is written to ``blueprint.visualizations["bpmn_mapping"]``.
  * Business richness lives in the JSON: partly *derived by enrichment
    conventions* from existing metadata (human_review -> approval gateway +
    rework loop; integration_targets -> data store + send task; multi-dependency
    -> parallel fork/join; governance -> annotations), partly from the optional
    ``business_process`` section (extra lanes/pools, manual steps, message
    flows, exceptions, decision points).

No third-party dependencies: the XML is emitted as text and is well-formed,
with a complete ``<bpmndi:BPMNDiagram>`` (a BPMNShape for every flow node /
data element / pool / lane and a BPMNEdge for every flow / association) so it
renders in bpmn-js, Camunda Modeler and draw.io.

Public API mirrors ``visualizer.py``:
    generate_bpmn(blueprint) -> str
    write_bpmn(blueprint, output_dir) -> Path   # writes workflow.bpmn
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .blueprint import Blueprint, Participant

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

POOL_X = 160
POOL_Y = 90
POOL_LABEL_W = 30  # left band of a horizontal pool (rotated name)
LANE_LABEL_W = 30  # left band of a lane inside the pool
CONTENT_X0 = POOL_X + POOL_LABEL_W + LANE_LABEL_W + 30  # first node column centre-ish
X_SPACING = 200  # horizontal distance between ranks
COL_W = 100  # nominal column width (for column centring)
# Each row inside a lane is split into a data-object zone (top) and the task zone.
# Task labels follow official BPMN conventions (verb-object, optional [CODE] prefix)
# and sit inside the shape — no custom caption overlay zone.
ROW_DATA_H = 95  # data-object zone height per row (gap above the task)
TASK_LABEL_H = 24  # small gap between data objects and the task box
ROW_TASK_H = 120  # task zone height per row
ROW_H = ROW_DATA_H + TASK_LABEL_H + ROW_TASK_H
DATA_OBJ_TOP_PAD = 8  # gap from the row top to the data object
LANE_PAD_TOP = 22  # padding at the top of a lane
LANE_PAD_BOTTOM = 22  # padding at the bottom of a lane
DATA_OBJ_GAP = 70  # horizontal gap between several data objects of one task
BASE_LANE_H = 300  # minimum lane height (swimlane readability)
EXT_POOL_H = 70
EXT_POOL_GAP = 30

# Standard BPMN element sizes (Camunda / bpmn-js friendly).
SIZE = {
    "event": (36, 36),
    "task": (130, 80),
    "gateway": (50, 50),
    "dataObject": (36, 50),
    "dataStore": (50, 50),
    "annotation": (180, 50),
}

# Short component codes for implementation-level task labels (GAIK modeling guide).
# Format: "[STR] Transcribe Audio" — readable name first; code is optional aid.
_COMPONENT_CODES: Dict[str, str] = {
    "Transcriber": "STR",
    "WhisperTranscriber": "STR",
    "transcriber": "STR",
    "whisper": "STR",
    "DataExtractor": "SE",
    "Extractor": "SE",
    "extractor": "SE",
    "data_extractor": "SE",
    "SchemaGenerator": "SSG",
    "schema_generator": "SSG",
    "RequirementParser": "RP",
    "PyMuPDFParser": "PAR",
    "DoclingParser": "PAR",
    "parser": "PAR",
    "LLMJudge": "JUD",
    "EnhanceTranscript": "ENH",
    "enhance_transcript": "ENH",
    "TextToSpeech": "TTS",
    "tts": "TTS",
    "Classifier": "CLS",
    "classifier": "CLS",
    "AudioToStructuredData": "A2S",
    "DocumentsToStructuredData": "D2S",
    "RAGWorkflow": "RAG",
    "rag": "RAG",
    "pgvector": "RAG",
}


def _component_code(component: Optional[str]) -> Optional[str]:
    """Return a short bracket code for a GAIK component, or None."""
    if not component:
        return None
    if component in _COMPONENT_CODES:
        return _COMPONENT_CODES[component]
    # Case-insensitive lookup for common aliases (UI may send lowercase ids).
    lower_map = {k.lower(): v for k, v in _COMPONENT_CODES.items()}
    hit = lower_map.get(component.lower())
    if hit:
        return hit
    # CamelCase / snake_case → up to 3 uppercase initials
    parts = re.findall(r"[A-Z][a-z]*|[a-z]+|[0-9]+", component.replace("-", "_"))
    if not parts:
        return component[:3].upper()
    initials = "".join(p[0].upper() for p in parts if p)
    return (initials or component[:3].upper())[:4]


def _humanize_token(token: str) -> str:
    """snake_case / camelCase / kebab → Title Case words."""
    spaced = re.sub(r"[_\-]+", " ", str(token))
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", spaced)
    return " ".join(w.capitalize() for w in spaced.split() if w)


# Prefer type-based data-object labels when the artifact id is opaque.
_ARTIFACT_TYPE_LABELS: Dict[str, str] = {
    "audio": "Audio File",
    "pdf": "PDF Document",
    "image": "Image",
    "video": "Media File",
    "transcript": "Transcript",
    "parsed_text": "Parsed Text",
    "text": "Text",
    "structured_json": "Structured JSON",
    "validation_report": "Validation Report",
    "schema": "Extraction Schema",
    "subtitle": "Subtitle File",
    "index": "Search Index",
}


def _data_object_label(art_id: str, art: Any = None) -> str:
    """Human-readable data object name (official BPMN samples + modeling guide)."""
    label = str(getattr(art, "label", "") or "").strip()
    if label:
        return label
    type_key = ""
    if art is not None:
        type_key = str(getattr(art, "type", "") or "").lower()
    # Exact id matches known type labels (e.g. structured_json → Structured JSON).
    if art_id in _ARTIFACT_TYPE_LABELS:
        return _ARTIFACT_TYPE_LABELS[art_id]
    # Prefer a readable id (voice_note_audio → Voice Note Audio) unless it is
    # a generic placeholder like src/out/artifact_*.
    opaque = bool(re.fullmatch(r"(src|out|input|output|data|artifact)(_\w+)?", art_id, re.I))
    if not opaque and art_id:
        return _humanize_token(art_id)
    if type_key in _ARTIFACT_TYPE_LABELS:
        return _ARTIFACT_TYPE_LABELS[type_key]
    if type_key:
        return _humanize_token(type_key)
    return _humanize_token(art_id) if art_id else "Data"


# ---------------------------------------------------------------------------
# Derived lanes
# ---------------------------------------------------------------------------

#: The lanes drawn when business_process.participants is empty, per node
#: category: (participant id, lane id, lane priority, bpmn_mapping path).
_DERIVED_LANES: dict[str, tuple[str, str, int, str]] = {
    "user": ("users", "Lane_users", 0, "derived:business_spec.intended_users"),
    "ai": ("system", "Lane_gaik_ai", 1, "derived:system"),
    "review": ("reviewers", "Lane_reviewers", 2, "derived:business_spec.reviewers"),
}
#: The ids of the derived participants; a step's performed_by may name one when
#: there are no participants.
DERIVED_PARTICIPANT_IDS = frozenset(spec[0] for spec in _DERIVED_LANES.values())


def _derived_participant(blueprint: Blueprint, category: str) -> Participant:
    """The participant behind the derived lane of a node category."""
    spec = blueprint.business_spec if isinstance(blueprint.business_spec, dict) else {}
    if category == "ai":
        # Official GAIK samples use "GenAI" for the software/AI lane.
        return Participant(
            id="system", name="GenAI", kind="system", default_lane_for=["automated_task"]
        )
    if category == "review":
        reviewers = spec.get("reviewers") or []
        name = (
            " / ".join(r.replace("_", " ").title() for r in reviewers) if reviewers else "Reviewer"
        )
        return Participant(id="reviewers", name=name, default_lane_for=["human_review"])
    users = spec.get("intended_users") or []
    name = " / ".join(u.replace("_", " ").title() for u in users) if users else "User"
    return Participant(id="users", name=name, default_lane_for=["user_task"])


def derived_participants(blueprint: Blueprint) -> list[Participant]:
    """The participants behind the lanes the generator derives when
    ``business_process.participants`` is empty, in lane order.

    Only the lanes the generator would draw are returned. Setting the result as
    the participants draws the same lanes, with the same names, in the same order.
    """
    if not blueprint.workflow.steps:
        return []
    process = blueprint.business_process.model_copy(update={"participants": []})
    builder = _BpmnBuilder(blueprint.model_copy(update={"business_process": process}))
    builder.build()
    category_of = {lane_id: category for category, (_, lane_id, _, _) in _DERIVED_LANES.items()}
    ordered = sorted(builder.lanes.values(), key=lambda lane: (lane.priority, lane.id))
    return [
        _derived_participant(blueprint, category_of[lane.id])
        for lane in ordered
        if lane.id in category_of
    ]


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape text for use in XML attribute values and element text."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _safe(token: str) -> str:
    """Make a blueprint id safe for use as an XML id fragment."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in str(token))


# ---------------------------------------------------------------------------
# Internal model objects
# ---------------------------------------------------------------------------


class _Node:
    """A BPMN flow node (event, task, gateway)."""

    def __init__(self, nid: str, tag: str, name: str, lane: str, size_key: str):
        self.id = nid
        self.tag = tag  # e.g. "bpmn:userTask"
        self.name = name
        self.lane = lane  # lane id
        self.w, self.h = SIZE[size_key]
        self.documentation = ""
        self.rank = 0
        self.x = 0
        self.y = 0
        self.incoming: List[str] = []  # sequence flow ids
        self.outgoing: List[str] = []
        # data associations attached to this node (tasks only)
        self.data_in: List[Tuple[str, str, str]] = []  # (assoc_id, dataobjref_id, property_id)
        self.data_out: List[Tuple[str, str]] = []  # (assoc_id, dataobjref_id)

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class _Flow:
    def __init__(self, fid: str, src: str, tgt: str, name: str = "", is_loop: bool = False):
        self.id = fid
        self.src = src
        self.tgt = tgt
        self.name = name
        self.is_loop = is_loop


class _Lane:
    def __init__(self, lid: str, name: str, priority: int):
        self.id = lid
        self.name = name
        self.priority = priority
        self.members: List[str] = []  # flow node ids
        self.top = 0.0
        self.height = float(BASE_LANE_H)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


#: The lane priority of the first extra lane (``generate_bpmn``'s
#: ``extra_lane_ids``): after every other lane, in the participants' order.
_EXTRA_LANE_PRIORITY = 10


class _BpmnBuilder:
    def __init__(
        self,
        blueprint: Blueprint,
        include_data_objects: bool = True,
        extra_lane_ids: frozenset[str] = frozenset(),
    ):
        self.bp = blueprint
        self.extra_lane_ids = frozenset(extra_lane_ids)
        # Without data objects the per-row data band is not reserved, so every
        # row (and the minimum lane height) loses ROW_DATA_H.
        self.include_data_objects = include_data_objects
        self.row_data_h = ROW_DATA_H if include_data_objects else 0
        self.row_h = self.row_data_h + TASK_LABEL_H + ROW_TASK_H
        self.base_lane_h = BASE_LANE_H if include_data_objects else BASE_LANE_H - ROW_DATA_H
        self.nodes: Dict[str, _Node] = {}
        self.lanes: Dict[str, _Lane] = {}
        self.flows: List[_Flow] = []
        self.msg_flows: List[Tuple[str, str, str, str]] = []  # id, src, tgt, name
        self.ext_pools: List[Tuple[str, str]] = []  # id, name
        self.data_objs: List[Tuple[str, str, str, str]] = []  # refid, objid, name, artifact_id
        self.data_stores: List[Tuple[str, str, str]] = []  # id, name, target
        self.annotations: List[Tuple[str, str]] = []  # id, text
        self.assocs: List[Tuple[str, str, str]] = []  # id, src(annotation), tgt(node)
        self.mapping: Dict[str, Dict[str, str]] = {}
        # unified geometry store: element id -> (x, y, w, h). Populated during
        # layout for every drawable element (flow nodes, data objects, data
        # stores, annotations, external pools) so edge routing never has to
        # guess a position.
        self.bounds: Dict[str, Tuple[float, float, float, float]] = {}
        # row index (stacking slot) each flow node was placed in, used to put a
        # task's data objects in that task's own row data-zone.
        self.node_row: Dict[str, int] = {}
        self._flow_seq = 0
        self._assoc_seq = 0
        self._msg_seq = 0
        self._prop_seq = 0
        # placement helper used by integration splice
        self._approval_gateways: List[str] = []
        # review step id -> (its approval gateway, the approval's "Yes" flows)
        self._approval_of: Dict[str, Tuple[str, List[_Flow]]] = {}
        self._dataobj_ref_for_artifact: Dict[str, str] = {}
        # exception ids consumed by _enrich_approval (discard path); skipped by _enrich_exceptions
        self._consumed_exception_ids: set = set()

    # -- id allocators ----------------------------------------------------

    def _next_flow_id(self) -> str:
        self._flow_seq += 1
        return f"Flow_{self._flow_seq}"

    def _next_assoc_id(self) -> str:
        self._assoc_seq += 1
        return f"Association_{self._assoc_seq}"

    def _next_msg_id(self) -> str:
        self._msg_seq += 1
        return f"MessageFlow_{self._msg_seq}"

    def _next_prop_id(self) -> str:
        self._prop_seq += 1
        return f"Property_{self._prop_seq}"

    def _map(self, element_id: str, kind: str, blueprint_path: str) -> None:
        self.mapping[element_id] = {"kind": kind, "blueprint_path": blueprint_path}

    # -- lanes ------------------------------------------------------------

    def _participant_lane(self, predicate) -> Optional[Tuple[str, str, int]]:
        """Return (lane_id, name, priority) for the first business_process
        participant matching predicate, or None."""
        for i, p in enumerate(self.bp.business_process.participants):
            if predicate(p):
                lid = f"Lane_{_safe(p.id)}"
                if lid not in self.mapping:
                    self._map(lid, "lane", f"business_process.participants[{i}]")
                return lid, p.name, self._priority(p)
        return None

    def _priority(self, p) -> int:
        """A participant's lane order: an extra lane (``extra_lane_ids``) after
        every other lane, in the participants' order; else by its role."""
        if getattr(p, "id", None) in self.extra_lane_ids:
            ids = [q.id for q in self.bp.business_process.participants]
            return _EXTRA_LANE_PRIORITY + ids.index(p.id)
        return self._participant_priority(p)

    @staticmethod
    def _participant_priority(p) -> int:
        """Lane order of a participant, from its role, so the lane keeps its
        place however a node reaches it (a category or a step's performed_by):
        users 0, the system 1, reviewers 2, as the derived lanes."""
        lanes_for = getattr(p, "default_lane_for", [])
        if getattr(p, "kind", "") == "system" or "automated_task" in lanes_for:
            return _DERIVED_LANES["ai"][2]
        if "human_review" in lanes_for and "user_task" not in lanes_for:
            return _DERIVED_LANES["review"][2]
        return _DERIVED_LANES["user"][2]

    def _ensure_lane(self, lid: str, name: str, priority: int) -> str:
        if lid not in self.lanes:
            self.lanes[lid] = _Lane(lid, name, priority)
        return lid

    def _lane_for_category(self, category: str) -> str:
        """Resolve a lane id for a node category, creating lanes lazily.

        Categories: 'user', 'ai', 'review', 'manual'. Without a matching
        participant the lane is the derived one (``_derived_participant``).
        """
        if category == "ai":
            hit = self._participant_lane(lambda p: getattr(p, "kind", "") == "system")
        elif category == "review":
            hit = self._participant_lane(
                lambda p: "human_review" in getattr(p, "default_lane_for", [])
            )
        else:  # user / manual default
            category = "user"
            hit = self._participant_lane(
                lambda p: "user_task" in getattr(p, "default_lane_for", [])
            )
        _, lid, priority, source = _DERIVED_LANES[category]
        if hit:
            return self._ensure_lane(*hit)
        lid = self._ensure_lane(lid, _derived_participant(self.bp, category).name, priority)
        if lid not in self.mapping:
            self._map(lid, "lane", source)
        return lid

    def _lane_for_participant(self, participant_id: str, fallback_category: str) -> str:
        for i, p in enumerate(self.bp.business_process.participants):
            if p.id == participant_id:
                lid = f"Lane_{_safe(p.id)}"
                if lid not in self.mapping:
                    self._map(lid, "lane", f"business_process.participants[{i}]")
                return self._ensure_lane(lid, p.name, self._priority(p))
        if not self.bp.business_process.participants:
            # Derived lanes: a derived participant id names its lane.
            for category, (derived_id, _, _, _) in _DERIVED_LANES.items():
                if derived_id == participant_id:
                    return self._lane_for_category(category)
        # An unknown id falls back to the category lane (validator rule 16 reports it).
        return self._lane_for_category(fallback_category)

    # -- step -> node -----------------------------------------------------

    def _step_node_id(self, step) -> str:
        if step.type == "decision":
            return f"Gateway_{_safe(step.id)}"
        return f"Activity_{_safe(step.id)}"

    def _step_display_name(self, step) -> str:
        """Official BPMN task naming: verb-object; optional [CODE] for automated steps.

        Matches GAIK modeling guide + public/bpmn/official samples — no custom
        ``\\n[User input]`` / ``\\n[Component]`` caption suffixes.
        """
        name = (step.name or step.id or "").strip()
        if step.type == "automated_task" and step.component:
            code = _component_code(step.component)
            if code:
                return f"[{code}] {name}"
        return name

    def _build_step_nodes(self) -> None:
        steps = self.bp.workflow.steps
        for i, step in enumerate(steps):
            nid = self._step_node_id(step)
            if step.type == "user_task":
                tag, size, category = "bpmn:userTask", "task", "user"
            elif step.type == "human_review":
                tag, size, category = "bpmn:userTask", "task", "review"
            elif step.type == "decision":
                tag, size, category = "bpmn:exclusiveGateway", "gateway", "ai"
            else:  # automated_task
                tag, size, category = "bpmn:serviceTask", "task", "ai"
            if step.performed_by:
                lane = self._lane_for_participant(step.performed_by, category)
            else:
                lane = self._lane_for_category(category)
            name = self._step_display_name(step)
            node = _Node(nid, tag, name, lane, size)
            node.documentation = (step.description or "").strip()
            self.nodes[nid] = node
            self._map(nid, step.type, f"workflow.steps[{i}]")

    # -- manual steps (business_process) ----------------------------------

    def _build_manual_steps(self) -> None:
        for i, ms in enumerate(self.bp.business_process.manual_steps):
            nid = f"Activity_{_safe(ms.id)}"
            tag = "bpmn:manualTask" if ms.type == "manual_task" else "bpmn:userTask"
            lane = self._lane_for_participant(ms.performed_by, "user")
            node = _Node(nid, tag, ms.name, lane, "task")
            self.nodes[nid] = node
            self._map(nid, "manual_step", f"business_process.manual_steps[{i}]")

    def _build_participant_lanes(self) -> None:
        """The extra lanes (``extra_lane_ids``) are drawn also while no step is
        in them, so a step can be moved into a lane the user added. Other
        participants are lanes only when a node reaches them."""
        for i, p in enumerate(self.bp.business_process.participants):
            if p.id not in self.extra_lane_ids:
                continue
            lid = f"Lane_{_safe(p.id)}"
            if lid not in self.mapping:
                self._map(lid, "lane", f"business_process.participants[{i}]")
            self._ensure_lane(lid, p.name, self._priority(p))

    # -- base sequence-flow graph -----------------------------------------

    def _add_flow(self, src: str, tgt: str, name: str = "", is_loop: bool = False) -> _Flow:
        f = _Flow(self._next_flow_id(), src, tgt, name, is_loop)
        self.flows.append(f)
        return f

    def _build_base_edges(self) -> None:
        steps = self.bp.workflow.steps
        step_ids = {s.id for s in steps}
        node_of = {s.id: self._step_node_id(s) for s in steps}

        # dependents in the step graph
        dependents: Dict[str, List[str]] = {s.id: [] for s in steps}
        for s in steps:
            for dep in s.depends_on:
                if dep in dependents:
                    dependents[dep].append(s.id)

        # manual step dependencies fold into the same graph
        manual_node_of = {
            ms.id: f"Activity_{_safe(ms.id)}" for ms in self.bp.business_process.manual_steps
        }
        all_node_of = {**node_of, **manual_node_of}

        # 1. raw step->step edges
        raw_edges: List[Tuple[str, str]] = []
        for s in steps:
            for dep in s.depends_on:
                if dep in all_node_of:
                    raw_edges.append((dep, s.id))
        for ms in self.bp.business_process.manual_steps:
            for dep in ms.depends_on:
                if dep in all_node_of:
                    raw_edges.append((dep, ms.id))

        indeg: Dict[str, int] = {}
        outdeg: Dict[str, int] = {}
        for a, b in raw_edges:
            outdeg[a] = outdeg.get(a, 0) + 1
            indeg[b] = indeg.get(b, 0) + 1

        # 2. start event -> entry steps (no dependencies)
        # Descriptive start/end names match official samples ("Started …").
        uc_name = (self.bp.use_case.name or "Process").strip()
        start = _Node(
            "StartEvent_1",
            "bpmn:startEvent",
            f"Started {uc_name}",
            "",
            "event",
        )
        self.nodes["StartEvent_1"] = start
        self._map("StartEvent_1", "start_event", "derived:start")

        entry_steps = [s for s in steps if not s.depends_on]
        # manual steps with no deps are also entries
        entry_manual = [ms for ms in self.bp.business_process.manual_steps if not ms.depends_on]
        # place start event in the lane of the first entry node
        first_entry_node = None
        if entry_steps:
            first_entry_node = node_of[entry_steps[0].id]
        elif entry_manual:
            first_entry_node = manual_node_of[entry_manual[0].id]
        start.lane = (
            self.nodes[first_entry_node].lane
            if first_entry_node
            else self._lane_for_category("user")
        )

        for s in entry_steps:
            self._add_flow("StartEvent_1", node_of[s.id])
        for ms in entry_manual:
            self._add_flow("StartEvent_1", manual_node_of[ms.id])

        # 3. main edges with parallel fork/join enrichment
        # forks: a step with >=2 dependents. Not after a step of type "decision":
        # it is drawn as an exclusive gateway, and its dependents are the ways it
        # chooses between, not steps that all run.
        fork_of: Dict[str, str] = {}
        for sid in list(all_node_of):
            if self.nodes[all_node_of[sid]].tag == "bpmn:exclusiveGateway":
                continue
            if outdeg.get(sid, 0) >= 2:
                pf = f"Gateway_fork_{_safe(sid)}"
                self.nodes[pf] = _Node(
                    pf, "bpmn:parallelGateway", "", self.nodes[all_node_of[sid]].lane, "gateway"
                )
                self._map(pf, "parallel_fork", f"derived:fork_after:{sid}")
                fork_of[sid] = pf
                self._add_flow(all_node_of[sid], pf)

        # joins: a step with >=2 dependencies
        join_of: Dict[str, str] = {}
        for sid in list(all_node_of):
            if indeg.get(sid, 0) >= 2:
                pj = f"Gateway_join_{_safe(sid)}"
                self.nodes[pj] = _Node(
                    pj, "bpmn:parallelGateway", "", self.nodes[all_node_of[sid]].lane, "gateway"
                )
                self._map(pj, "parallel_join", f"derived:join_before:{sid}")
                join_of[sid] = pj
                self._add_flow(pj, all_node_of[sid])

        for a, b in raw_edges:
            src_node = fork_of.get(a, all_node_of[a])
            tgt_node = join_of.get(b, all_node_of[b])
            self._add_flow(src_node, tgt_node)

        # 4. end event(s) from terminal steps
        uc_name = (self.bp.use_case.name or "Process").strip()
        end = _Node(
            "EndEvent_success",
            "bpmn:endEvent",
            f"{uc_name} completed",
            "",
            "event",
        )
        self.nodes["EndEvent_success"] = end
        self._map("EndEvent_success", "end_event", "derived:end")
        terminal = [s for s in steps if not dependents[s.id]]
        terminal_manual = [
            ms
            for ms in self.bp.business_process.manual_steps
            if ms.id not in {d for deps in dependents.values() for d in deps}
            and not any(ms.id in m.depends_on for m in self.bp.business_process.manual_steps)
        ]
        last_lane = None
        for s in terminal:
            self._add_flow(node_of[s.id], "EndEvent_success")
            last_lane = self.nodes[node_of[s.id]].lane
        for ms in terminal_manual:
            self._add_flow(manual_node_of[ms.id], "EndEvent_success")
            last_lane = self.nodes[manual_node_of[ms.id]].lane
        end.lane = last_lane or self._lane_for_category("ai")

    # -- enrichment: human_review approval gateway + rework loop ----------

    def _enrich_approval(self) -> None:
        steps = self.bp.workflow.steps
        review_steps = [s for s in steps if s.type == "human_review"]
        # also honour technical_spec.human_review_required when no explicit
        # human_review step exists but a final output is produced -> skip
        # (we only add a gateway when there is a concrete review step).
        for s in review_steps:
            hid = self._step_node_id(s)
            xg = f"Gateway_approve_{_safe(s.id)}"
            self.nodes[xg] = _Node(
                xg, "bpmn:exclusiveGateway", "Approved?", self.nodes[hid].lane, "gateway"
            )
            self._map(xg, "approval_gateway", f"derived:approval_after:{s.id}")
            self._approval_gateways.append(xg)

            # redirect outgoing edges of the review step through the gateway
            outgoing = [f for f in self.flows if f.src == hid]
            for f in outgoing:
                f.src = xg
                if not f.name:
                    f.name = "Yes"
            self._add_flow(hid, xg)
            # A decision after the review follows these (see _enrich_decision_points).
            self._approval_of[s.id] = (xg, [f for f in outgoing if not f.is_loop])

            # Determine the "No" path from the available exceptions and the blueprint's
            # explicit intent. Priority order:
            #
            # 1. outcome="end"  → discard: a dedicated "Rejected" end event in the
            #    reviewer's lane (already supported).
            # 2. outcome="loop_to:<step_id>"  → rework: loop back to the named step.
            #    If that step is a user_task (employee), the loop correctly returns to the
            #    employee for correction. If it is an automated_task, the loop goes there.
            # 3. No matching exception  → DEFAULT: a clean "Rejected" end event.
            #    We do NOT automatically generate a rework loop to an AI extraction step;
            #    that path is almost always semantically wrong (supervisor rejection should
            #    end the process unless the blueprint explicitly says otherwise).

            # Case 1 & default case 3: discard end event.
            discard_ex = next(
                (
                    ex
                    for ex in self.bp.business_process.exceptions
                    if ex.attached_to == s.id and ex.outcome == "end"
                ),
                None,
            )
            # Case 2: explicit loop_to rework exception.
            loop_ex = next(
                (
                    ex
                    for ex in self.bp.business_process.exceptions
                    if ex.attached_to == s.id and ex.outcome.startswith("loop_to:")
                ),
                None,
            )

            if loop_ex is not None:
                # Explicit rework loop to a named step (may be employee or AI).
                target_step_id = loop_ex.outcome.split(":", 1)[1].strip()
                target_node = self._lookup_node_for_step(target_step_id)
                if target_node:
                    self._add_flow(
                        xg, target_node, name=loop_ex.condition or "No (rework)", is_loop=True
                    )
                    self._consumed_exception_ids.add(loop_ex.id)
                else:
                    # Named step not found; fall back to a rejected end event.
                    self._add_rejection_end(xg, s.id)
            elif discard_ex is not None:
                # Explicit "end" exception (discard).
                rej_end = f"EndEvent_{_safe(discard_ex.id)}"
                self.nodes[rej_end] = _Node(
                    rej_end,
                    "bpmn:endEvent",
                    discard_ex.name or "Rejected",
                    self.nodes[xg].lane,
                    "event",
                )
                self._map(rej_end, "end_event", f"business_process.exceptions.{discard_ex.id}")
                self._add_flow(xg, rej_end, name=discard_ex.condition or "No")
                self._consumed_exception_ids.add(discard_ex.id)
            else:
                # Default (no exception defined): a clean "Rejected" end event.
                # We do NOT loop back to an AI step — that would be semantically wrong
                # for any supervisor-rejection scenario without an explicit rework path.
                self._add_rejection_end(xg, s.id)

    def _add_rejection_end(self, gateway_id: str, review_step_id: str) -> None:
        """Add a 'Rejected' end event connected from the given gateway."""
        rej_end = f"EndEvent_rejected_{_safe(review_step_id)}"
        if rej_end not in self.nodes:
            self.nodes[rej_end] = _Node(
                rej_end,
                "bpmn:endEvent",
                "Rejected",
                self.nodes[gateway_id].lane,
                "event",
            )
            self._map(rej_end, "end_event", f"derived:rejection_after:{review_step_id}")
        self._add_flow(gateway_id, rej_end, name="No")

    def _rework_target_for(self, review_step) -> Optional[str]:
        """The step a rejected review loops back to: the automated_task that
        produced the reviewed record, else the nearest upstream automated step."""
        artifacts = self.bp.artifacts
        for art_id in review_step.inputs:
            art = artifacts.get(art_id)
            if art and art.produced_by:
                producer = art.produced_by
                # only loop back to an automated task
                for s in self.bp.workflow.steps:
                    if s.id == producer and s.type == "automated_task":
                        return self._step_node_id(s)
        # fallback: last automated_task before the review in list order
        prior_auto = [s for s in self.bp.workflow.steps if s.type == "automated_task"]
        if prior_auto:
            return self._step_node_id(prior_auto[-1])
        return None

    # -- one way into the success end, for the boxes every success passes --

    def _reaching(self, into: List[_Flow]) -> Dict[str, set]:
        """For each flow, the ids of the flows in ``into`` it leads to, itself
        included, up to the first of them on each path; loops are left out.

        Walked back once from each of ``into``, not forward again from every way
        out of every gateway: that took 27 s for a blueprint of 200 steps.
        """
        ids = {f.id for f in into}
        by_tgt: Dict[str, List[_Flow]] = {}
        for f in self.flows:
            if not f.is_loop:
                by_tgt.setdefault(f.tgt, []).append(f)
        reaching: Dict[str, set] = {}
        for last in into:
            seen, todo = {last.id}, [last]
            while todo:
                f = todo.pop()
                reaching.setdefault(f.id, set()).add(last.id)
                for prev in by_tgt.get(f.src, ()):
                    if prev.id not in seen and prev.id not in ids:
                        seen.add(prev.id)
                        todo.append(prev)
        return reaching

    def _meeting_kind(self, into: List[_Flow]) -> str:
        """The gateway where the flows ``into`` meet.

        Only a split with at least two ways out that lead to different ones of
        these flows counts: a review's "No" to a rejection end, or a path that
        ends without success, is no choice between them, and neither are ways
        that all lead to the same flows (a decision whose branches meet again
        before them, or one that sends a case back to an earlier step). When an
        exclusive split counts, one of the flows runs (an exclusive gateway);
        when only parallel ones (or none), all do (a parallel join). Both at
        once (a decision's ending beside steps that all run) would be an
        inclusive gateway, which the diagram's readers do not know yet: it is
        drawn exclusive.
        """
        reaching = self._reaching(into)
        ways_of: Dict[str, List[_Flow]] = {}
        for f in self.flows:
            if not f.is_loop:
                ways_of.setdefault(f.src, []).append(f)
        kinds = set()
        for node in self.nodes.values():
            if node.tag not in ("bpmn:exclusiveGateway", "bpmn:parallelGateway"):
                continue
            reached = {
                frozenset(reaching[f.id]) for f in ways_of.get(node.id, ()) if f.id in reaching
            }
            if len(reached) >= 2:
                kinds.add(node.tag)
        if "bpmn:exclusiveGateway" in kinds:
            return "bpmn:exclusiveGateway"
        return "bpmn:parallelGateway"

    def _settle_joins(self) -> None:
        """A join before a step that depends on several steps waits for all of
        them; after a decision, they can be alternatives, and the join would wait
        for ever. Each join becomes the gateway its incoming flows meet at."""
        for node in list(self.nodes.values()):
            # Known by its mapping, not its id: a workflow step of type "decision"
            # with an id like join_check is drawn as Gateway_join_check too.
            if self.mapping.get(node.id, {}).get("kind") != "parallel_join":
                continue
            into = [f for f in self.flows if f.tgt == node.id and not f.is_loop]
            if len(into) > 1:
                node.tag = self._meeting_kind(into)

    def _success_entry(self) -> Optional[_Flow]:
        """The one flow into the success end that a PDF task or a send task is
        spliced onto, so that every successful path passes it.

        Before, each box was spliced onto one of the flows into the end, so with
        an auto-approval beside a review (two ways to finish) the report and the
        submission landed on different paths. Several flows into the end now meet
        first, at the gateway `_meeting_kind` picks: exclusive when only one of
        them runs (a decision), parallel when they all do.
        """
        into_end = [f for f in self.flows if f.tgt == "EndEvent_success" and not f.is_loop]
        if not into_end:
            return None
        if len(into_end) == 1:
            return into_end[0]
        # A workflow step of type "decision" is drawn as Gateway_<its id>: one
        # with the id merge_success keeps that element, and the merge takes a
        # free id.
        merge_id, n = "Gateway_merge_success", 2
        while merge_id in self.nodes:
            merge_id, n = f"Gateway_merge_success_{n}", n + 1
        kind = self._meeting_kind(into_end)
        self.nodes[merge_id] = _Node(
            merge_id, kind, "", self.nodes["EndEvent_success"].lane, "gateway"
        )
        self._map(merge_id, "merge_gateway", "derived:merge_before_end")
        for f in into_end:
            f.tgt = merge_id
        return self._add_flow(merge_id, "EndEvent_success")

    # -- enrichment: integration target -> data store + send task ---------

    def _enrich_integration(self) -> None:
        spec = self.bp.technical_spec if isinstance(self.bp.technical_spec, dict) else {}
        targets = spec.get("integration_targets") or []
        if not targets:
            return
        for idx, target in enumerate(targets):
            ds_id = f"DataStore_{_safe(target)}"
            ds_name = _humanize_token(target)
            # Persistent repositories use clean names (e.g. "Incident Reporting Database").
            if not ds_name.lower().endswith(("database", "repository", "system", "store")):
                ds_label = f"{ds_name} Repository"
            else:
                ds_label = ds_name
            self.data_stores.append((ds_id, ds_label, target))
            self._map(ds_id, "data_store", f"technical_spec.integration_targets[{idx}]")

            send_id = f"Activity_submit_{_safe(target)}"
            send_node = _Node(
                send_id,
                "bpmn:sendTask",
                f"Submit to {ds_name}",
                self._lane_for_category("ai"),
                "task",
            )
            self.nodes[send_id] = send_node
            self._map(send_id, "send_task", f"derived:submit:{target}")
            send_node.data_out.append((self._next_assoc_id(), ds_id))

            # Splice the send task onto the one way into the success end, so every
            # successful path submits (after the PDF report, which is spliced
            # first); a further target is spliced after the previous send task.
            chosen = self._success_entry()
            if chosen is not None:
                # src -> send_task -> end (keep the original edge name on src->send)
                end_target = chosen.tgt
                chosen.tgt = send_id
                self._add_flow(send_id, end_target)
            else:
                # no end edge yet (unusual) -- attach send task after the last terminal
                self._add_flow(send_id, "EndEvent_success")

    # -- enrichment: PDF generation service task --------------------------

    def _enrich_pdf_generation(self) -> None:
        """When `output_types` includes 'pdf' and no explicit PDF-generation step
        exists in the workflow, inject a synthetic service task in the GAIK AI lane
        labelled 'Generate PDF report'.

        Placement (generic across use cases): the PDF report is the rendering of
        the *approved final output*, so it is spliced onto the success path as
        late as possible, on the one way into the success end
        (`_success_entry()`): the approved ("Yes") edge when a review is the only
        way to finish, so the reviewer approves the content *before* the PDF is
        rendered; the point where all the ways to finish meet when there are
        several (an auto-approval beside a review), so every one renders it.
        This runs before `_enrich_integration()`, so a subsequent Send Task is
        spliced *after* the PDF -- the natural "generate the report, then submit
        it" order.

        Nothing is added when the workflow already contains an explicit step whose
        id or component names a PDF/report generator (case-insensitive), so
        intentionally modelled blueprints are never double-counted.
        """
        spec = self.bp.technical_spec if isinstance(self.bp.technical_spec, dict) else {}
        out = spec.get("output_types") or []
        if isinstance(out, str):
            out = [out]
        if not any(str(o).lower() in ("pdf", "report") for o in out):
            return

        # Skip if an explicit PDF generation step is already in the workflow.
        for s in self.bp.workflow.steps:
            sid_low = s.id.lower()
            comp_low = (s.component or "").lower()
            if (
                "pdf" in sid_low
                or "pdf" in comp_low
                or "report_gen" in sid_low
                or "report_gen" in comp_low
            ):
                return

        pdf_id = "Activity_generate_pdf"
        pdf_node = _Node(
            pdf_id,
            "bpmn:serviceTask",
            "Generate PDF report",
            self._lane_for_category("ai"),
            "task",
        )
        self.nodes[pdf_id] = pdf_node
        self._map(pdf_id, "pdf_generation", "derived:pdf_output")

        # The one way into the success end: the approved ("Yes") flow when a review
        # is the only way to finish, else the point where all the ways meet, so
        # every successful path renders the report.
        splice_edge = self._success_entry()

        if splice_edge is not None:
            original_tgt = splice_edge.tgt
            splice_edge.tgt = pdf_id
            self._add_flow(pdf_id, original_tgt)
        else:
            self._add_flow(pdf_id, "EndEvent_success")

    # -- enrichment: business decision points -----------------------------

    def _enrich_decision_points(self) -> None:
        for i, dp in enumerate(self.bp.business_process.decision_points):
            after_node = self._lookup_node_for_step(dp.after)
            if not after_node:
                continue
            if dp.after in self._approval_of:
                # After a review: the decision comes after the approval, on its
                # "Yes"; the "No" and any rework path stay with the approval.
                approval, yes_flows = self._approval_of[dp.after]
                xg = self._new_decision_gateway(i, dp, approval)
                outgoing = [f for f in yes_flows if f in self.flows and f.src == approval]
                for f in outgoing:
                    f.src = xg
                self._add_flow(approval, xg, name="Yes")
                after_node = approval
            else:
                xg = self._new_decision_gateway(i, dp, after_node)
                # reroute the after_node's forward (non-loop) edges through the gateway
                outgoing = [f for f in self.flows if f.src == after_node and not f.is_loop]
                for f in outgoing:
                    f.src = xg
                self._add_flow(after_node, xg)
            # Each branch's step, and the nodes a flow into it can lead to: the
            # step itself, or the join before it when it depends on several.
            targets = [
                "EndEvent_success"
                if br.target in ("end", "")
                else self._lookup_node_for_step(br.target)
                for br in dp.branches
            ]
            entries = [self._entries_of(br.target, tgt) for br, tgt in zip(dp.branches, targets)]
            outgoing = self._dissolve_fork(after_node, xg, outgoing, set().union(*entries))
            for br, tgt, entry in zip(dp.branches, targets, entries):
                if not tgt:
                    continue
                # A branch to where the step already led (the step it is after
                # depends_on: the usual way a decision is written) is that flow,
                # now from the gateway, also when it goes through the join before
                # the step: name it, rather than drawing it twice. Any other
                # branch goes to the step itself: into a join the decision does
                # not feed, it would make the join wait for a token that comes
                # only when this branch is taken.
                moved = next((f for f in outgoing if f.tgt in entry), None)
                if moved is not None:
                    outgoing.remove(moved)
                    moved.name = br.condition or moved.name
                else:
                    self._add_flow(xg, tgt, name=br.condition)

    def _new_decision_gateway(self, i: int, dp, beside: str) -> str:
        """The exclusive gateway a decision point is drawn as, in the lane of ``beside``."""
        xg = f"Gateway_decision_{_safe(dp.id)}"
        self.nodes[xg] = _Node(
            xg, "bpmn:exclusiveGateway", dp.name, self.nodes[beside].lane, "gateway"
        )
        self._map(xg, "decision_point", f"business_process.decision_points[{i}]")
        return xg

    def _entries_of(self, step_id: str, node: Optional[str]) -> set:
        """The nodes a flow into ``step_id`` (drawn as ``node``) can lead to: the
        step, and the join before it when it depends on several steps."""
        if not node:
            return set()
        join = f"Gateway_join_{_safe(step_id)}"
        return {node, join} if join in self.nodes else {node}

    def _dissolve_fork(
        self, step_node: str, gateway: str, outgoing: List[_Flow], targets: set
    ) -> List[_Flow]:
        """A decision after a step with several dependents chooses between them.

        The base edges give such a step a parallel fork, as if all its
        dependents ran. The dependents a branch of the decision leads to are
        alternatives: their flows leave from the decision gateway instead. When
        the decision chooses between all of them, the fork goes; when some are
        not chosen between, they still always run, so the fork stays after the
        step, with the decision as one of its ways. Returns the gateway's
        outgoing flows after that.
        """
        # Only the fork after the step: a join it feeds (another step waits for it
        # and others) chooses nothing, and removing it would leave the flows of
        # those others going nowhere.
        forks = [f for f in outgoing if self.mapping.get(f.tgt, {}).get("kind") == "parallel_fork"]
        for into_fork in forks:
            fork = into_fork.tgt
            out_of_fork = [f for f in self.flows if f.src == fork and not f.is_loop]
            chosen = [f for f in out_of_fork if f.tgt in targets]
            if not chosen:
                continue
            for f in chosen:
                f.src = gateway
            outgoing = [f for f in outgoing if f is not into_fork] + chosen
            if len(chosen) == len(out_of_fork):
                self.flows.remove(into_fork)
                del self.nodes[fork]
                self.mapping.pop(fork, None)
                continue
            # step -> fork -> (the steps that always run, and the decision)
            into_fork.src = step_node
            self.flows = [f for f in self.flows if not (f.src == step_node and f.tgt == gateway)]
            self._add_flow(fork, gateway)
        return outgoing

    # -- enrichment: exception flows --------------------------------------

    def _enrich_exceptions(self) -> None:
        for i, ex in enumerate(self.bp.business_process.exceptions):
            # Skip exceptions already rendered as a discard path by _enrich_approval
            if ex.id in self._consumed_exception_ids:
                continue
            attached = self._lookup_node_for_step(ex.attached_to)
            if not attached:
                continue
            xg = f"Gateway_exc_{_safe(ex.id)}"
            self.nodes[xg] = _Node(
                xg, "bpmn:exclusiveGateway", ex.name, self.nodes[attached].lane, "gateway"
            )
            self._map(xg, "exception_gateway", f"business_process.exceptions[{i}]")
            outgoing = [f for f in self.flows if f.src == attached and not f.is_loop]
            for f in outgoing:
                f.src = xg
                if not f.name:
                    f.name = "OK"
            self._add_flow(attached, xg)
            if ex.outcome.startswith("loop_to:"):
                # Stripped like the approval's loop_to (and the draft check's).
                tgt = self._lookup_node_for_step(ex.outcome.split(":", 1)[1].strip())
                if tgt:
                    self._add_flow(xg, tgt, name=ex.condition or "exception", is_loop=True)
            else:  # outcome == "end"
                rej = f"EndEvent_{_safe(ex.id)}"
                self.nodes[rej] = _Node(
                    rej, "bpmn:endEvent", ex.name or "Discarded", self.nodes[attached].lane, "event"
                )
                self._map(rej, "end_event", f"business_process.exceptions[{i}]")
                self._add_flow(xg, rej, name=ex.condition or "exception")

    def _lookup_node_for_step(self, step_id: str) -> Optional[str]:
        if not step_id:
            return None
        for s in self.bp.workflow.steps:
            if s.id == step_id:
                return self._step_node_id(s)
        for ms in self.bp.business_process.manual_steps:
            if ms.id == step_id:
                return f"Activity_{_safe(ms.id)}"
        return None

    # -- external parties (message-flow pools) ----------------------------

    def _build_external_parties(self) -> None:
        for i, ep in enumerate(self.bp.business_process.external_parties):
            pid = f"Participant_{_safe(ep.id)}"
            self.ext_pools.append((pid, ep.name))
            self._map(pid, "external_pool", f"business_process.external_parties[{i}]")
            tgt_node = self._lookup_node_for_step(ep.to_step)
            if tgt_node:
                label = ", ".join(ep.sends) if ep.sends else "hand-off"
                self.msg_flows.append((self._next_msg_id(), pid, tgt_node, label))

        # explicit message flows from business_process
        for i, mf in enumerate(self.bp.business_process.message_flows):
            src = self._resolve_msg_endpoint(mf.from_)
            tgt = self._resolve_msg_endpoint(mf.to)
            if src and tgt:
                mid = self._next_msg_id()
                self.msg_flows.append((mid, src, tgt, mf.name))
                self._map(mid, "message_flow", f"business_process.message_flows[{i}]")

    def _resolve_msg_endpoint(self, ref: str) -> Optional[str]:
        if not ref:
            return None
        # participant / external pool ids
        for pid, _ in self.ext_pools:
            if pid == f"Participant_{_safe(ref)}" or pid == ref:
                return pid
        node = self._lookup_node_for_step(ref)
        if node:
            return node
        for ds_id, _, target in self.data_stores:
            if target == ref or ds_id == ref:
                return ds_id
        return None

    # -- data objects + associations --------------------------------------

    def _build_data_objects(self) -> None:
        artifacts = self.bp.artifacts
        for art_id, art in artifacts.items():
            ref_id = f"DataObjectRef_{_safe(art_id)}"
            obj_id = f"DataObject_{_safe(art_id)}"
            label = _data_object_label(art_id, art)
            self.data_objs.append((ref_id, obj_id, label, art_id))
            self._dataobj_ref_for_artifact[art_id] = ref_id
            self._map(ref_id, "data_object", f"artifacts.{art_id}")

        # producer (data output) + consumer (data input) associations
        for s in self.bp.workflow.steps:
            node_id = self._step_node_id(s)
            node = self.nodes.get(node_id)
            if node is None:
                continue
            for out_art in s.outputs:
                ref = self._dataobj_ref_for_artifact.get(out_art)
                if ref:
                    node.data_out.append((self._next_assoc_id(), ref))
            for in_art in s.inputs:
                ref = self._dataobj_ref_for_artifact.get(in_art)
                if ref:
                    node.data_in.append((self._next_assoc_id(), ref, self._next_prop_id()))

    # -- governance annotations -------------------------------------------

    def _build_annotations(self) -> None:
        gov = self.bp.governance
        dh = gov.data_handling
        notes: List[str] = []
        if dh.contains_personal_data not in ("no", "unknown", ""):
            notes.append("Contains personal data (PII)")
        if dh.output_sensitivity not in ("low", "unknown", ""):
            notes.append(f"Output sensitivity: {dh.output_sensitivity}")
        if dh.audit_log_required:
            notes.append("Audit log required")
        # "leave blank if not mentioned" extraction policy
        tos = self.bp.target_output_spec if isinstance(self.bp.target_output_spec, dict) else {}
        if not (tos.get("required_fields") or []):
            notes.append("Leave fields blank when not stated in inputs (no assumptions)")

        for i, text in enumerate(notes):
            aid = f"TextAnnotation_{i + 1}"
            self.annotations.append((aid, text))
            self._map(aid, "annotation", "derived:governance.data_handling")

        # These governance notes apply to the whole process, not one task, so
        # they are shown as a free-floating notes column to the right of the
        # pool (no association connector -- a single connector to one task would
        # draw a long line across the whole diagram and misrepresent the scope).

    # -- lane membership --------------------------------------------------

    def _assign_lane_membership(self) -> None:
        # ensure every flow node has a lane; default to AI lane
        default_lane = self._lane_for_category("ai")
        for node in self.nodes.values():
            if not node.lane:
                node.lane = default_lane
            self.lanes[node.lane].members.append(node.id)

    # -- layout -----------------------------------------------------------

    def _compute_ranks(self) -> None:
        # longest-path ranks over the non-loop DAG
        nodes = list(self.nodes.keys())
        succ: Dict[str, List[str]] = {n: [] for n in nodes}
        indeg: Dict[str, int] = {n: 0 for n in nodes}
        for f in self.flows:
            if f.is_loop:
                continue
            if f.src in succ and f.tgt in indeg:
                succ[f.src].append(f.tgt)
                indeg[f.tgt] += 1
        # Kahn with longest-path relaxation
        from collections import deque

        rank = {n: 0 for n in nodes}
        q = deque([n for n in nodes if indeg[n] == 0])
        local_indeg = dict(indeg)
        while q:
            n = q.popleft()
            for m in succ[n]:
                if rank[n] + 1 > rank[m]:
                    rank[m] = rank[n] + 1
                local_indeg[m] -= 1
                if local_indeg[m] == 0:
                    q.append(m)
        for n in nodes:
            self.nodes[n].rank = rank[n]

    def _layout(self) -> Tuple[float, float]:
        self._compute_ranks()

        # group nodes per lane per rank to compute stacking
        lane_rank_count: Dict[Tuple[str, int], int] = {}
        max_stack_per_lane: Dict[str, int] = {l: 1 for l in self.lanes}
        for node in self.nodes.values():
            key = (node.lane, node.rank)
            lane_rank_count[key] = lane_rank_count.get(key, 0) + 1
            max_stack_per_lane[node.lane] = max(
                max_stack_per_lane.get(node.lane, 1), lane_rank_count[key]
            )

        # lane heights & tops (ordered by priority then creation). Every row is
        # tall enough to hold a data-object zone above its task zone.
        ordered_lanes = sorted(self.lanes.values(), key=lambda l: (l.priority, l.id))
        top = float(POOL_Y)
        for lane in ordered_lanes:
            rows = max_stack_per_lane.get(lane.id, 1)
            lane.height = max(self.base_lane_h, LANE_PAD_TOP + rows * self.row_h + LANE_PAD_BOTTOM)
            lane.top = top
            top += lane.height
        pool_height = top - POOL_Y

        # assign x,y for flow nodes. stack index resets per (lane, rank); the
        # task sits in the lower (task) zone of its row.
        slot_index: Dict[Tuple[str, int], int] = {}
        max_rank = max((n.rank for n in self.nodes.values()), default=0)
        for node in sorted(self.nodes.values(), key=lambda n: (n.rank, n.lane)):
            key = (node.lane, node.rank)
            idx = slot_index.get(key, 0)
            slot_index[key] = idx + 1
            self.node_row[node.id] = idx
            lane = self.lanes[node.lane]
            col_cx = CONTENT_X0 + node.rank * X_SPACING + COL_W / 2
            row_top = lane.top + LANE_PAD_TOP + idx * self.row_h
            task_cy = row_top + self.row_data_h + TASK_LABEL_H + ROW_TASK_H / 2
            node.x = col_cx - node.w / 2
            node.y = task_cy - node.h / 2
            self.bounds[node.id] = (node.x, node.y, node.w, node.h)

        pool_width = (CONTENT_X0 - POOL_X) + (max_rank + 1) * X_SPACING + 60
        self._place_data_elements(pool_width, pool_height)
        return pool_width, pool_height

    def _place_data_elements(self, pool_width: float, pool_height: float) -> None:
        """Position data objects (in the data-zone of their producer task's own
        row, spread when a task has several), data stores (below their send
        task), and annotations (a notes column right of the pool). All stored
        in self.bounds."""
        w_obj, h_obj = SIZE["dataObject"]

        # group data objects by their anchoring (producer) flow node
        groups: Dict[str, List[str]] = {}
        for ref_id, obj_id, name, art_id in self.data_objs:
            anchor = self._artifact_anchor_node(art_id)
            groups.setdefault(anchor or "", []).append(ref_id)

        for anchor, refs in groups.items():
            if anchor and anchor in self.bounds and anchor in self.node_row:
                ax, ay, aw, ah = self.bounds[anchor]
                lane = self.lanes[self.nodes[anchor].lane]
                idx = self.node_row[anchor]
                row_top = lane.top + LANE_PAD_TOP + idx * self.row_h
                # sit near the top of the data zone so there is a clear gap down
                # to the task below it
                oy = row_top + DATA_OBJ_TOP_PAD
                n = len(refs)
                total_w = n * w_obj + (n - 1) * DATA_OBJ_GAP
                start_cx = (ax + aw / 2) - total_w / 2 + w_obj / 2
                for i, ref_id in enumerate(refs):
                    cx = start_cx + i * (w_obj + DATA_OBJ_GAP)
                    self.bounds[ref_id] = (cx - w_obj / 2, oy, w_obj, h_obj)
            else:
                # no anchor: drop into the top-left content area
                for i, ref_id in enumerate(refs):
                    self.bounds[ref_id] = (
                        CONTENT_X0 + i * (w_obj + DATA_OBJ_GAP),
                        POOL_Y + 10,
                        w_obj,
                        h_obj,
                    )

        # data stores: directly below their send task, beneath the pool
        w_ds, h_ds = SIZE["dataStore"]
        pool_bottom = POOL_Y + pool_height
        for ds_id, ds_name, target in self.data_stores:
            send_id = f"Activity_submit_{_safe(target)}"
            if send_id in self.bounds:
                sx, sy, sw, sh = self.bounds[send_id]
                cx = sx + sw / 2
            else:
                cx = CONTENT_X0 + w_ds
            self.bounds[ds_id] = (cx - w_ds / 2, pool_bottom + 30, w_ds, h_ds)

        # annotations: a notes column just to the right of the pool
        w_an, h_an = SIZE["annotation"]
        an_x = POOL_X + pool_width + 40
        an_y = POOL_Y + 20
        for aid, text in self.annotations:
            self.bounds[aid] = (an_x, an_y, w_an, h_an)
            an_y += h_an + 18

    def _artifact_anchor_node(self, art_id: str) -> Optional[str]:
        """The flow node a data object hangs from: its producer, else its first
        consumer."""
        producer = None
        consumer = None
        for s in self.bp.workflow.steps:
            if art_id in s.outputs and producer is None:
                producer = self._step_node_id(s)
            if art_id in s.inputs and consumer is None:
                consumer = self._step_node_id(s)
        return producer or consumer

    # -- build orchestration ---------------------------------------------

    def build(self) -> str:
        self._build_step_nodes()
        self._build_manual_steps()
        self._build_participant_lanes()
        self._build_base_edges()
        self._enrich_approval()
        self._enrich_decision_points()
        self._enrich_exceptions()
        self._settle_joins()
        # PDF generation is placed on the approved path *before* integration so
        # the order reads "generate the report -> submit it", and so a human
        # review approves the output before the PDF is rendered.
        self._enrich_pdf_generation()
        self._enrich_integration()
        if self.include_data_objects:
            self._build_data_objects()
        self._build_external_parties()
        self._build_annotations()
        self._assign_lane_membership()
        pool_w, pool_h = self._layout()

        # resolve incoming/outgoing on nodes
        for f in self.flows:
            if f.src in self.nodes:
                self.nodes[f.src].outgoing.append(f.id)
            if f.tgt in self.nodes:
                self.nodes[f.tgt].incoming.append(f.id)

        return self._emit(pool_w, pool_h)

    # -- emit XML ---------------------------------------------------------

    def _emit(self, pool_w: float, pool_h: float) -> str:
        L: List[str] = []
        L.append('<?xml version="1.0" encoding="UTF-8"?>')
        L.append(
            "<bpmn:definitions "
            'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
            'xmlns:omgdc="http://www.omg.org/spec/DD/20100524/DC" '
            'xmlns:omgdi="http://www.omg.org/spec/DD/20100524/DI" '
            'id="Definitions_1" targetNamespace="http://gaik.solutionwizard/bpmn">'
        )

        # ---- collaboration ----
        L.append('  <bpmn:collaboration id="Collaboration_1">')
        proc_name = _esc(self.bp.use_case.name)
        L.append(
            f'    <bpmn:participant id="Participant_main" name="{proc_name}" processRef="Process_1" />'
        )
        for pid, name in self.ext_pools:
            L.append(f'    <bpmn:participant id="{pid}" name="{_esc(name)}" />')
        for mid, src, tgt, name in self.msg_flows:
            nm = f' name="{_esc(name)}"' if name else ""
            L.append(f'    <bpmn:messageFlow id="{mid}"{nm} sourceRef="{src}" targetRef="{tgt}" />')
        L.append("  </bpmn:collaboration>")

        # ---- process ----
        L.append('  <bpmn:process id="Process_1" isExecutable="false">')

        # laneSet
        ordered_lanes = sorted(self.lanes.values(), key=lambda l: (l.priority, l.id))
        L.append('    <bpmn:laneSet id="LaneSet_1">')
        for lane in ordered_lanes:
            L.append(f'      <bpmn:lane id="{lane.id}" name="{_esc(lane.name)}">')
            for ref in lane.members:
                L.append(f"        <bpmn:flowNodeRef>{ref}</bpmn:flowNodeRef>")
            L.append("      </bpmn:lane>")
        L.append("    </bpmn:laneSet>")

        # flow nodes
        for node in self.nodes.values():
            self._emit_node(L, node)

        # data objects
        for ref_id, obj_id, name, art_id in self.data_objs:
            L.append(
                f'    <bpmn:dataObjectReference id="{ref_id}" name="{_esc(name)}" dataObjectRef="{obj_id}" />'
            )
            L.append(f'    <bpmn:dataObject id="{obj_id}" />')

        # data stores
        for ds_id, ds_name, target in self.data_stores:
            L.append(f'    <bpmn:dataStoreReference id="{ds_id}" name="{_esc(ds_name)}" />')

        # text annotations + associations
        for aid, text in self.annotations:
            L.append(
                f'    <bpmn:textAnnotation id="{aid}"><bpmn:text>{_esc(text)}</bpmn:text></bpmn:textAnnotation>'
            )
        for assoc_id, src, tgt in self.assocs:
            L.append(
                f'    <bpmn:association id="{assoc_id}" sourceRef="{tgt}" targetRef="{src}" associationDirection="None" />'
            )

        # sequence flows
        for f in self.flows:
            nm = f' name="{_esc(f.name)}"' if f.name else ""
            L.append(
                f'    <bpmn:sequenceFlow id="{f.id}"{nm} sourceRef="{f.src}" targetRef="{f.tgt}" />'
            )

        L.append("  </bpmn:process>")

        # ---- diagram ----
        self._emit_di(L, pool_w, pool_h)

        L.append("</bpmn:definitions>")
        return "\n".join(L) + "\n"

    def _emit_node(self, L: List[str], node: _Node) -> None:
        inner: List[str] = []
        if node.documentation:
            # BPMN puts documentation first among an element's children.
            inner.append(
                f"      <bpmn:documentation>{_esc(node.documentation)}</bpmn:documentation>"
            )
        for fid in node.incoming:
            inner.append(f"      <bpmn:incoming>{fid}</bpmn:incoming>")
        for fid in node.outgoing:
            inner.append(f"      <bpmn:outgoing>{fid}</bpmn:outgoing>")
        # data associations (tasks only)
        for assoc_id, ref_id, prop_id in node.data_in:
            inner.append(f'      <bpmn:property id="{prop_id}" name="__targetRef_placeholder" />')
            inner.append(f'      <bpmn:dataInputAssociation id="{assoc_id}">')
            inner.append(f"        <bpmn:sourceRef>{ref_id}</bpmn:sourceRef>")
            inner.append(f"        <bpmn:targetRef>{prop_id}</bpmn:targetRef>")
            inner.append("      </bpmn:dataInputAssociation>")
        for assoc_id, ref_id in node.data_out:
            inner.append(f'      <bpmn:dataOutputAssociation id="{assoc_id}">')
            inner.append(f"        <bpmn:targetRef>{ref_id}</bpmn:targetRef>")
            inner.append("      </bpmn:dataOutputAssociation>")

        name_attr = f' name="{_esc(node.name)}"' if node.name else ""
        if inner:
            L.append(f'    <{node.tag} id="{node.id}"{name_attr}>')
            L.extend(inner)
            L.append(f"    </{node.tag}>")
        else:
            L.append(f'    <{node.tag} id="{node.id}"{name_attr} />')

    def _emit_di(self, L: List[str], pool_w: float, pool_h: float) -> None:
        L.append('  <bpmndi:BPMNDiagram id="BPMNDiagram_1">')
        L.append('    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Collaboration_1">')

        # main pool
        L.append(
            '      <bpmndi:BPMNShape id="Participant_main_di" bpmnElement="Participant_main" isHorizontal="true">'
        )
        L.append(
            f'        <omgdc:Bounds x="{POOL_X}" y="{POOL_Y}" width="{int(pool_w)}" height="{int(pool_h)}" />'
        )
        L.append("      </bpmndi:BPMNShape>")

        # lanes
        ordered_lanes = sorted(self.lanes.values(), key=lambda l: (l.priority, l.id))
        lane_x = POOL_X + POOL_LABEL_W
        lane_w = pool_w - POOL_LABEL_W
        for lane in ordered_lanes:
            L.append(
                f'      <bpmndi:BPMNShape id="{lane.id}_di" bpmnElement="{lane.id}" isHorizontal="true">'
            )
            L.append(
                f'        <omgdc:Bounds x="{int(lane_x)}" y="{int(lane.top)}" width="{int(lane_w)}" height="{int(lane.height)}" />'
            )
            L.append("      </bpmndi:BPMNShape>")

        # external pools (stacked above the main pool)
        ext_y = POOL_Y - EXT_POOL_GAP - EXT_POOL_H
        for pid, name in self.ext_pools:
            self.bounds[pid] = (float(POOL_X), float(ext_y), float(pool_w), float(EXT_POOL_H))
            L.append(
                f'      <bpmndi:BPMNShape id="{pid}_di" bpmnElement="{pid}" isHorizontal="true">'
            )
            L.append(
                f'        <omgdc:Bounds x="{POOL_X}" y="{int(ext_y)}" width="{int(pool_w)}" height="{EXT_POOL_H}" />'
            )
            L.append("      </bpmndi:BPMNShape>")
            ext_y -= EXT_POOL_H + EXT_POOL_GAP

        # flow node shapes
        for node in self.nodes.values():
            is_marker = node.tag in (
                "bpmn:startEvent",
                "bpmn:endEvent",
                "bpmn:exclusiveGateway",
                "bpmn:parallelGateway",
            )
            extra = ' isMarkerVisible="true"' if node.tag == "bpmn:exclusiveGateway" else ""
            L.append(f'      <bpmndi:BPMNShape id="{node.id}_di" bpmnElement="{node.id}"{extra}>')
            L.append(
                f'        <omgdc:Bounds x="{int(node.x)}" y="{int(node.y)}" width="{node.w}" height="{node.h}" />'
            )
            if node.name and is_marker:
                # label below small shapes
                L.append("        <bpmndi:BPMNLabel>")
                L.append(
                    f'          <omgdc:Bounds x="{int(node.x - 10)}" y="{int(node.y + node.h + 4)}" width="{node.w + 20}" height="20" />'
                )
                L.append("        </bpmndi:BPMNLabel>")
            L.append("      </bpmndi:BPMNShape>")

        # data object shapes (positions precomputed into self.bounds)
        for ref_id, obj_id, name, art_id in self.data_objs:
            x, y, w, h = self.bounds[ref_id]
            L.append(f'      <bpmndi:BPMNShape id="{ref_id}_di" bpmnElement="{ref_id}">')
            L.append(
                f'        <omgdc:Bounds x="{int(x)}" y="{int(y)}" width="{int(w)}" height="{int(h)}" />'
            )
            L.append("      </bpmndi:BPMNShape>")

        # data store shapes (below their send task)
        for ds_id, ds_name, target in self.data_stores:
            x, y, w, h = self.bounds[ds_id]
            L.append(f'      <bpmndi:BPMNShape id="{ds_id}_di" bpmnElement="{ds_id}">')
            L.append(
                f'        <omgdc:Bounds x="{int(x)}" y="{int(y)}" width="{int(w)}" height="{int(h)}" />'
            )
            L.append("      </bpmndi:BPMNShape>")

        # annotation shapes (notes column right of the pool)
        for aid, text in self.annotations:
            x, y, w, h = self.bounds[aid]
            L.append(f'      <bpmndi:BPMNShape id="{aid}_di" bpmnElement="{aid}">')
            L.append(
                f'        <omgdc:Bounds x="{int(x)}" y="{int(y)}" width="{int(w)}" height="{int(h)}" />'
            )
            L.append("      </bpmndi:BPMNShape>")

        # sequence flow edges
        for f in self.flows:
            self._emit_edge(L, f)

        # data association edges (border-to-border, real positions)
        for node in self.nodes.values():
            for assoc_id, ref_id, prop_id in node.data_in:
                self._emit_data_edge(L, assoc_id, ref_id, node.id)
            for assoc_id, ref_id in node.data_out:
                # for the integration send task, the out ref is a data store
                self._emit_data_edge(L, assoc_id, node.id, ref_id)

        # message flow edges
        for mid, src, tgt, name in self.msg_flows:
            self._emit_msg_edge(L, mid, src, tgt)

        L.append("    </bpmndi:BPMNPlane>")
        L.append("  </bpmndi:BPMNDiagram>")

    def _element_center(self, element_id: str) -> Tuple[float, float]:
        b = self.bounds.get(element_id)
        if b is not None:
            x, y, w, h = b
            return x + w / 2, y + h / 2
        # last-resort (should not happen now that every element is in bounds)
        return CONTENT_X0, POOL_Y

    def _element_rect(self, element_id: str) -> tuple[float, float, float, float]:
        b = self.bounds.get(element_id)
        if b is not None:
            return b
        cx, cy = self._element_center(element_id)
        return cx, cy, 0.0, 0.0

    @staticmethod
    def _emit_waypoints(lines: list[str], points: list[tuple[int, int]]) -> None:
        for x, y in points:
            lines.append(f'        <omgdi:waypoint x="{x}" y="{y}" />')

    def _emit_edge(self, L: List[str], f: _Flow) -> None:
        src = self.nodes.get(f.src)
        tgt = self.nodes.get(f.tgt)
        L.append(f'      <bpmndi:BPMNEdge id="{f.id}_di" bpmnElement="{f.id}">')
        if src is None or tgt is None:
            L.append(f'        <omgdi:waypoint x="{CONTENT_X0}" y="{POOL_Y}" />')
            L.append(f'        <omgdi:waypoint x="{CONTENT_X0 + 40}" y="{POOL_Y}" />')
            L.append("      </bpmndi:BPMNEdge>")
            return
        if f.is_loop:
            # route below the lanes: src bottom -> down -> left -> up to tgt bottom
            sx, sy = src.cx, src.y + src.h
            tx, ty = tgt.cx, tgt.y + tgt.h
            low = max(src.y + src.h, tgt.y + tgt.h) + 50
            L.append(f'        <omgdi:waypoint x="{int(sx)}" y="{int(sy)}" />')
            L.append(f'        <omgdi:waypoint x="{int(sx)}" y="{int(low)}" />')
            L.append(f'        <omgdi:waypoint x="{int(tx)}" y="{int(low)}" />')
            L.append(f'        <omgdi:waypoint x="{int(tx)}" y="{int(ty)}" />')
        else:
            points = route_edge((src.x, src.y, src.w, src.h), (tgt.x, tgt.y, tgt.w, tgt.h))
            self._emit_waypoints(L, points)
        L.append("      </bpmndi:BPMNEdge>")

    def _emit_data_edge(self, L: List[str], edge_id: str, a_id: str, b_id: str) -> None:
        """A dashed data-association edge from a_id to b_id, attached to each
        shape's border (never the centre) and drawn with right angles."""
        points = route_edge(self._element_rect(a_id), self._element_rect(b_id))
        L.append(f'      <bpmndi:BPMNEdge id="{edge_id}_di" bpmnElement="{edge_id}">')
        self._emit_waypoints(L, points)
        L.append("      </bpmndi:BPMNEdge>")

    def _emit_msg_edge(self, L: List[str], mid: str, src: str, tgt: str) -> None:
        # attach at borders so the dashed message flow meets the pool / task cleanly
        points = route_edge(self._element_rect(src), self._element_rect(tgt))
        L.append(f'      <bpmndi:BPMNEdge id="{mid}_di" bpmnElement="{mid}">')
        self._emit_waypoints(L, points)
        L.append("      </bpmndi:BPMNEdge>")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def route_edge(
    src: tuple[int, int, int, int], tgt: tuple[int, int, int, int]
) -> list[tuple[int, int]]:
    """Right-angle waypoints for a connection from shape `src` to shape `tgt`.

    Both shapes are ``(x, y, width, height)``. Consecutive waypoints share x or
    y; the first lies on the source's border and the last on the target's.

    - target to the right: exit right, enter left, with a middle vertical
      segment when the centres' ys differ;
    - shapes stacked (their x ranges overlap): one vertical segment;
    - target to the left: loop back below both shapes, as the rework loop does.
    """
    sx, sy, sw, sh = src
    tx, ty, tw, th = tgt
    s_cy, t_cy = sy + sh / 2, ty + th / 2
    if tx >= sx + sw:
        x0, x1 = int(sx + sw), int(tx)
        y0, y1 = int(s_cy), int(t_cy)
        if abs(s_cy - t_cy) < 1:
            return [(x0, y0), (x1, y0)]
        midx = int((sx + sw + tx) / 2)
        return [(x0, y0), (midx, y0), (midx, y1), (x1, y1)]
    left, right = max(sx, tx), min(sx + sw, tx + tw)
    if left <= right:
        x = int((left + right) / 2)
        if t_cy >= s_cy:
            return [(x, int(sy + sh)), (x, int(ty))]
        return [(x, int(sy)), (x, int(ty + th))]
    low = int(max(sy + sh, ty + th) + 50)
    xs, xt = int(sx + sw / 2), int(tx + tw / 2)
    return [(xs, int(sy + sh)), (xs, low), (xt, low), (xt, int(ty + th))]


def generate_bpmn(
    blueprint: Blueprint,
    *,
    include_data_objects: bool = True,
    extra_lane_ids: frozenset[str] = frozenset(),
) -> str:
    """Generate BPMN 2.0 XML from a blueprint.

    With ``include_data_objects=False`` the artifacts are left out (no data
    objects, no data associations to them) and the rows lose their data band,
    so the diagram is more compact. Data stores stay.

    ``extra_lane_ids`` names participants drawn as lanes even when no node is
    in them (lanes a user added in an editor). They come after every other
    lane, in their order in ``participants``, so adding one moves no other
    lane. Without it, a participant no node reaches is not drawn.

    Side effect: writes the element->blueprint id map to
    ``blueprint.visualizations["bpmn_mapping"]`` so the linkage is recorded in
    the JSON (the diagram stays derived, never the source of truth).
    """
    if not blueprint.workflow.steps:
        # minimal valid empty diagram
        return _empty_bpmn()
    builder = _BpmnBuilder(
        blueprint, include_data_objects=include_data_objects, extra_lane_ids=extra_lane_ids
    )
    xml = builder.build()
    if not isinstance(blueprint.visualizations, dict):
        blueprint.visualizations = {}
    blueprint.visualizations["bpmn_mapping"] = builder.mapping
    return xml


def write_bpmn(blueprint: Blueprint, output_dir: str | Path) -> Path:
    """Generate BPMN and write workflow.bpmn to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bpmn_path = output_dir / "workflow.bpmn"
    bpmn_path.write_text(generate_bpmn(blueprint), encoding="utf-8")
    return bpmn_path


def _empty_bpmn() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<bpmn:definitions "
        'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:omgdc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:omgdi="http://www.omg.org/spec/DD/20100524/DI" '
        'id="Definitions_1" targetNamespace="http://gaik.solutionwizard/bpmn">\n'
        '  <bpmn:process id="Process_1" isExecutable="false">\n'
        '    <bpmn:startEvent id="StartEvent_1" name="No workflow steps defined" />\n'
        "  </bpmn:process>\n"
        '  <bpmndi:BPMNDiagram id="BPMNDiagram_1">\n'
        '    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">\n'
        '      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">\n'
        '        <omgdc:Bounds x="160" y="100" width="36" height="36" />\n'
        "      </bpmndi:BPMNShape>\n"
        "    </bpmndi:BPMNPlane>\n"
        "  </bpmndi:BPMNDiagram>\n"
        "</bpmn:definitions>\n"
    )
