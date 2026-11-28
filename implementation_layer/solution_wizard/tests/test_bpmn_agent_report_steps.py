"""The agent's own report and submission steps are drawn once, with no generated duplicate.

With "pdf" in ``technical_spec.output_types`` the generator adds a "Generate PDF
report" task, and for each ``technical_spec.integration_targets`` entry a
"Submit to …" send task. When the agent writes its own steps for that work (a
live run: ``invoice_pdf_report`` and ``erp_submission``, both
``component: custom``), the diagram showed the report and the submission twice.

- The report: a step that outputs a *generated* artifact of type pdf or report,
  with ``final_output: true``, ``produced_by`` it. (An upload step's PDF is
  ``source: user_upload``; an intermediate PDF is not the final output.)
- The submission: a step whose ``parameters.integration_target`` is the
  target's exact name. Its data store stays, written by that step.
- A decision's branch to "end" still passes the report and the submission once.

The checks walk the drawn diagram as a case would run it (`_runs`): every
choice at an exclusive gateway, every way out of a fork, a join waiting for
all its ways. So a step entered twice, or a token left waiting, shows.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import generate_bpmn

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
END = "EndEvent_success"
ERP = "ERP system (approved invoice data)"
PDF = "Activity_generate_pdf"


def _step(sid, kind="automated_task", deps=(), inputs=(), outputs=(), **extra):
    step = {
        "id": sid,
        "name": sid.replace("_", " ").capitalize(),
        "type": kind,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "depends_on": list(deps),
        **extra,
    }
    if kind == "automated_task":
        step.setdefault("component", "custom")
    return step


def _send(sid, deps, target=ERP):
    return _step(
        sid,
        deps=deps,
        inputs=["record"],
        outputs=[f"{sid}_receipt"],
        parameters={"integration_target": target} if target else {},
    )


def _art(kind, by=None, *, upload=False, final=False):
    if upload:
        return {"type": kind, "source": "user_upload", "optional": False}
    return {
        "type": kind,
        "source": "generated",
        "optional": False,
        "produced_by": by,
        "final_output": final,
    }


def _blueprint(steps, artifacts, **kw):
    return Blueprint.model_validate(_blueprint_dict(steps, artifacts, **kw))


def _blueprint_dict(
    steps, artifacts, *, targets=(ERP,), outputs=("structured_json", "pdf"), decisions=()
):
    artifacts = dict(artifacts)
    for s in steps:
        for out in s["outputs"]:
            artifacts.setdefault(out, _art("structured_json", s["id"]))
    return {
        "blueprint_version": "1.0",
        "use_case": {"id": "uc", "name": "Invoices", "description": "x", "domain": "t"},
        "business_spec": {"intended_users": ["clerk"], "reviewers": ["manager"]},
        "technical_spec": {
            "input_types": ["pdf"],
            "output_types": list(outputs),
            "language": "en",
            "integration_targets": list(targets),
        },
        "target_output_spec": {"required_fields": ["a"]},
        "components": {
            "selected_modules": [],
            "selected_building_blocks": [],
            "custom_components": [],
        },
        "artifacts": artifacts,
        "workflow": {"steps": steps},
        "business_process": {"decision_points": list(decisions)},
    }


def _decision(did, after, *branches):
    return {
        "id": did,
        "name": did,
        "after": after,
        "branches": [{"condition": c, "target": t} for c, t in branches],
    }


def _flows(bp):
    root = ET.fromstring(generate_bpmn(bp))
    proc = root.find("bpmn:process", NS)
    flows = [
        (f.get("sourceRef"), f.get("targetRef")) for f in proc.findall("bpmn:sequenceFlow", NS)
    ]
    kinds = {e.get("id"): e.tag.split("}")[-1] for e in proc}
    writes = {
        e.get("id"): [
            a.findtext("bpmn:targetRef", namespaces=NS)
            for a in e.findall("bpmn:dataOutputAssociation", NS)
        ]
        for e in proc
    }
    return flows, kinds, writes


def _back_edges(flows):
    """The flows that return to a node on the way to them from the start: the
    rework ways (a loop, or a decision branch back to an earlier step)."""
    out = {}
    for a, b in flows:
        out.setdefault(a, []).append(b)
    back, state = set(), {"StartEvent_1": 1}
    stack = [("StartEvent_1", iter(out.get("StartEvent_1", [])))]
    while stack:
        node, it = stack[-1]
        nxt = next(it, None)
        if nxt is None:
            state[node] = 2
            stack.pop()
        elif state.get(nxt) == 1:
            back.add((node, nxt))
        elif nxt not in state:
            state[nxt] = 1
            stack.append((nxt, iter(out.get(nxt, []))))
    return back


def _runs(bp):
    """Every way a case can run through the drawn diagram.

    A token at an exclusive gateway with several ways takes each in turn (a way
    back, `_back_edges`, is rework and is not taken); a task or a fork sends a
    token down every way out; a parallel join fires when a token has come in on
    each of its forward ways. A node two tokens reach is passed twice. Returns
    ``(nodes in the order passed, nodes a token was left waiting at)`` per run.
    """
    flows, kinds, _ = _flows(bp)
    back = _back_edges(flows)
    out, indeg = {}, {}
    for a, b in flows:
        if (a, b) in back:
            continue
        out.setdefault(a, []).append(b)
        indeg[b] = indeg.get(b, 0) + 1
    runs = []

    def go(pending, order, waiting):
        while pending:
            n = pending.pop(0)
            kind = kinds[n]
            if kind == "exclusiveGateway" and len(out.get(n, [])) > 1:
                for t in out[n]:
                    go([t] + pending, order + [n], dict(waiting))
                return
            if kind == "parallelGateway" and indeg.get(n, 0) > 1:
                waiting[n] = waiting.get(n, 0) + 1
                if waiting[n] < indeg[n]:
                    continue
                waiting[n] = 0
            order = order + [n]
            if kind != "endEvent":
                pending = pending + out.get(n, [])
        runs.append((order, {n for n, c in waiting.items() if c}))

    go(["StartEvent_1"], [], {})
    return runs


def _assert_each_finished_run_passes_once(bp, reports, sends):
    """Every run that reaches the success end passes the report (an own report
    step or a generated one) and the submission (an own send step or a
    generated one) exactly once, and no run leaves a token waiting."""
    runs = _runs(bp)
    finished = [order for order, _ in runs if END in order]
    assert finished, runs
    for order, waiting in runs:
        assert not waiting, (order, waiting)
    for order in finished:
        n_reports = sum(1 for n in order if n in reports or n.startswith(PDF))
        n_sends = sum(1 for n in order if n in sends or n.startswith("Activity_submit_"))
        assert n_reports == 1, order
        assert n_sends == 1, order
    return finished


UPLOAD = _step("upload", "user_task", outputs=["invoice_pdf"])
EXTRACT = _step("extract", deps=["upload"], inputs=["invoice_pdf"], outputs=["record"])
BASE_ARTS = {"invoice_pdf": _art("pdf", upload=True), "record": _art("structured_json", "extract")}


def _report(sid, deps):
    return _step(sid, deps=deps, inputs=["record"], outputs=[f"{sid}_pdf"])


def _report_art(sid, final=True):
    return {f"{sid}_pdf": _art("pdf", sid, final=final)}


# -- the boxes ------------------------------------------------------------------


def test_the_agents_own_report_and_submission_are_drawn_once():
    steps = [
        UPLOAD,
        EXTRACT,
        _report("make_document", ["extract"]),
        _send("deliver", ["make_document"]),
    ]
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_document")})
    flows, kinds, writes = _flows(bp)

    assert PDF not in kinds
    assert not any(k.startswith("Activity_submit_") for k in kinds)
    assert ("Activity_make_document", "Activity_deliver") in flows
    assert ("Activity_deliver", END) in flows
    # The integration's data store stays, written by the agent's own step.
    store = next(k for k, v in kinds.items() if v == "dataStoreReference")
    assert store in writes["Activity_deliver"]
    _assert_each_finished_run_passes_once(bp, {"Activity_make_document"}, {"Activity_deliver"})


def test_without_own_steps_both_boxes_are_generated_report_first():
    flows, kinds, _ = _flows(_blueprint([UPLOAD, EXTRACT], dict(BASE_ARTS)))

    assert ("Activity_extract", PDF) in flows
    send = next(k for k in kinds if k.startswith("Activity_submit_"))
    assert (PDF, send) in flows
    assert (send, END) in flows


def test_an_own_report_step_without_a_submission_gets_the_generated_send_after_it():
    steps = [UPLOAD, EXTRACT, _report("make_document", ["extract"])]
    flows, kinds, _ = _flows(_blueprint(steps, {**BASE_ARTS, **_report_art("make_document")}))

    assert PDF not in kinds
    send = next(k for k in kinds if k.startswith("Activity_submit_"))
    assert ("Activity_make_document", send) in flows


def test_a_marker_for_one_of_two_targets_keeps_the_other_targets_box():
    steps = [UPLOAD, EXTRACT, _send("deliver", ["extract"])]
    flows, kinds, _ = _flows(
        _blueprint(steps, BASE_ARTS, targets=(ERP, "archive_system"), outputs=("structured_json",))
    )

    sends = [k for k in kinds if k.startswith("Activity_submit_")]
    assert sends == ["Activity_submit_archive_system"]


def test_a_marker_naming_no_target_is_not_taken_for_the_submission():
    bp = _blueprint([UPLOAD, EXTRACT, _send("send_erp", ["extract"], target="erp")], BASE_ARTS)
    _, kinds, _ = _flows(bp)

    assert any(k.startswith("Activity_submit_") for k in kinds)


def test_an_upload_steps_pdf_is_not_taken_for_the_report():
    _, kinds, _ = _flows(_blueprint([UPLOAD, EXTRACT], dict(BASE_ARTS), targets=()))

    assert PDF in kinds


def test_an_intermediate_pdf_is_not_taken_for_the_final_report():
    """A normalised PDF that the review then reads is not the report: the
    generated report is still drawn after approval."""
    steps = [
        UPLOAD,
        _step("normalise", deps=["upload"], inputs=["invoice_pdf"], outputs=["clean_pdf"]),
        _step("extract", deps=["normalise"], inputs=["clean_pdf"], outputs=["record"]),
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
    ]
    arts = {**BASE_ARTS, "clean_pdf": _art("pdf", "normalise", final=False)}
    bp = _blueprint(steps, arts, targets=())
    flows, kinds, _ = _flows(bp)

    assert PDF in kinds
    runs = _runs(bp)
    assert all(not w for _, w in runs)
    finished = [o for o, _ in runs if END in o]
    assert finished
    for order in finished:
        assert order.index("Activity_review") < order.index(PDF)


def _assert_safe(bp):
    """Whatever the shape: no element id is used twice, some run finishes, and
    no run leaves a token waiting. Returns the finished runs."""
    root = ET.fromstring(generate_bpmn(bp))
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    runs = _runs(bp)
    finished = [o for o, _ in runs if END in o]
    assert finished, runs
    for order, waiting in runs:
        assert not waiting, (order, waiting)
    return finished


# -- a way that skips the agent's steps keeps the generated boxes ---------------


def test_a_branch_to_end_past_the_own_steps_keeps_the_generated_boxes():
    """The auto-approval shape written with "end": the small invoice skips the
    agent's report and send steps, so the diagram keeps develop's generated
    report and submission at the end. The reviewed path shows two of each;
    nothing is rewired."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _report("make_doc", ["review"]),
        _send("deliver", ["make_doc"]),
    ]
    decision = _decision("auto", "extract", ("small", "end"), ("big", "review"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])
    flows, kinds, _ = _flows(bp)

    assert PDF in kinds
    send = "Activity_submit_ERP_system__approved_invoice_data_"
    assert send in kinds
    assert (PDF, send) in flows
    assert ("Gateway_decision_auto", "Activity_make_doc") not in flows
    for order in _assert_safe(bp):
        assert order.index(PDF) < order.index(send)


def test_a_branch_pointed_at_the_own_report_step_draws_each_once():
    """The same process with the branch pointed at the agent's report step, as
    the agent is asked to write it: every way passes the agent's steps, so
    nothing is generated."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _report("make_doc", ["review"]),
        _send("deliver", ["make_doc"]),
    ]
    decision = _decision("auto", "extract", ("small", "make_doc"), ("big", "review"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])
    _, kinds, _ = _flows(bp)

    assert PDF not in kinds
    assert not any(k.startswith("Activity_submit_") for k in kinds)
    finished = _assert_each_finished_run_passes_once(
        bp, {"Activity_make_doc"}, {"Activity_deliver"}
    )
    assert any("Activity_review" not in o for o in finished)


def test_an_own_report_on_one_branch_only_keeps_the_generated_report():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("route", deps=["extract"]),
        _step("manager", "user_task", deps=["route"]),
        _report("make_document", ["manager"]),
        _step("archive", deps=["route"]),
    ]
    decision = _decision("big", "route", ("yes", "manager"), ("no", "archive"))
    bp = _blueprint(
        steps, {**BASE_ARTS, **_report_art("make_document")}, targets=(), decisions=[decision]
    )
    _, kinds, _ = _flows(bp)

    assert PDF in kinds
    for order in _assert_safe(bp):
        assert PDF in order


def test_a_marked_sender_with_a_generated_report_keeps_the_submit_task_after_it():
    """The report is generated at the end, so the agent's own send step comes
    before it: the generated submission stays, after the report, as in develop."""
    bp = _blueprint([UPLOAD, EXTRACT, _send("send_erp", ["extract"])], BASE_ARTS)
    flows, kinds, _ = _flows(bp)

    send = "Activity_submit_ERP_system__approved_invoice_data_"
    assert send in kinds
    assert (PDF, send) in flows
    assert (send, END) in flows
    for order in _assert_safe(bp):
        assert order.index(PDF) < order.index(send)


def test_two_marked_senders_on_two_branches_keep_the_submit_task():
    steps = [UPLOAD, EXTRACT, _send("send_small", ["extract"]), _send("send_large", ["extract"])]
    decision = _decision("size", "extract", ("small", "send_small"), ("large", "send_large"))
    bp = _blueprint(steps, BASE_ARTS, decisions=[decision])
    _, kinds, _ = _flows(bp)

    assert "Activity_submit_ERP_system__approved_invoice_data_" in kinds
    _assert_safe(bp)


def test_a_marked_sender_on_both_branches_with_an_own_report_draws_nothing():
    """Both ways send, and the report is the agent's on every way: no box."""
    steps = [
        UPLOAD,
        EXTRACT,
        _report("make_doc", ["extract"]),
        _send("send_small", ["make_doc"]),
        _send("send_large", ["make_doc"]),
    ]
    decision = _decision("size", "make_doc", ("small", "send_small"), ("large", "send_large"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])
    _, kinds, _ = _flows(bp)

    assert PDF not in kinds
    assert not any(k.startswith("Activity_submit_") for k in kinds)
    _assert_each_finished_run_passes_once(
        bp, {"Activity_make_doc"}, {"Activity_send_small", "Activity_send_large"}
    )


def test_a_marked_sender_before_the_review_leaves_the_report_after_approval():
    steps = [
        UPLOAD,
        EXTRACT,
        _send("send_erp", ["extract"]),
        _step("review", "human_review", deps=["send_erp"], inputs=["record"]),
    ]
    bp = _blueprint(steps, BASE_ARTS)

    for order in _assert_safe(bp):
        assert order.index("Activity_review") < order.index(PDF)


def test_a_sender_before_approval_keeps_the_generated_sender():
    review = _step("review", "human_review", deps=["deliver"], inputs=["record"])
    bp = _blueprint(
        [UPLOAD, EXTRACT, _send("deliver", ["extract"]), review],
        BASE_ARTS,
        outputs=("structured_json",),
    )
    flows, kinds, _ = _flows(bp)
    (sender,) = [node for node, kind in kinds.items() if kind == "sendTask"]
    assert ("Gateway_approve_review", sender) in flows


def test_a_sender_before_the_own_report_keeps_the_generated_sender():
    bp = _blueprint(
        [UPLOAD, EXTRACT, _send("deliver", ["extract"]), _report("make_doc", ["deliver"])],
        {**BASE_ARTS, **_report_art("make_doc")},
    )
    flows, kinds, _ = _flows(bp)
    (sender,) = [node for node, kind in kinds.items() if kind == "sendTask"]
    assert PDF not in kinds
    assert ("Activity_make_doc", sender) in flows


@pytest.mark.parametrize(
    ("targets", "stores"),
    [
        (("erp", "archive"), ("DataStore_erp", "DataStore_archive")),
        (("erp-system", "erp_system"), ("DataStore_erp_system", "DataStore_erp_system_2")),
    ],
)
def test_each_store_sits_under_its_own_sender(targets, stores):
    bp = _blueprint(
        [
            UPLOAD,
            EXTRACT,
            _send("first_destination", ["extract"], target=targets[0]),
            _send("second_destination", ["first_destination"], target=targets[1]),
        ],
        BASE_ARTS,
        targets=targets,
        outputs=("structured_json",),
    )
    _, kinds, writes = _flows(bp)
    assert "sendTask" not in kinds.values()
    first, second = stores
    assert first in writes["Activity_first_destination"]
    assert second in writes["Activity_second_destination"]
    centers = {}
    for shape in ET.fromstring(generate_bpmn(bp)).iter(
        "{http://www.omg.org/spec/BPMN/20100524/DI}BPMNShape"
    ):
        bounds = shape[0]
        centers[shape.get("bpmnElement")] = float(bounds.get("x")) + float(bounds.get("width")) / 2
    assert centers[first] == centers["Activity_first_destination"]
    assert centers[second] == centers["Activity_second_destination"]
    assert centers[first] != centers[second]


def test_done_mapping_distinguishes_work_before_and_after_the_anchor():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _report("make_doc", ["review"]),
        _send("deliver", ["make_doc"]),
        _step("announce", deps=["deliver"]),
    ]
    decision = _decision("finish", "deliver", ("announce", "announce"), ("done", "end"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])
    generate_bpmn(bp)
    mapping = bp.visualizations["bpmn_mapping"]
    assert not any(entry["kind"] in ("pdf_generation", "send_task") for entry in mapping.values())
    assert mapping["Activity_extract"]["done_report"] == "conditional"
    assert mapping["Activity_extract"]["done_delivery"] == "conditional"
    assert mapping["Activity_make_doc"]["done_report"] == "complete"
    assert mapping["Activity_make_doc"]["done_delivery"] == "conditional"
    assert mapping["Gateway_decision_finish"]["done_report"] == "complete"
    assert mapping["Gateway_decision_finish"]["done_delivery"] == "complete"


def test_a_sender_on_one_way_of_a_fork_keeps_the_submit_task():
    """A fork: one way reviews and sends, the other reaches a decision whose
    branch ends. The success end can be reached without the send step, so the
    generated submission stays."""
    steps = [
        UPLOAD,
        EXTRACT,
        _report("make_doc", ["upload"]),
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _send("deliver", ["review"]),
        _step("screen", deps=["upload"]),
        _step("flag", deps=["screen"]),
    ]
    decision = _decision("s", "screen", ("clean", "end"), ("odd", "flag"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])
    _, kinds, _ = _flows(bp)

    assert "Activity_submit_ERP_system__approved_invoice_data_" in kinds
    _assert_safe(bp)


def test_targets_whose_ids_could_collide_keep_unique_ids():
    """Targets "erp" and "erp_auto" with a decision "auto": no generated id is
    built from a target and a decision, so none can repeat."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _send("deliver", ["review"], target="erp"),
    ]
    decision = _decision("auto", "extract", ("small", "end"), ("big", "review"))
    bp = _blueprint(steps, BASE_ARTS, targets=("erp", "erp_auto"), decisions=[decision])

    _assert_safe(bp)


def test_a_rework_branch_beside_the_report_keeps_one_way_through_it():
    """extract forks into check and the report then send; a decision after
    check has done to "end" and rework back to extract. The report and the send
    are on every way to the end, so nothing is generated."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("check", deps=["extract"]),
        _report("make_doc", ["extract"]),
        _send("deliver", ["make_doc"]),
    ]
    decision = _decision("ok", "check", ("done", "end"), ("rework", "extract"))
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])

    _assert_safe(bp)


def test_two_decisions_and_a_join_stay_safe():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _step("verify", deps=["extract"]),
        _step("check", deps=["review"]),
        _report("make_doc", ["check", "verify"]),
        _send("deliver", ["make_doc"]),
    ]
    decisions = [
        _decision("auto", "extract", ("small", "end"), ("big", "review")),
        _decision("again", "make_doc", ("fine", "deliver"), ("redo", "check")),
    ]
    bp = _blueprint(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=decisions)
    root = ET.fromstring(generate_bpmn(bp))
    ids = [e.get("id") for e in root.iter() if e.get("id")]

    assert len(ids) == len(set(ids))
    _, kinds, _ = _flows(bp)
    assert PDF in kinds


def test_a_marker_on_a_decision_step_is_not_taken_for_the_submission():
    """A step of type "decision" is drawn as a gateway: it sends nothing, so the
    target keeps its generated box and no gateway writes the data store."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("route", "decision", deps=["extract"], parameters={"integration_target": ERP}),
        _step("done", deps=["route"]),
    ]
    _, kinds, writes = _flows(_blueprint(steps, BASE_ARTS, outputs=("structured_json",)))

    assert any(k.startswith("Activity_submit_") for k in kinds)
    assert not any(w for k, w in writes.items() if kinds.get(k) == "exclusiveGateway")


def test_the_shared_rules_read_final_output_as_the_blueprint_does():
    from solution_wizard.bpmn_generator import final_report_step_ids

    arts = {
        "r": {"type": "pdf", "source": "generated", "produced_by": "make", "final_output": "true"}
    }
    steps = [{"id": "make", "outputs": ["r"]}]
    assert final_report_step_ids(steps, arts) == ["make"]
    arts["r"]["final_output"] = "false"
    assert final_report_step_ids(steps, arts) == []


# -- the reviewed shapes draw as develop does -----------------------------------
#
# In each of these a way to the end skips the agent's own steps, so the diagram
# must be exactly what develop drew. tests/fixtures/bpmn_develop/ holds each
# blueprint (<name>.json) and develop's drawing of it (<name>.bpmn), made at the
# commit in tests/fixtures/bpmn_develop/DEVELOP_COMMIT by
#     python tests/fixtures/bpmn_develop/regenerate.py
# (from implementation_layer/solution_wizard). After a deliberate change to the
# layout, regenerate them and review the change in the diagrams.


def _shape_auto_approval_to_end():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _report("make_doc", ["review"]),
        _send("deliver", ["make_doc"]),
    ]
    decision = _decision("auto", "extract", ("small", "end"), ("big", "review"))
    return _blueprint_dict(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])


def _shape_sender_with_generated_report():
    return _blueprint_dict([UPLOAD, EXTRACT, _send("send_erp", ["extract"])], BASE_ARTS)


def _shape_two_senders_on_two_branches():
    steps = [UPLOAD, EXTRACT, _send("send_small", ["extract"]), _send("send_large", ["extract"])]
    decision = _decision("size", "extract", ("small", "send_small"), ("large", "send_large"))
    return _blueprint_dict(steps, BASE_ARTS, decisions=[decision])


def _shape_sender_before_review():
    steps = [
        UPLOAD,
        EXTRACT,
        _send("send_erp", ["extract"]),
        _step("review", "human_review", deps=["send_erp"], inputs=["record"]),
    ]
    return _blueprint_dict(steps, BASE_ARTS)


def _shape_sender_on_one_way_of_a_fork():
    steps = [
        UPLOAD,
        EXTRACT,
        _report("make_doc", ["upload"]),
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _send("deliver", ["review"]),
        _step("screen", deps=["upload"]),
        _step("flag", deps=["screen"]),
    ]
    decision = _decision("s", "screen", ("clean", "end"), ("odd", "flag"))
    return _blueprint_dict(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=[decision])


def _shape_targets_that_could_collide():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _send("deliver", ["review"], target="erp"),
    ]
    decision = _decision("auto", "extract", ("small", "end"), ("big", "review"))
    return _blueprint_dict(steps, BASE_ARTS, targets=("erp", "erp_auto"), decisions=[decision])


def _shape_report_on_one_branch_only():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("route", deps=["extract"]),
        _step("manager", "user_task", deps=["route"]),
        _report("make_document", ["manager"]),
        _step("archive", deps=["route"]),
    ]
    decision = _decision("big", "route", ("yes", "manager"), ("no", "archive"))
    return _blueprint_dict(
        steps, {**BASE_ARTS, **_report_art("make_document")}, targets=(), decisions=[decision]
    )


def _shape_two_decisions_and_a_join():
    steps = [
        UPLOAD,
        EXTRACT,
        _step("review", "human_review", deps=["extract"], inputs=["record"]),
        _step("verify", deps=["extract"]),
        _step("check", deps=["review"]),
        _report("make_doc", ["check", "verify"]),
        _send("deliver", ["make_doc"]),
    ]
    decisions = [
        _decision("auto", "extract", ("small", "end"), ("big", "review")),
        _decision("again", "make_doc", ("fine", "deliver"), ("redo", "check")),
    ]
    return _blueprint_dict(steps, {**BASE_ARTS, **_report_art("make_doc")}, decisions=decisions)


DEVELOP_SHAPES = {
    "auto_approval_to_end": _shape_auto_approval_to_end,
    "sender_with_generated_report": _shape_sender_with_generated_report,
    "two_senders_on_two_branches": _shape_two_senders_on_two_branches,
    "sender_before_review": _shape_sender_before_review,
    "sender_on_one_way_of_a_fork": _shape_sender_on_one_way_of_a_fork,
    "targets_that_could_collide": _shape_targets_that_could_collide,
    "report_on_one_branch_only": _shape_report_on_one_branch_only,
    "two_decisions_and_a_join": _shape_two_decisions_and_a_join,
}

FIXTURES = Path(__file__).parent / "fixtures" / "bpmn_develop"


@pytest.mark.parametrize("name", sorted(DEVELOP_SHAPES))
def test_a_shape_whose_ways_skip_the_own_steps_draws_as_develop_did(name):
    blueprint = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    # The fixture is the blueprint the shape builds, so a change to the shape
    # is not silently tested against an old drawing.
    assert blueprint == json.loads(json.dumps(DEVELOP_SHAPES[name]()))
    expected = (FIXTURES / f"{name}.bpmn").read_text(encoding="utf-8").replace("\r\n", "\n")

    assert generate_bpmn(Blueprint.model_validate(blueprint)) == expected


def test_a_choice_that_skips_the_report_through_a_rework_loop_keeps_the_generated_report():
    """A decision chooses "write" (the agent's report step) or "get" (an
    existing record); both lead to a check, which can rework back to "get".
    The way through "get" skips the report, so the generated one stays."""
    steps = [
        UPLOAD,
        EXTRACT,
        _report("make_doc", ["extract"]),
        _step("fetch", deps=["extract"]),
        _step("check", deps=["make_doc", "fetch"]),
    ]
    decisions = [
        _decision("src", "extract", ("write", "make_doc"), ("get", "fetch")),
        _decision("ok", "check", ("done", "end"), ("rework", "fetch")),
    ]
    bp = _blueprint(
        steps, {**BASE_ARTS, **_report_art("make_doc")}, targets=(), decisions=decisions
    )
    _, kinds, _ = _flows(bp)

    assert PDF in kinds


def test_a_decision_step_is_not_taken_for_the_report_writer():
    """A step of type "decision" is drawn as a gateway: it writes nothing, so a
    final PDF it declares does not stand for the report."""
    steps = [
        UPLOAD,
        EXTRACT,
        _step("route", "decision", deps=["extract"], outputs=["route_pdf"]),
        _step("done", deps=["route"]),
    ]
    arts = {**BASE_ARTS, **_report_art("route")}
    _, kinds, _ = _flows(_blueprint(steps, arts, targets=()))

    assert PDF in kinds
