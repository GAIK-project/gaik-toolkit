"""A decision's branches are drawn once, and every successful path gets the report and delivery.

Found in an invoice run: a decision after "Route invoice" with a branch to the
finance manager drew the route -> manager flow twice, and the PDF report and the
ERP submission were each spliced onto a different flow into the end, so in the
diagram auto-approved invoices got no PDF and manager-approved ones never reached
the ERP. These cases are generic: any decision before a step, and any process with
more than one way to finish and a report or an integration target.
"""

import xml.etree.ElementTree as ET

from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import generate_bpmn

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
END = "EndEvent_success"


def _blueprint(steps, *, outputs=("structured_json",), targets=(), decisions=(), exceptions=()):
    return Blueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "use_case": {"id": "uc", "name": "Case", "description": "x", "domain": "t"},
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
                "selected_building_blocks": ["Extractor"],
                "custom_components": [],
            },
            "artifacts": {
                "src": {"type": "pdf", "source": "user_upload", "optional": False},
                "out": {
                    "type": "structured_json",
                    "source": "generated",
                    "optional": False,
                    "final_output": True,
                    "produced_by": "extract",
                },
            },
            "workflow": {"steps": steps},
            "business_process": {
                "decision_points": list(decisions),
                "exceptions": list(exceptions),
            },
        }
    )


def _step(sid, kind="automated_task", deps=(), inputs=("out",)):
    step = {
        "id": sid,
        "name": sid.replace("_", " ").title(),
        "type": kind,
        "inputs": list(inputs),
        "outputs": [],
        "depends_on": list(deps),
    }
    if kind == "automated_task":
        step["component"] = "Extractor"
    return step


def _invoice(*, outputs=("structured_json", "pdf"), targets=("erp_system",)):
    """upload -> extract -> route -> (auto: end | otherwise: manager review)."""
    steps = [
        _step("upload", "user_task", inputs=()),
        dict(_step("extract", deps=["upload"], inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("manager", "human_review", deps=["route"]),
    ]
    return _blueprint(
        steps,
        outputs=outputs,
        targets=targets,
        decisions=[
            {
                "id": "auto",
                "name": "Auto-approve?",
                "after": "route",
                "branches": [
                    {"condition": "under 5,000 EUR", "target": "end"},
                    {"condition": "otherwise", "target": "manager"},
                ],
            }
        ],
        exceptions=[
            {
                "id": "rejected",
                "name": "Rejected",
                "attached_to": "manager",
                "condition": "No",
                "outcome": "loop_to:upload",
            }
        ],
    )


def _flows(bp):
    xml = generate_bpmn(bp)
    proc = ET.fromstring(xml).find("bpmn:process", NS)
    flows = [
        (f.get("sourceRef"), f.get("targetRef"), f.get("name") or "")
        for f in proc.findall("bpmn:sequenceFlow", NS)
    ]
    kinds = {e.get("id"): e.tag.split("}")[-1] for e in proc}
    return flows, kinds


def _start(kinds):
    return next(nid for nid, kind in kinds.items() if kind == "startEvent")


def _reaches_end_without(flows, start, skipped):
    """Whether the success end can be reached from the start without passing ``skipped``."""
    seen, todo = {start}, [start]
    while todo:
        node = todo.pop()
        for src, tgt, _ in flows:
            if src == node and tgt != skipped and tgt not in seen:
                seen.add(tgt)
                todo.append(tgt)
    return END in seen


def test_a_decision_branch_to_its_own_steps_successor_is_drawn_once():
    flows, _ = _flows(_invoice())

    into_manager = [(s, n) for s, t, n in flows if t == "Activity_manager"]
    assert into_manager == [("Gateway_decision_auto", "otherwise")]


def _routed_two_ways():
    """route leads to both "accept" and "manager" (two dependents), and a decision
    after route picks one: the agent's draft in a second invoice run."""
    steps = [
        _step("upload", "user_task", inputs=()),
        dict(_step("extract", deps=["upload"], inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("accept", deps=["route"]),
        _step("manager", "human_review", deps=["route"]),
    ]
    return _blueprint(
        steps,
        outputs=("structured_json", "pdf"),
        targets=("erp_system",),
        decisions=[
            {
                "id": "big",
                "name": "Over 5,000 EUR?",
                "after": "route",
                "branches": [
                    {"condition": "Yes", "target": "manager"},
                    {"condition": "No", "target": "accept"},
                ],
            }
        ],
    )


def test_a_decision_after_a_step_with_two_successors_replaces_the_parallel_fork():
    flows, kinds = _flows(_routed_two_ways())

    assert "Gateway_fork_route" not in kinds
    assert not any(kind == "parallelGateway" for kind in kinds.values())
    assert [(s, n) for s, t, n in flows if t == "Activity_manager"] == [
        ("Gateway_decision_big", "Yes")
    ]
    assert [(s, n) for s, t, n in flows if t == "Activity_accept"] == [
        ("Gateway_decision_big", "No")
    ]
    assert [t for s, t, _ in flows if s == "Activity_route"] == ["Gateway_decision_big"]


def test_a_branch_to_a_step_whose_join_its_own_step_does_not_feed_goes_to_the_step():
    """post waits for a and b; the decision after check leads to post or fix.
    The join before post is fed by a and b only: a branch into it would make the
    join wait for a token that comes only when that branch is taken."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("a", deps=["extract"]),
        _step("b", deps=["extract"]),
        _step("check", deps=["extract"]),
        _step("fix", deps=["check"]),
        _step("post", deps=["a", "b"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "ok",
                "name": "OK?",
                "after": "check",
                "branches": [
                    {"condition": "ok", "target": "post"},
                    {"condition": "bad", "target": "fix"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    assert sorted((t, n) for s, t, n in flows if s == "Gateway_decision_ok") == [
        ("Activity_fix", "bad"),
        ("Activity_post", "ok"),
    ]
    assert kinds["Gateway_join_post"] == "parallelGateway"
    assert sorted(s for s, t, _ in flows if t == "Gateway_join_post") == [
        "Activity_a",
        "Activity_b",
    ]


def test_a_step_the_decision_does_not_choose_still_runs_beside_it():
    """route leads to accept, manager and notify; the decision picks between
    accept and manager only, so notify always runs: the fork stays in front of
    the decision and notify, and notify gets no unnamed branch."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("accept", deps=["route"]),
        _step("manager", "user_task", deps=["route"]),
        _step("notify", deps=["route"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "big",
                "name": "Big?",
                "after": "route",
                "branches": [
                    {"condition": "Yes", "target": "manager"},
                    {"condition": "No", "target": "accept"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    assert kinds["Gateway_fork_route"] == "parallelGateway"
    assert [t for s, t, _ in flows if s == "Activity_route"] == ["Gateway_fork_route"]
    assert sorted(t for s, t, _ in flows if s == "Gateway_fork_route") == [
        "Activity_notify",
        "Gateway_decision_big",
    ]
    assert sorted((t, n) for s, t, n in flows if s == "Gateway_decision_big") == [
        ("Activity_accept", "No"),
        ("Activity_manager", "Yes"),
    ]


def test_the_merge_gateway_does_not_take_the_id_of_a_decision_step():
    """A workflow step of type "decision" is drawn as Gateway_<id>: one called
    merge_success must keep its gateway, and the merge takes another id."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        {
            "id": "merge_success",
            "name": "Merge success?",
            "type": "decision",
            "inputs": ["out"],
            "outputs": [],
            "depends_on": ["extract"],
        },
        _step("notify", deps=["merge_success"]),
        _step("archive", deps=["merge_success"]),
    ]
    flows, kinds = _flows(_blueprint(steps, outputs=["structured_json", "pdf"]))

    assert ("Activity_extract", "Gateway_merge_success") in {(s, t) for s, t, _ in flows}
    merges = {t for s, t, _ in flows if s in ("Activity_notify", "Activity_archive")}
    assert len(merges) == 1
    merge = merges.pop()
    assert merge != "Gateway_merge_success"
    assert [t for s, t, _ in flows if s == merge] == ["Activity_generate_pdf"]


def test_after_the_fork_is_replaced_both_ways_still_get_the_report_and_submission():
    flows, kinds = _flows(_routed_two_ways())
    start = _start(kinds)

    merge = next(t for s, t, _ in flows if t.startswith("Gateway_merge"))
    assert kinds[merge] == "exclusiveGateway"
    assert not _reaches_end_without(flows, start, "Activity_generate_pdf")
    assert not _reaches_end_without(flows, start, "Activity_submit_erp_system")


def test_every_successful_path_passes_the_pdf_report_and_the_submission():
    flows, kinds = _flows(_invoice())
    start = _start(kinds)

    assert END in {t for _, t, _ in flows}
    assert not _reaches_end_without(flows, start, "Activity_generate_pdf")
    assert not _reaches_end_without(flows, start, "Activity_submit_erp_system")
    # Report first, then the submission, then the end.
    assert ("Activity_generate_pdf", "Activity_submit_erp_system") in {(s, t) for s, t, _ in flows}
    assert [s for s, t, _ in flows if t == END] == ["Activity_submit_erp_system"]


def test_the_alternative_endings_meet_at_an_exclusive_merge_before_the_report():
    flows, kinds = _flows(_invoice())

    merge = next(t for s, t, _ in flows if s != t and t.startswith("Gateway_merge"))
    assert kinds[merge] == "exclusiveGateway"
    sources = {s for s, t, _ in flows if t == merge}
    assert sources == {"Gateway_decision_auto", "Gateway_approve_manager"}
    assert [t for s, t, _ in flows if s == merge] == ["Activity_generate_pdf"]


def test_a_triage_with_two_endings_submits_on_both():
    """A second, different process: urgent tickets are escalated, the rest end;
    both go to the ticket system, and there is no report."""
    steps = [
        dict(_step("classify", inputs=["src"]), outputs=["out"]),
        _step("escalate", "user_task", deps=["classify"]),
    ]
    bp = _blueprint(
        steps,
        targets=["ticket_system"],
        decisions=[
            {
                "id": "urgent",
                "name": "Urgent?",
                "after": "classify",
                "branches": [
                    {"condition": "urgent", "target": "escalate"},
                    {"condition": "normal", "target": "end"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    assert "Activity_generate_pdf" not in kinds
    assert not _reaches_end_without(flows, _start(kinds), "Activity_submit_ticket_system")
    assert [(s, n) for s, t, n in flows if t == "Activity_escalate"] == [
        ("Gateway_decision_urgent", "urgent")
    ]


def test_steps_that_all_run_meet_at_a_parallel_join_before_the_report():
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("notify", deps=["extract"]),
        _step("archive", deps=["extract"]),
    ]
    flows, kinds = _flows(_blueprint(steps, outputs=["structured_json", "pdf"]))

    merge = next(t for s, t, _ in flows if t.startswith("Gateway_merge"))
    assert kinds[merge] == "parallelGateway"
    assert {s for s, t, _ in flows if t == merge} == {"Activity_notify", "Activity_archive"}
    assert not _reaches_end_without(flows, _start(kinds), "Activity_generate_pdf")


def test_steps_that_all_run_after_a_review_meet_at_a_parallel_join():
    """A review's approval has a "No" to a rejection end; that is no choice
    between the steps after it, which all run: an exclusive merge would run the
    report and the submission once for each of them."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("review", "human_review", deps=["extract"]),
        _step("notify", deps=["review"]),
        _step("archive", deps=["review"]),
    ]
    flows, kinds = _flows(_blueprint(steps, outputs=["structured_json", "pdf"], targets=["erp"]))

    merge = next(t for s, t, _ in flows if t.startswith("Gateway_merge"))
    assert kinds[merge] == "parallelGateway"


def test_a_step_after_both_ways_of_a_decision_is_reached_once_through_an_exclusive_merge():
    """ERP depends on both the accepted and the manager-approved way: the join
    before it would wait for two alternatives and never go on."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("accept", deps=["route"]),
        _step("manager", "user_task", deps=["route"]),
        _step("erp", deps=["accept", "manager"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "big",
                "name": "Big?",
                "after": "route",
                "branches": [
                    {"condition": "Yes", "target": "manager"},
                    {"condition": "No", "target": "accept"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    join = next(t for s, t, _ in flows if t == "Gateway_join_erp")
    assert kinds[join] == "exclusiveGateway"
    assert [s for s, t, _ in flows if t == "Activity_erp"] == [join]
    assert sorted(n for s, t, n in flows if s == "Gateway_decision_big") == ["No", "Yes"]


def test_a_branch_to_a_step_behind_a_join_is_drawn_once():
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("manager", "user_task", deps=["route"]),
        _step("erp", deps=["route", "manager"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "big",
                "name": "Big?",
                "after": "route",
                "branches": [
                    {"condition": "Yes", "target": "manager"},
                    {"condition": "No", "target": "erp"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    assert sorted((t, n) for s, t, n in flows if s == "Gateway_decision_big") == [
        ("Activity_manager", "Yes"),
        ("Gateway_join_erp", "No"),
    ]
    assert kinds["Gateway_join_erp"] == "exclusiveGateway"
    assert [s for s, t, _ in flows if t == "Activity_erp"] == ["Gateway_join_erp"]


def test_without_a_report_or_an_integration_the_endings_are_left_as_they_are():
    flows, kinds = _flows(_invoice(outputs=("structured_json",), targets=()))

    assert not any(nid.startswith("Gateway_merge") for nid in kinds)
    assert {s for s, t, _ in flows if t == END} == {
        "Gateway_decision_auto",
        "Gateway_approve_manager",
    }


def test_a_single_path_is_drawn_as_before():
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("review", "human_review", deps=["extract"]),
    ]
    flows, kinds = _flows(_blueprint(steps, outputs=["structured_json", "pdf"], targets=["erp"]))

    assert not any(nid.startswith("Gateway_merge") for nid in kinds)
    assert ("Gateway_approve_review", "Activity_generate_pdf") in {(s, t) for s, t, _ in flows}


def _ok_or_end(after):
    return {
        "id": f"ok_{after}",
        "name": "OK?",
        "after": after,
        "branches": [
            {"condition": "ok", "target": "post"},
            {"condition": "bad", "target": "end"},
        ],
    }


def test_a_decision_after_a_step_that_feeds_a_join_keeps_the_join():
    """post waits for a and b; a decision after a (and one after b) leads to post
    or the end. The join before post is no fork after a: it stays, and the flow
    from b still reaches it (it was removed, and a second such decision failed
    the whole diagram)."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("a", deps=["extract"]),
        _step("b", deps=["extract"]),
        _step("post", deps=["a", "b"]),
    ]
    for decisions in ([_ok_or_end("a")], [_ok_or_end("a"), _ok_or_end("b")]):
        flows, kinds = _flows(_blueprint(steps, decisions=decisions))

        assert all(s in kinds and t in kinds for s, t, _ in flows)
        assert kinds["Gateway_join_post"] == "parallelGateway"
        sources = {s for s, t, _ in flows if t == "Gateway_join_post"}
        assert "Gateway_decision_ok_a" in sources
        assert len(sources) == 2
        assert [s for s, t, _ in flows if t == "Activity_post"] == ["Gateway_join_post"]


def test_steps_that_all_run_after_a_decision_whose_ways_meet_again_stay_parallel():
    """The decision's two ways meet again before erp; notify and archive both run
    after it, so they meet at a parallel join, not an exclusive one that would
    render the report once for each of them."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("route", deps=["extract"]),
        _step("accept", deps=["route"]),
        _step("manager", "user_task", deps=["route"]),
        _step("erp", deps=["accept", "manager"]),
        _step("notify", deps=["erp"]),
        _step("archive", deps=["erp"]),
    ]
    bp = _blueprint(
        steps,
        outputs=["structured_json", "pdf"],
        decisions=[
            {
                "id": "big",
                "name": "Big?",
                "after": "route",
                "branches": [
                    {"condition": "Yes", "target": "manager"},
                    {"condition": "No", "target": "accept"},
                ],
            }
        ],
    )
    flows, kinds = _flows(bp)

    assert kinds["Gateway_join_erp"] == "exclusiveGateway"
    merge = next(t for s, t, _ in flows if t.startswith("Gateway_merge"))
    assert kinds[merge] == "parallelGateway"
    assert {s for s, t, _ in flows if t == merge} == {"Activity_notify", "Activity_archive"}


def test_a_decision_that_sends_a_case_back_leaves_a_later_join_parallel():
    """Both ways of the decision reach p and q (one through the earlier steps
    again): it chooses nothing between them, and r still waits for both."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("check", deps=["extract"]),
        _step("nxt", deps=["check"]),
        _step("p", deps=["nxt"]),
        _step("q", deps=["nxt"]),
        _step("r", deps=["p", "q"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "complete",
                "name": "Complete?",
                "after": "check",
                "branches": [
                    {"condition": "no", "target": "extract"},
                    {"condition": "yes", "target": "nxt"},
                ],
            }
        ],
    )
    _, kinds = _flows(bp)

    assert kinds["Gateway_join_r"] == "parallelGateway"


def test_a_decision_step_with_an_id_like_a_join_stays_a_decision():
    """A step of type "decision" called join_check is drawn as Gateway_join_check,
    the id a join would have: a branch into it does not make it a join."""
    steps = [
        dict(_step("extract", inputs=["src"]), outputs=["out"]),
        _step("a", deps=["extract"]),
        _step("b", deps=["extract"]),
        {
            "id": "join_check",
            "name": "Check?",
            "type": "decision",
            "inputs": ["out"],
            "outputs": [],
            "depends_on": ["a"],
        },
        _step("c", deps=["join_check"]),
        _step("d", deps=["join_check"]),
    ]
    bp = _blueprint(
        steps,
        decisions=[
            {
                "id": "more",
                "name": "More?",
                "after": "b",
                "branches": [
                    {"condition": "yes", "target": "join_check"},
                    {"condition": "no", "target": "end"},
                ],
            }
        ],
    )
    _, kinds = _flows(bp)

    assert kinds["Gateway_join_check"] == "exclusiveGateway"
