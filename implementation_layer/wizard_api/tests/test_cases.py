"""Cases: the generated solution run as a process, on real input (case_service).

A case goes draft → running (the sandbox runs the package on the case's own
input) → review → approved, or back to the person who gave the input when the
reviewer returns it. What carries the weight: a case run reads only its own
input, a run's result is found in the run log by the output fields, and a
record the reviewer approves passes the same checks the form makes.
"""

import io
import json
import os
import re
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers import requires_postgres, write_gate_artifacts
from wizard_api.services import (
    artifact_sync,
    case_service,
    input_content,
    poc_service,
    session_service,
)
from wizard_api.services.sandbox_runner import (
    CASE_KIND,
    CASE_LABEL,
    RUN_KIND_LABEL,
    SandboxRunner,
    render_job_manifest,
)

IMAGE = "registry.example/gaik/wizard-v2-poc-runner:latest"
SESSION = "0b5b7b2b-a9ce-4896-b224-8d73614a9bb7"

SPEC = {
    "schema_name": "Ticket",
    "fields": ["reporter", "location", "urgency", "seen_on", "uncertain_fields"],
    "field_types": {"uncertain_fields": "list[string]"},
    "required_fields": ["location", "urgency"],
    "field_descriptions": {"seen_on": "Date it was seen, DD/MM/YYYY"},
    "allowed_values": {"urgency": ["low", "medium", "high"]},
}

RECORD = {
    "reporter": "A. Tester",
    "location": "Hall 3",
    "urgency": "high",
    "seen_on": "01/02/2026",
    "uncertain_fields": [],
}


def _log(record=RECORD, transcript="the spoken report"):
    return "\n".join(
        [
            "starting",
            "=== POC OUTPUT BEGIN ===",
            "--- output/report_ticket.json ---",
            json.dumps([record]),
            "--- output/report_validation.json ---",
            json.dumps({"hallucination_flags": [], "passed": True}),
            "--- output/report_transcript.txt ---",
            transcript,
            "",
            "=== POC OUTPUT END ===",
        ]
    )


@pytest.fixture
def out(tmp_path):
    return str(tmp_path)


def _running_case(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF....WAVE")
    return case_service.mark_submitted(out, case["id"], run_id="r1", role="Technician", note="")


# ---------------------------------------------------------------------------
# A case and its input
# ---------------------------------------------------------------------------


def test_a_new_case_is_a_draft_with_no_input(out):
    case = case_service.create_case(out, created_by="u")

    assert case["status"] == "draft"
    assert case["round"] == 1
    assert case_service.get_case(out, case["id"])["inputs"] == []


def test_an_input_is_stored_with_the_case_not_in_the_package(out):
    case = case_service.create_case(out, created_by="u")

    case_service.save_input(out, case["id"], "report.wav", b"RIFF....WAVE")

    assert case_service.get_case(out, case["id"])["inputs"] == [
        {"name": "report.wav", "bytes": 12, "task": None}
    ]
    assert not os.path.exists(os.path.join(out, "poc", "sample_input"))


def test_a_case_holds_so_many_files_and_so_many_bytes(out, monkeypatch):
    monkeypatch.setattr(case_service, "MAX_INPUTS_PER_CASE", 2)
    monkeypatch.setattr(case_service, "MAX_CASE_INPUT_BYTES", 20)
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "a.txt", b"x" * 8)
    case_service.save_input(out, case["id"], "b.txt", b"x" * 8)

    with pytest.raises(poc_service.InputRejectedError, match="already has 2 input files"):
        case_service.save_input(out, case["id"], "c.txt", b"x")
    case_service.delete_input(out, case["id"], "b.txt")
    with pytest.raises(poc_service.InputTooLargeError, match="exceed 0 MB in all"):
        case_service.save_input(out, case["id"], "c.txt", b"x" * 13)
    assert case_service.save_input(out, case["id"], "c.txt", b"x" * 12) == "c.txt"


def test_a_session_holds_so_many_cases(out, monkeypatch):
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 1)
    case_service.create_case(out, created_by="u")

    with pytest.raises(case_service.CaseStateError, match="already has 1 open cases"):
        case_service.create_case(out, created_by="u")


def test_a_closed_case_frees_its_place_and_its_input(out, monkeypatch):
    """A long-lived session keeps working: only open cases count against the caps."""
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 1)
    monkeypatch.setattr(case_service, "MAX_SESSION_INPUT_BYTES", 20)
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "a.wav", b"x" * 15)
    case_service.mark_submitted(out, case["id"], run_id="r1", role="Technician", note="")
    with pytest.raises(case_service.CaseStateError, match="already has 1 open cases"):
        case_service.create_case(out, created_by="u")

    done = case_service.finish_run(
        out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC, review_needed=False
    )
    assert done["status"] == "completed"
    second = case_service.create_case(out, created_by="u")
    assert case_service.save_input(out, second["id"], "b.wav", b"x" * 15) == "b.wav"


def test_cases_opened_at_once_stop_at_the_limit(out, monkeypatch):
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 3)

    def attempt(_):
        try:
            return case_service.create_case(out, created_by="u")["id"]
        except case_service.CaseStateError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        opened = [i for i in pool.map(attempt, range(12)) if i]

    assert len(opened) == 3
    assert {c["id"] for c in case_service.list_cases(out)} == set(opened)


def test_the_session_limits_come_from_the_environment(out, monkeypatch):
    monkeypatch.setenv("WIZARD_MAX_CASES_PER_SESSION", "1")
    case_service.create_case(out, created_by="u")
    with pytest.raises(case_service.CaseStateError, match="already has 1 open cases"):
        case_service.create_case(out, created_by="u")

    monkeypatch.setenv("WIZARD_MAX_CASES_PER_SESSION", "not a number")
    assert case_service.max_cases_per_session() == case_service.MAX_CASES_PER_SESSION
    monkeypatch.setenv("WIZARD_MAX_SESSION_INPUT_MB", "0")
    assert case_service.max_session_input_bytes() == case_service.MAX_SESSION_INPUT_BYTES
    monkeypatch.setenv("WIZARD_MAX_SESSION_INPUT_MB", "300")
    assert case_service.max_session_input_bytes() == 300 * 1024 * 1024


def test_a_sessions_input_is_bounded_across_its_cases(out, monkeypatch):
    """Each case under its own limit can still fill the shared volume together."""
    monkeypatch.setattr(case_service, "MAX_SESSION_INPUT_BYTES", 20)
    first = case_service.create_case(out, created_by="u")
    second = case_service.create_case(out, created_by="u")
    case_service.save_input(out, first["id"], "a.txt", b"x" * 12)

    with pytest.raises(poc_service.InputTooLargeError, match="session's case input"):
        case_service.save_input(out, second["id"], "b.txt", b"x" * 9)
    assert case_service.save_input(out, second["id"], "b.txt", b"x" * 8) == "b.txt"

    case_service.delete_input(out, first["id"], "a.txt")
    assert case_service.save_input(out, second["id"], "c.txt", b"x" * 12) == "c.txt"


def test_an_input_name_that_climbs_out_is_refused(out):
    case = case_service.create_case(out, created_by="u")

    with pytest.raises(poc_service.InputRejectedError):
        case_service.save_input(out, case["id"], "../../poc/run_poc.py", b"print(1)")


def test_a_case_id_that_is_not_a_uuid_is_not_a_case(out):
    with pytest.raises(case_service.CaseNotFoundError):
        case_service.get_case(out, "../poc")


def test_a_file_of_a_name_already_in_the_case_is_refused_not_overwritten(out):
    case = case_service.create_case(out, created_by="dev")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF.1..", task="T_rec")

    with pytest.raises(case_service.InputExistsError, match="already in the case"):
        case_service.save_input(out, case["id"], "report.wav", b"RIFF.2..", task="T_aud")

    stored = case_service.get_case(out, case["id"])
    assert stored["input_tasks"] == {"report.wav": "T_rec"}
    assert case_service.input_path(out, case["id"], "report.wav").read_bytes() == b"RIFF.1.."


def test_uploads_at_the_same_time_all_keep_whose_they_were(out):
    from concurrent.futures import ThreadPoolExecutor

    case = case_service.create_case(out, created_by="dev")
    names = [f"part-{i}.txt" for i in range(12)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(
            pool.map(
                lambda n: case_service.save_input(out, case["id"], n, b"x", task=f"task-{n}"),
                names,
            )
        )

    stored = case_service.get_case(out, case["id"])
    assert stored["input_tasks"] == {n: f"task-{n}" for n in names}


def test_a_claimed_case_refuses_a_second_submit_and_is_given_back_without_a_run(out):
    case = case_service.create_case(out, created_by="dev")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF....")

    claimed = case_service.claim_submission(out, case["id"])
    assert claimed["status"] == "running" and claimed["run_id"] is None
    with pytest.raises(case_service.CaseStateError):
        case_service.claim_submission(out, case["id"])

    released = case_service.release_submission(out, case["id"])
    assert released["status"] == "draft"
    assert "claimed_from" not in released

    # A claim completed with its run is a running case like any other.
    case_service.claim_submission(out, case["id"])
    sent = case_service.mark_submitted(out, case["id"], run_id="r1", role="Technician", note="go")
    assert sent["status"] == "running" and sent["run_id"] == "r1"
    assert "claimed_at" not in sent
    assert case_service.release_submission(out, case["id"])["run_id"] == "r1"


def test_a_failed_case_given_back_keeps_its_run_and_reason(out):
    case = _running_case(out)
    failed = case_service.finish_run(
        out, case["id"], phase="failed", log=_TRACEBACK, message="backoff limit", spec=SPEC
    )
    case_service.claim_submission(out, case["id"])

    released = case_service.release_submission(out, case["id"])

    assert released["status"] == "failed"
    assert released["run_id"] == "r1"
    assert released["run_message"] == failed["run_message"]
    assert "claimed_from" not in released and "claimed_at" not in released


def test_a_claim_the_api_never_completed_is_given_back_once_stale(out):
    from datetime import UTC, datetime, timedelta

    case = case_service.create_case(out, created_by="dev")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF....")
    case_service.claim_submission(out, case["id"])

    fresh = case_service.release_stale_claim(out, case["id"])
    assert fresh["status"] == "running"
    later = datetime.now(UTC) + case_service.CLAIM_MAX_AGE + timedelta(seconds=1)
    stale = case_service.release_stale_claim(out, case["id"], now=later)
    assert stale["status"] == "draft"


# ---------------------------------------------------------------------------
# Removing a case that was never sent
# ---------------------------------------------------------------------------


def test_a_waiting_case_is_removed_with_its_input(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF....WAVE")

    case_service.delete_case(out, case["id"])

    assert case_service.list_cases(out) == []
    assert not os.path.exists(os.path.join(out, "cases", case["id"]))
    with pytest.raises(case_service.CaseNotFoundError):
        case_service.get_case(out, case["id"])
    # A request that was on its way to the case finds none, and writes nothing.
    with pytest.raises(case_service.CaseNotFoundError):
        case_service.save_input(out, case["id"], "late.wav", b"RIFF")
    assert not os.path.exists(os.path.join(out, "cases", case["id"]))


def test_removing_a_waiting_case_frees_its_place_and_its_input(out, monkeypatch):
    """The way out of a session full of open cases: nothing else closes a waiting one."""
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 1)
    monkeypatch.setattr(case_service, "MAX_SESSION_INPUT_BYTES", 20)
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "a.wav", b"x" * 15)
    with pytest.raises(case_service.CaseStateError, match="remove one that is still waiting"):
        case_service.create_case(out, created_by="u")

    case_service.delete_case(out, case["id"])

    second = case_service.create_case(out, created_by="u")
    assert case_service.save_input(out, second["id"], "b.wav", b"x" * 15) == "b.wav"


def _claimed(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "report.wav", b"RIFF....WAVE")
    return case_service.claim_submission(out, case["id"])


def _failed(out):
    case = _running_case(out)
    return case_service.finish_run(
        out, case["id"], phase="failed", log="KeyError: 'x'", message=None, spec=SPEC
    )


def _completed(out):
    case = _running_case(out)
    return case_service.finish_run(
        out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC, review_needed=False
    )


def _decided(action):
    def make(out):
        case = _in_review(out)
        return case_service.review(
            out, case["id"], action=action, role="Supervisor", record=None, comment="Why", spec=SPEC
        )

    return make


@pytest.mark.parametrize(
    ("make", "status"),
    [
        (_claimed, "running"),
        (lambda out: _running_case(out), "running"),
        (lambda out: _in_review(out), "review"),
        (_failed, "failed"),
        (_completed, "completed"),
        (_decided("return"), "returned"),
        (_decided("approve"), "approved"),
        (_decided("reject"), "rejected"),
    ],
)
def test_a_case_that_was_sent_is_not_removed(out, make, status):
    """A run, a result or a decision is the record of what was done: it stays."""
    case = make(out)
    assert case["status"] == status

    with pytest.raises(case_service.CaseStateError, match="only a case still waiting"):
        case_service.delete_case(out, case["id"])

    kept = case_service.get_case(out, case["id"])
    assert kept["status"] == status
    assert [f["name"] for f in kept["inputs"]] == ["report.wav"]
    assert case_service._removed(out) == ([], [])


def _cases_opened_at(out, monkeypatch, *times):
    stamps = iter(times)
    monkeypatch.setattr(case_service, "_now", lambda: next(stamps))
    return [case_service.create_case(out, created_by="u")["id"] for _ in times]


def _numbers(out):
    return {c["id"]: c["number"] for c in case_service.list_cases(out)}


def test_the_cases_left_keep_their_numbers_when_one_is_removed(out, monkeypatch):
    first, second, third = _cases_opened_at(
        out,
        monkeypatch,
        "2026-11-12T08:00:00+00:00",
        "2026-11-12T08:05:00+00:00",
        "2026-11-12T08:10:00+00:00",
    )
    assert _numbers(out) == {first: 1, second: 2, third: 3}

    case_service.delete_case(out, second)

    # #3 is still #3: a case is spoken of by its number.
    assert _numbers(out) == {first: 1, third: 3}
    (fourth,) = _cases_opened_at(out, monkeypatch, "2026-11-12T08:15:00+00:00")
    assert _numbers(out) == {first: 1, third: 3, fourth: 4}
    assert [c["id"] for c in case_service.list_cases(out)] == [fourth, third, first]


def test_a_removal_that_fails_leaves_the_case_and_its_number(out, monkeypatch):
    first, second = _cases_opened_at(
        out, monkeypatch, "2026-11-12T08:00:00+00:00", "2026-11-12T08:05:00+00:00"
    )
    case_service.save_input(out, first, "report.wav", b"RIFF....WAVE")
    rename = case_service.os.rename

    def disk_trouble(*args, **kwargs):
        raise OSError("device busy")

    monkeypatch.setattr(case_service.os, "rename", disk_trouble)
    with pytest.raises(OSError):
        case_service.delete_case(out, first)

    # Still a whole case the list shows, under the numbers they had.
    assert _numbers(out) == {first: 1, second: 2}
    kept = case_service.get_case(out, first)
    assert kept["status"] == "draft" and [f["name"] for f in kept["inputs"]] == ["report.wav"]
    monkeypatch.setattr(case_service.os, "rename", rename)
    case_service.delete_case(out, first)
    # Remembered once, though it was tried twice.
    assert _numbers(out) == {second: 2}
    assert case_service._removed(out) == ([], ["2026-11-12T08:00:00+00:00"])


def test_the_numbers_hold_at_every_moment_of_a_removal(out, monkeypatch):
    """The list is read without the session's lock, so it can be read half way."""
    first, second, third = _cases_opened_at(
        out,
        monkeypatch,
        "2026-11-12T08:00:00+00:00",
        "2026-11-12T08:05:00+00:00",
        "2026-11-12T08:10:00+00:00",
    )
    seen = []
    rename = case_service.os.rename

    def watched(src, dst):
        seen.append(_numbers(out))  # remembered as removed, still in place
        rename(src, dst)
        seen.append(_numbers(out))  # set aside, not yet deleted

    monkeypatch.setattr(case_service.os, "rename", watched)
    case_service.delete_case(out, first)

    assert seen == [{first: 1, second: 2, third: 3}, {second: 2, third: 3}]
    assert _numbers(out) == {second: 2, third: 3}


def test_a_removal_stopped_half_way_leaves_nothing_that_holds_a_place(out, monkeypatch):
    """The api can die while the folder is being deleted (a restart, a full disk)."""
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 1)
    monkeypatch.setattr(case_service, "MAX_SESSION_INPUT_BYTES", 20)
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "a.wav", b"x" * 15)
    rmtree = case_service.shutil.rmtree
    # The deletion never happens: what was set aside stays on the disk.
    monkeypatch.setattr(case_service.shutil, "rmtree", lambda *a, **k: None)
    case_service.delete_case(out, case["id"])
    left = [p.name for p in (Path(out) / "cases").iterdir() if p.is_dir()]
    assert left == [f".removed-{case['id']}"]

    # It is no case, holds no place and no bytes, and the next change sweeps it.
    assert case_service.list_cases(out) == []
    with pytest.raises(case_service.CaseNotFoundError):
        case_service.delete_case(out, case["id"])
    monkeypatch.setattr(case_service.shutil, "rmtree", rmtree)
    second = case_service.create_case(out, created_by="u")
    assert case_service.save_input(out, second["id"], "b.wav", b"x" * 15) == "b.wav"
    assert [p.name for p in (Path(out) / "cases").iterdir() if p.is_dir()] == [second["id"]]


def test_only_so_many_removed_cases_are_remembered_one_by_one(out, monkeypatch):
    monkeypatch.setattr(case_service, "MAX_REMOVED_REMEMBERED", 1)
    first, second, third, fourth = _cases_opened_at(
        out,
        monkeypatch,
        "2026-11-12T08:00:00+00:00",
        "2026-11-12T08:05:00+00:00",
        "2026-11-12T08:10:00+00:00",
        "2026-11-12T08:15:00+00:00",
    )

    case_service.delete_case(out, first)
    case_service.delete_case(out, second)

    # The older of the two is a count only, and the numbers still hold.
    assert case_service._removed(out) == (
        [("2026-11-12T08:00:00+00:00", 1)],
        ["2026-11-12T08:05:00+00:00"],
    )
    assert _numbers(out) == {third: 3, fourth: 4}


def _minute(n: int) -> str:
    return f"2026-11-12T{8 + n // 60:02d}:{n % 60:02d}:00+00:00"


def test_the_numbers_hold_when_more_cases_are_removed_than_are_remembered(out, monkeypatch):
    """A removal kept as a count only counts for the cases opened after it, not
    for the ones that were there before it."""
    monkeypatch.setattr(case_service, "MAX_REMOVED_REMEMBERED", 3)
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 100)
    ids = _cases_opened_at(out, monkeypatch, *(_minute(n) for n in range(12)))
    given = dict(zip(ids, range(1, 13), strict=True))
    assert _numbers(out) == given

    # #1, #4 and #8 stay; the nine others go, oldest first, six past the limit.
    kept = {ids[0]: 1, ids[3]: 4, ids[7]: 8}
    for case_id in ids:
        if case_id not in kept:
            case_service.delete_case(out, case_id)
            left = {i: n for i, n in given.items() if i in _numbers(out)}
            assert _numbers(out) == left

    assert _numbers(out) == kept
    later = _cases_opened_at(out, monkeypatch, _minute(12), _minute(13))
    assert _numbers(out) == {**kept, later[0]: 13, later[1]: 14}

    # An old case removed late is counted where it was opened, not at the end.
    case_service.delete_case(out, ids[3])
    case_service.delete_case(out, later[0])
    (last,) = _cases_opened_at(out, monkeypatch, _minute(14))
    assert _numbers(out) == {ids[0]: 1, ids[7]: 8, later[1]: 14, last: 15}


def test_the_removals_kept_as_counts_do_not_grow_with_the_removals(out, monkeypatch):
    monkeypatch.setattr(case_service, "MAX_REMOVED_REMEMBERED", 2)
    monkeypatch.setattr(case_service, "MAX_CASES_PER_SESSION", 2)
    (first,) = _cases_opened_at(out, monkeypatch, _minute(0))
    for n in range(1, 41):
        (opened,) = _cases_opened_at(out, monkeypatch, _minute(n))
        case_service.delete_case(out, opened)

    # One case is left, so the 38 removals past the limit are one count.
    folded, remembered = case_service._removed(out)
    assert folded == [(_minute(38), 38)] and remembered == [_minute(39), _minute(40)]
    (second,) = _cases_opened_at(out, monkeypatch, _minute(41))
    assert _numbers(out) == {first: 1, second: 42}


def test_a_count_written_before_it_said_which_cases_it_covers_is_still_read(out, monkeypatch):
    first, second = _cases_opened_at(out, monkeypatch, _minute(0), _minute(1))
    (Path(out) / "cases" / "removed.json").write_text(
        json.dumps({"earlier": 5, "opened": []}), encoding="utf-8"
    )

    assert _numbers(out) == {first: 6, second: 7}


def test_a_case_is_not_submitted_without_input(out):
    case = case_service.create_case(out, created_by="u")

    with pytest.raises(case_service.CaseStateError):
        case_service.claim_submission(out, case["id"])


def test_the_input_of_a_running_case_cannot_change(out):
    case = _running_case(out)

    with pytest.raises(case_service.CaseStateError):
        case_service.save_input(out, case["id"], "other.wav", b"x")
    with pytest.raises(case_service.CaseStateError):
        case_service.delete_input(out, case["id"], "report.wav")


# ---------------------------------------------------------------------------
# The run's result
# ---------------------------------------------------------------------------


def test_the_record_is_the_json_whose_keys_are_the_output_fields():
    result = case_service.parse_run_output(_log(), SPEC)

    assert result["record"] == RECORD
    assert result["validation"] == {"hallucination_flags": [], "passed": True}
    assert result["transcript"] == "the spoken report"


def _files_log(*files):
    lines = ["starting", "=== POC OUTPUT BEGIN ==="]
    for name, body in files:
        lines += [f"--- output/{name} ---", body, ""]
    return "\n".join(lines + ["=== POC OUTPUT END ==="])


def test_a_side_file_printed_first_does_not_become_the_record():
    """A review note naming one output field used to win over the record itself."""
    note = {
        "ticket_file": "report_ticket.json",
        "transcript_file": "report_transcript.txt",
        "uncertain_fields": [],
        "decision": None,
        "decision_options": ["approve", "return"],
    }
    log = _files_log(
        ("report_review.json", json.dumps(note)),
        ("report_ticket.json", json.dumps([RECORD])),
    )
    assert case_service.parse_run_output(log, SPEC)["record"] == RECORD


def test_a_grounding_check_that_names_fields_is_never_the_record():
    check = {
        "hallucination_flags": [{"field": "location", "severity": "wrong"}],
        "passed": False,
        "location": "checked",
        "urgency": "checked",
        "reporter": "checked",
    }
    log = _files_log(("a_check.json", json.dumps(check)), ("b_ticket.json", json.dumps(RECORD)))
    result = case_service.parse_run_output(log, SPEC)
    assert result["record"] == RECORD
    assert result["validation"] == check


def test_a_markdown_report_is_the_result_when_no_json_is():
    report = "# Q2 Report\n\nIntro line.\n\n## Summary\nAll good.\n\n## Actions\n- Fix A\n"
    log = _files_log(
        ("report.md", report),
        ("result.json", json.dumps({"title": "Q2 Report", "sources": ["a.csv"], "checks": {}})),
    )
    result = case_service.parse_run_output(log, {"fields": ["executive_summary"]})
    assert result["record"] == {
        "title": "Q2 Report",
        "sections": [
            {"title": "Summary", "text": "All good."},
            {"title": "Actions", "text": "- Fix A"},
        ],
    }
    assert case_service.record_problems(result["record"], {"fields": ["executive_summary"]}) == []


def test_a_markdown_note_without_sections_is_not_a_result():
    log = _files_log(("notes.md", "Run finished.\nSee the logs."))
    assert case_service.parse_run_output(log, SPEC)["record"] is None


def test_a_markdown_only_report_puts_the_case_up_for_review(out):
    case = _running_case(out)
    report = "# Report\n\n## Findings\nOne finding.\n"
    settled = case_service.finish_run(
        out,
        case["id"],
        phase="succeeded",
        log=_files_log(("report.md", report)),
        message=None,
        spec={"fields": ["findings"]},
    )
    assert settled["status"] == "review"
    assert settled["record"]["sections"][0]["title"] == "Findings"


def _cut_log(name="report_ticket.json", size=case_service.OUTPUT_FILE_LIMIT):
    """A result the container cut at its per-file limit: valid JSON up to there."""
    whole = json.dumps({**RECORD, "notes": "n" * size})
    return "\n".join(
        [
            "=== POC OUTPUT BEGIN ===",
            f"--- output/{name} ---",
            whole[:size],
            "=== POC OUTPUT END ===",
        ]
    )


def test_a_result_cut_by_the_containers_limit_is_said_to_be_cut_not_missing():
    result = case_service.parse_run_output(_cut_log(), SPEC)
    assert result["record"] is None
    assert result["truncated"] == ["report_ticket.json"]

    # A JSON the run wrote whole but wrong is still just skipped.
    broken = "\n".join(
        ["=== POC OUTPUT BEGIN ===", "--- output/x.json ---", "{not json", "=== POC OUTPUT END ==="]
    )
    assert case_service.parse_run_output(broken, SPEC)["truncated"] == []


def test_a_cut_result_fails_the_case_with_the_size_as_the_reason(out):
    case = _running_case(out)

    settled = case_service.finish_run(
        out, case["id"], phase="succeeded", log=_cut_log(), message=None, spec=SPEC
    )

    assert settled["status"] == "failed"
    assert "output/report_ticket.json is larger than the 64 KB" in settled["run_message"]


def test_the_containers_limits_are_the_ones_the_parser_knows():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE)
    run = next(
        c for c in manifest["spec"]["template"]["spec"]["containers"] if c["name"] == "poc-run"
    )
    script = " ".join(run["args"])

    assert f"head -c {case_service.OUTPUT_FILE_LIMIT} " in script
    assert f"head -c {case_service.OUTPUT_TOTAL_LIMIT}" in script


def test_a_log_without_the_markers_has_no_result():
    assert case_service.parse_run_output("Traceback ...", SPEC)["record"] is None


def test_a_successful_run_puts_the_case_up_for_review(out):
    case = _running_case(out)

    settled = case_service.finish_run(
        out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC
    )

    assert settled["status"] == "review"
    assert settled["record"] == RECORD


def test_a_run_that_wrote_no_record_fails_the_case_with_a_reason(out):
    case = _running_case(out)

    settled = case_service.finish_run(
        out, case["id"], phase="succeeded", log="no markers", message=None, spec=SPEC
    )

    assert settled["status"] == "failed"
    assert "no result" in settled["run_message"]


_TRACEBACK = """Warning: PyTorch not available. CUDA detection disabled.
Traceback (most recent call last):
  File "/workspace/poc/run_poc.py", line 192, in parse_pages
    m = meta_by_file[pdf.name]
        ~~~~~~~~~~~~^^^^^^^^^^
KeyError: 'employee_travel_policy.pdf'
=== POC OUTPUT BEGIN === r1

=== POC OUTPUT END === r1
"""


def test_the_reason_a_run_failed_is_the_last_exception_line_of_its_log():
    assert case_service.failure_reason(_TRACEBACK) == "KeyError: 'employee_travel_policy.pdf'"
    api_error = "openai.NotFoundError: Error code: 404 - {'error': {'code': 'DeploymentNotFound'}}"
    assert case_service.failure_reason("x\n" + api_error + "\n") == api_error
    assert (
        case_service.failure_reason(
            "import pandas as pd\nModuleNotFoundError: No module named 'pandas'"
        )
        == "ModuleNotFoundError: No module named 'pandas'"
    )


def test_the_reason_is_an_error_line_when_there_is_no_traceback_and_none_otherwise():
    log = "\n".join(
        [
            "Warning: docling missing",
            "ERROR: no PDF documents found in sample_input",
            case_service.OUTPUT_BEGIN,
        ]
    )
    assert case_service.failure_reason(log) == "ERROR: no PDF documents found in sample_input"
    assert case_service.failure_reason("Killed\n") is None
    assert case_service.failure_reason("") is None


def test_a_long_reason_is_cut_and_a_line_after_the_markers_does_not_count():
    long = "ValueError: " + "x" * 500
    reason = case_service.failure_reason(long)
    assert reason.startswith("ValueError: xxx") and reason.endswith("…") and len(reason) <= 240
    assert case_service.failure_reason("ok\n=== POC OUTPUT BEGIN ===\nValueError: echoed") is None


def test_a_failed_run_tells_the_case_what_its_log_said():
    reason = case_service.run_failure_message(
        "failed", _TRACEBACK, "Job has reached the specified backoff limit"
    )
    assert reason == "KeyError: 'employee_travel_policy.pdf'"
    assert case_service.run_failure_message("failed", "Killed", "backoff") == "backoff"
    assert case_service.run_failure_message("failed", "", None) == "the run ended: failed"
    assert case_service.run_failure_message("timeout", _TRACEBACK, "cut off") == "cut off"


def test_a_failed_case_carries_the_reason_from_its_log(out):
    case = _running_case(out)

    settled = case_service.finish_run(
        out, case["id"], phase="failed", log=_TRACEBACK, message="backoff limit", spec=SPEC
    )

    assert settled["status"] == "failed"
    assert settled["run_message"] == "KeyError: 'employee_travel_policy.pdf'"


def test_a_failed_run_can_be_sent_again(out):
    case = _running_case(out)
    case_service.finish_run(
        out, case["id"], phase="timeout", log=None, message="cut off", spec=SPEC
    )

    assert case_service.claim_submission(out, case["id"])["claimed_from"]["status"] == "failed"


# ---------------------------------------------------------------------------
# The review
# ---------------------------------------------------------------------------


def _in_review(out):
    case = _running_case(out)
    return case_service.finish_run(
        out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC
    )


def test_the_reviewer_approves_the_corrected_record(out):
    case = _in_review(out)

    approved = case_service.review(
        out,
        case["id"],
        action="approve",
        role="Supervisor",
        record={**RECORD, "location": "Hall 3, east end"},
        comment="",
        spec=SPEC,
    )

    assert approved["status"] == "approved"
    assert approved["record"]["location"] == "Hall 3, east end"
    assert approved["result"]["record"]["location"] == "Hall 3"  # what the AI wrote is kept
    assert approved["events"][-1]["detail"] == "location"


@pytest.mark.parametrize(
    "change, problem",
    [
        ({"location": ""}, "location is required"),
        ({"urgency": "urgent"}, "urgency must be one of"),
        ({"seen_on": "2026-02-01"}, "seen_on must be DD/MM/YYYY"),
    ],
)
def test_a_record_the_form_would_refuse_is_not_approved(out, change, problem):
    case = _in_review(out)

    with pytest.raises(case_service.CaseStateError, match=problem):
        case_service.review(
            out,
            case["id"],
            action="approve",
            role="Supervisor",
            record={**RECORD, **change},
            comment="",
            spec=SPEC,
        )


def test_a_returned_case_goes_back_for_a_new_round_with_the_comment(out):
    case = _in_review(out)

    returned = case_service.review(
        out,
        case["id"],
        action="return",
        role="Supervisor",
        record=None,
        comment="Which hall?",
        spec=SPEC,
    )

    assert returned["status"] == "returned"
    assert returned["round"] == 2
    assert returned["comment"] == "Which hall?"
    # The input can be changed and the case sent again.
    case_service.save_input(out, case["id"], "report2.wav", b"RIFF")
    assert case_service.claim_submission(out, case["id"])["status"] == "running"


def test_a_case_run_again_goes_back_without_a_reason_and_says_which_it_was(out):
    case = _in_review(out)

    again = case_service.review(
        out, case["id"], action="rerun", role="Supervisor", record=None, comment="", spec=SPEC
    )

    assert (again["status"], again["round"], again["comment"]) == ("returned", 2, "")
    assert again["rerun"] is True
    assert again["events"][-1]["action"] == "rerun"
    # The input can be changed and the case sent again, as after a return.
    case_service.save_input(out, case["id"], "report2.wav", b"RIFF")
    case_service.mark_submitted(out, case["id"], run_id="r2", role="Technician", note="")
    case_service.finish_run(out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC)
    # A reviewer's return after it is a return: told from the action, not the words.
    returned = case_service.review(
        out,
        case["id"],
        action="return",
        role="Supervisor",
        record=None,
        comment="Ajetaan uudelleen.",
        spec=SPEC,
    )
    assert returned["rerun"] is False
    # A case from before the field was kept reads as a return.
    stored = json.loads((Path(out) / "cases" / case["id"] / "case.json").read_text())
    del stored["rerun"]
    (Path(out) / "cases" / case["id"] / "case.json").write_text(json.dumps(stored))
    assert case_service.get_case(out, case["id"])["rerun"] is False


@requires_postgres
def test_a_case_is_run_again_over_the_api_with_no_comment(client, db_session, monkeypatch):
    sid = _session_with_package(client, db_session)
    case = _submitted_case(client, sid, monkeypatch)
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    case_service.finish_run(out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC)

    res = client.post(f"/sessions/{sid}/cases/{case['id']}/review", json={"action": "rerun"})

    assert res.status_code == 200
    assert (res.json()["status"], res.json()["rerun"]) == ("returned", True)
    # A return still owes its reason.
    assert client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={}).status_code == 200
    case_service.finish_run(out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC)
    refused = client.post(f"/sessions/{sid}/cases/{case['id']}/review", json={"action": "return"})
    assert refused.status_code == 409


def test_returning_or_rejecting_needs_a_reason(out):
    case = _in_review(out)

    for action in ("return", "reject"):
        with pytest.raises(case_service.CaseStateError):
            case_service.review(
                out, case["id"], action=action, role="", record=None, comment=" ", spec=SPEC
            )


def test_a_case_not_in_review_cannot_be_approved(out):
    case = case_service.create_case(out, created_by="u")

    with pytest.raises(case_service.CaseStateError):
        case_service.review(
            out, case["id"], action="approve", role="", record=RECORD, comment="", spec=SPEC
        )


# ---------------------------------------------------------------------------
# The process the UI is built from
# ---------------------------------------------------------------------------

BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="P">
    <bpmn:laneSet>
      <bpmn:lane id="L_user" name="Technician">
        <bpmn:flowNodeRef>S</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>T_rec</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="L_ai" name="GenAI">
        <bpmn:flowNodeRef>T_ext</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="L_rev" name="Supervisor">
        <bpmn:flowNodeRef>T_rev</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>G</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>E_ok</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>E_no</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="S"/>
    <bpmn:userTask id="T_rec" name="Record report">
      <bpmn:dataOutputAssociation><bpmn:targetRef>D_audio</bpmn:targetRef></bpmn:dataOutputAssociation>
    </bpmn:userTask>
    <bpmn:serviceTask id="T_ext" name="[A2S] Extract fields"/>
    <bpmn:userTask id="T_rev" name="Review ticket"/>
    <bpmn:exclusiveGateway id="G" name="Approved?"/>
    <bpmn:endEvent id="E_ok"/><bpmn:endEvent id="E_no" name="Rejected"/>
    <bpmn:dataObjectReference id="D_audio" name="Report Audio"/>
    <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="T_rec"/>
    <bpmn:sequenceFlow id="f2" sourceRef="T_rec" targetRef="T_ext"/>
    <bpmn:sequenceFlow id="f3" sourceRef="T_ext" targetRef="T_rev"/>
    <bpmn:sequenceFlow id="f4" sourceRef="T_rev" targetRef="G"/>
    <bpmn:sequenceFlow id="f5" name="Yes" sourceRef="G" targetRef="E_ok"/>
    <bpmn:sequenceFlow id="f6" name="No" sourceRef="G" targetRef="E_no"/>
  </bpmn:process>
</bpmn:definitions>"""


def test_a_bpmn_that_does_not_parse_is_said_so_and_not_a_crash():
    with pytest.raises(case_service.BpmnParseError, match="does not parse"):
        case_service.process_from_bpmn("<bpmn:definitions><bpmn:process>")


def test_the_reviewer_is_the_first_person_after_the_ai_step():
    process = case_service.process_from_bpmn(BPMN)
    assert case_service.reviewer_task(process) == "T_rev"

    def chain(*kinds):
        nodes = [{"id": "S", "kind": "startEvent"}] + [
            {"id": f"T{i}", "kind": k} for i, k in enumerate(kinds)
        ]
        flows = [{"from": a["id"], "to": b["id"], "name": ""} for a, b in zip(nodes, nodes[1:])]
        return {"lanes": [], "nodes": nodes, "flows": flows}

    # Two people give the input, the AI runs, nobody reviews: the old count of
    # user tasks said "review" and the case stuck (#296).
    assert case_service.reviewer_task(chain("userTask", "userTask", "serviceTask")) is None
    assert case_service.reviewer_task(chain("userTask", "serviceTask", "manualTask")) == "T2"
    assert case_service.reviewer_task(chain("userTask", "userTask")) is None
    assert case_service.reviewer_task({"lanes": [], "nodes": [], "flows": []}) is None


def test_a_process_that_cannot_be_walked_is_a_problem_not_no_reviewer():
    """reviewer_task says None for it too; that must not read as "nobody reviews"."""
    nodes = [{"id": "T0", "kind": "userTask"}, {"id": "T1", "kind": "serviceTask"}]
    no_start = {"lanes": [], "nodes": nodes, "flows": [{"from": "T0", "to": "T1", "name": ""}]}
    assert "no start event" in case_service.process_problem(no_start)
    unreachable = {
        "lanes": [],
        "nodes": [{"id": "S", "kind": "startEvent"}, *nodes],
        "flows": [{"from": "T0", "to": "T1", "name": ""}],
    }
    assert "no task can be reached" in case_service.process_problem(unreachable)
    assert case_service.process_problem(case_service.process_from_bpmn(BPMN)) is None


def test_lanes_with_a_user_task_are_roles_and_the_ai_lane_is_not():
    process = case_service.process_from_bpmn(BPMN)

    assert [(lane["name"], lane["human"]) for lane in process["lanes"]] == [
        ("Technician", True),
        ("GenAI", False),
        ("Supervisor", True),
    ]


def test_tasks_keep_their_lane_their_data_and_a_readable_name():
    nodes = {n["id"]: n for n in case_service.process_from_bpmn(BPMN)["nodes"]}

    assert nodes["T_rec"]["lane"] == "L_user"
    assert nodes["T_rec"]["outputs"] == ["Report Audio"]
    assert nodes["T_ext"]["name"] == "Extract fields"  # component code dropped
    assert nodes["G"]["kind"] == "exclusiveGateway"


def test_the_gateway_branches_keep_their_names():
    flows = case_service.process_from_bpmn(BPMN)["flows"]

    assert {f["name"] for f in flows if f["from"] == "G"} == {"Yes", "No"}


# ---------------------------------------------------------------------------
# The sandbox run of a case
# ---------------------------------------------------------------------------

CASE = "3f1c2a4e-5b6d-4e7f-8a9b-0c1d2e3f4a5b"


def _fetch_command(manifest):
    return manifest["spec"]["template"]["spec"]["initContainers"][0]["command"][-1]


def test_a_case_run_fetches_the_package_with_that_cases_input():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE, case_id=CASE)

    assert f'/sessions/{SESSION}/poc?case={CASE}"' in _fetch_command(manifest)
    assert manifest["metadata"]["labels"][CASE_LABEL] == CASE
    assert manifest["spec"]["template"]["metadata"]["labels"][CASE_LABEL] == CASE
    # A case run is its own kind, so it never opens the deployable download.
    assert manifest["metadata"]["labels"][RUN_KIND_LABEL] == CASE_KIND
    assert manifest["spec"]["template"]["metadata"]["labels"][RUN_KIND_LABEL] == CASE_KIND


def test_a_plain_run_fetches_the_package_as_before():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE)

    assert "?case=" not in _fetch_command(manifest)
    assert CASE_LABEL not in manifest["metadata"]["labels"]
    assert RUN_KIND_LABEL not in manifest["metadata"]["labels"]


def test_a_case_run_keeps_the_rest_of_the_reviewed_job():
    plain = render_job_manifest(SESSION, "run-1", IMAGE)
    case = render_job_manifest(SESSION, "run-1", IMAGE, case_id=CASE)

    assert (
        case["spec"]["template"]["spec"]["containers"]
        == plain["spec"]["template"]["spec"]["containers"]
    )
    assert case["spec"]["activeDeadlineSeconds"] == plain["spec"]["activeDeadlineSeconds"]


def test_a_case_id_that_could_inject_into_the_fetch_is_refused():
    with pytest.raises(ValueError):
        render_job_manifest(SESSION, "run-1", IMAGE, case_id='x" ; rm -rf / #')


def test_the_whole_log_of_a_finished_run_is_read_from_its_pod():
    class Core:
        def list_namespaced_pod(self, namespace, label_selector):
            return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name="pod-1"))])

        def read_namespaced_pod_log(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(data=_log().encode())

    core = Core()
    runner = SandboxRunner(namespace="ns", image=IMAGE, batch=object(), core=core)

    log = runner.read_log("run-1")

    assert "POC OUTPUT BEGIN" in log
    assert case_service.parse_run_output(log, SPEC)["record"] == RECORD
    # The client's own decoding escaped the newlines, so the raw body is read.
    assert core.kwargs["_preload_content"] is False
    assert "follow" not in core.kwargs


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


# The agent's draft the package sessions are built from: the same process as BPMN.
PACKAGE_DRAFT = {
    "use_case": {"id": "fault_reports", "name": "Fault reports", "description": "d", "domain": "d"},
    "target_output_spec": SPEC,
    "business_spec": {"intended_users": ["technician"], "reviewers": ["supervisor"]},
    "artifacts": {
        "report_audio": {"type": "audio", "source": "user_upload", "optional": False},
        "ticket": {
            "type": "json",
            "source": "generated",
            "optional": False,
            "produced_by": "extract",
        },
    },
    "workflow": {
        "steps": [
            {
                "id": "record",
                "name": "Record report",
                "type": "user_task",
                "outputs": ["report_audio"],
            },
            {
                "id": "extract",
                "name": "Extract fields",
                "type": "automated_task",
                "component": "AudioToStructuredData",
                "inputs": ["report_audio"],
                "outputs": ["ticket"],
            },
            {"id": "review", "name": "Review ticket", "type": "human_review", "inputs": ["ticket"]},
        ]
    },
    "business_process": {
        "participants": [
            {"id": "technician", "name": "Technician", "default_lane_for": ["user_task"]},
            {"id": "supervisor", "name": "Supervisor", "default_lane_for": ["human_review"]},
            {"id": "genai", "name": "GenAI", "kind": "system"},
        ]
    },
}


def _session_with_package(client, db_session, gate_2="approved"):
    created = client.post("/sessions", json={"user_id": "case-user", "title": "Cases"}).json()
    write_gate_artifacts(created["output_dir"], "gate_2")
    client.patch(f"/sessions/{created['id']}", json={"gate_statuses": {"gate_2": gate_2}})
    out = session_service.get_session(db_session, uuid.UUID(created["id"])).output_dir
    poc = os.path.join(out, "poc")
    os.makedirs(os.path.join(poc, "sample_input"), exist_ok=True)
    os.makedirs(os.path.join(poc, "output"), exist_ok=True)
    with open(os.path.join(poc, "run_poc.py"), "w", encoding="utf-8") as fh:
        fh.write("from gaik.software_components.extractor import Extractor\n")
    for name, text in (
        ("requirements.txt", "gaik\n"),
        ("README.md", "# PoC\n"),
        ("sample_input/developer.wav", "dev"),
        ("output/old.json", "{}"),
    ):
        with open(os.path.join(poc, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(out, "use_case.blueprint.json"), "w", encoding="utf-8") as fh:
        json.dump(PACKAGE_DRAFT, fh)
    content = artifact_sync.blueprint_from_draft(PACKAGE_DRAFT).model_dump()
    client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})
    # The agent's own diagram, with other roles: not what the cases are built from.
    with open(os.path.join(out, "workflow.bpmn"), "w", encoding="utf-8") as fh:
        fh.write(BPMN.replace('name="Supervisor"', 'name="Agent-only reviewer"'))
    return created["id"]


def _diagram(monkeypatch, xml: str) -> None:
    """The diagram the user sees, as the cases read it."""
    from wizard_api.services import bpmn_service

    monkeypatch.setattr(bpmn_service, "generate_bpmn_xml", lambda *a, **k: xml)


@requires_postgres
def test_the_model_carries_the_process_and_the_output_fields(client, db_session):
    sid = _session_with_package(client, db_session)

    model = client.get(f"/sessions/{sid}/cases/model").json()

    assert model["title"] == "Fault reports"
    assert model["spec"]["fields"] == SPEC["fields"]
    # What an upload accepts, as the upload itself decides it.
    assert model["accepted_inputs"] == input_content.accepted(
        input_content.allowed_kinds(PACKAGE_DRAFT)
    )
    assert [lane["name"] for lane in model["process"]["lanes"]] == [
        "Technician",
        "GenAI",
        "Supervisor",
    ]


@requires_postgres
def test_the_model_is_the_diagram_the_user_sees_not_the_agents_own(client, db_session):
    sid = _session_with_package(client, db_session)

    process = client.get(f"/sessions/{sid}/cases/model").json()["process"]
    shown = case_service.process_from_bpmn(client.get(f"/sessions/{sid}/bpmn").text)

    assert process == shown
    assert "Agent-only reviewer" not in [lane["name"] for lane in process["lanes"]]


@requires_postgres
def test_without_a_diagram_the_model_falls_back_to_the_agents_own(client, db_session, monkeypatch):
    from wizard_api.services import bpmn_service

    sid = _session_with_package(client, db_session)

    def boom(*args, **kwargs):
        raise bpmn_service.BpmnGenerationError("no generator")

    monkeypatch.setattr(bpmn_service, "generate_bpmn_xml", boom)

    lanes = client.get(f"/sessions/{sid}/cases/model").json()["process"]["lanes"]
    assert "Agent-only reviewer" in [lane["name"] for lane in lanes]


@requires_postgres
def test_the_model_names_the_reviewer(client, db_session):
    sid = _session_with_package(client, db_session)

    assert client.get(f"/sessions/{sid}/cases/model").json()["reviewer"] == "Activity_review"


@requires_postgres
def test_a_running_case_is_settled_even_when_the_bpmn_no_longer_parses(
    client, db_session, monkeypatch
):
    from wizard_api.services.sandbox_runner import RunStatus, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    monkeypatch.setattr(SandboxRunner, "create_run", lambda self, *a, **k: "run-9")
    assert client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={}).status_code == 200
    # The diagram came out broken mid-run (#295).
    _diagram(monkeypatch, "<bpmn:definitions><bpmn:process>")
    monkeypatch.setattr(
        SandboxRunner,
        "status",
        lambda self, run_id, **k: RunStatus(run_id, "succeeded", exit_code=0),
    )
    monkeypatch.setattr(SandboxRunner, "read_log", lambda self, run_id: _log())

    removed: list[str] = []
    monkeypatch.setattr(SandboxRunner, "delete_run", lambda self, run_id: removed.append(run_id))

    settled = client.get(f"/sessions/{sid}/cases/{case['id']}")

    assert settled.status_code == 200
    # The case holds the result now, so the Job and its log are removed.
    assert removed == ["run-9"]
    # Nobody can be named from a broken diagram, so someone reviews.
    assert settled.json()["status"] == "review"
    assert settled.json()["record"] == RECORD
    model = client.get(f"/sessions/{sid}/cases/model")
    assert model.status_code == 409 and model.json()["detail"]["error"] == "bpmn_invalid"
    assert "does not parse" in model.json()["detail"]["message"]


@requires_postgres
def test_a_run_under_a_process_without_a_start_event_goes_to_review(
    client, db_session, monkeypatch
):
    from wizard_api.services.sandbox_runner import RunStatus, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    monkeypatch.setattr(SandboxRunner, "create_run", lambda self, *a, **k: "run-9")
    assert client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={}).status_code == 200
    # Well-formed, but with no start event nothing can be walked or named.
    _diagram(
        monkeypatch,
        re.sub(
            r"<bpmn:startEvent[^>]*/>|<bpmn:startEvent.*?</bpmn:startEvent>",
            "",
            BPMN,
            flags=re.S,
        ),
    )
    monkeypatch.setattr(
        SandboxRunner,
        "status",
        lambda self, run_id, **k: RunStatus(run_id, "succeeded", exit_code=0),
    )
    monkeypatch.setattr(SandboxRunner, "read_log", lambda self, run_id: _log())

    settled = client.get(f"/sessions/{sid}/cases/{case['id']}")

    assert settled.json()["status"] == "review"
    model = client.get(f"/sessions/{sid}/cases/model")
    assert model.status_code == 409 and "no start event" in model.json()["detail"]["message"]


@requires_postgres
def test_the_package_of_a_case_run_carries_only_that_cases_input(client, db_session):
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )

    zipped = client.get(f"/sessions/{sid}/poc", params={"case": case["id"]})

    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert "poc/sample_input/report.wav" in names
    assert "poc/sample_input/developer.wav" not in names
    assert "poc/output/old.json" not in names
    assert "poc/run_poc.py" in names


@requires_postgres
def test_submitting_starts_a_sandbox_run_of_the_case(client, db_session, monkeypatch):
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    started = {}

    def create_run(self, session_id, *, run_id=None, kind=None, case_id=None, user_id=None):
        started.update(session_id=session_id, case_id=case_id, user_id=user_id)
        return "run-9"

    monkeypatch.setattr(SandboxRunner, "create_run", create_run)

    res = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={"role": "Technician"})

    assert res.status_code == 200
    assert res.json()["status"] == "running"
    assert started["session_id"] == sid and started["case_id"] == case["id"]
    assert started["user_id"]  # the run fetches the package as the session's owner


@requires_postgres
def test_a_submit_whose_run_cannot_start_gives_the_case_back(client, db_session, monkeypatch):
    from wizard_api.services.sandbox_runner import SandboxNotConfiguredError, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )

    def no_sandbox(self, *a, **k):
        raise SandboxNotConfiguredError("no sandbox here")

    monkeypatch.setattr(SandboxRunner, "create_run", no_sandbox)
    refused = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={})
    assert refused.status_code == 503
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").json()["status"] == "draft"

    # A case taken by one submit is refused to another until its run exists.
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    case_service.claim_submission(out, case["id"])
    monkeypatch.setattr(SandboxRunner, "create_run", lambda self, *a, **k: "run-9")
    second = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={})
    assert second.status_code == 409
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").json()["status"] == "running"


@requires_postgres
def test_a_submit_the_sandbox_has_no_room_for_gives_the_case_back(client, db_session, monkeypatch):
    from wizard_api.services.sandbox_runner import RunLimitError, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )

    def full(self, *a, **k):
        raise RunLimitError("you already have 2 runs going")

    monkeypatch.setattr(SandboxRunner, "create_run", full)
    refused = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={})

    assert refused.status_code == 429
    assert refused.json()["detail"]["error"] == "sandbox_busy"
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").json()["status"] == "draft"


@requires_postgres
def test_a_job_made_after_its_claim_went_stale_is_removed(client, db_session, monkeypatch):
    """The claim was given back while the Job was being made: that Job must not run."""
    from wizard_api.services.sandbox_runner import SandboxRunner

    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    deleted = []

    def slow_create(self, session_id, *, run_id=None, kind=None, case_id=None, user_id=None):
        # Meanwhile the claim goes stale and another submit takes the case.
        case_service.release_submission(out, case_id)
        case_service.claim_submission(out, case_id)
        case_service.mark_submitted(out, case_id, run_id="run-other", role="x", note="")
        return run_id

    monkeypatch.setattr(SandboxRunner, "create_run", slow_create)
    monkeypatch.setattr(SandboxRunner, "delete_run", lambda self, rid: deleted.append(rid))

    res = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={})

    assert res.status_code == 409
    assert len(deleted) == 1 and deleted[0] != "run-other"
    assert case_service.get_case(out, case["id"])["run_id"] == "run-other"


@requires_postgres
def test_a_second_file_of_the_same_name_is_a_conflict(client, db_session):
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    first = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    again = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )

    assert first.status_code == 201
    assert again.status_code == 409
    assert again.json()["detail"]["error"] == "input_exists"
    assert "already in the case" in again.json()["detail"]["message"]


@requires_postgres
def test_an_upload_over_the_limit_is_stopped_at_the_limit_not_read_whole(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(poc_service, "MAX_INPUT_BYTES", 16)
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()

    too_big = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("big.wav", b"x" * 17, "audio/wav")},
    )
    fits = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("ok.wav", b"RIFF\x08\x00\x00\x00WAVEdata", "audio/wav")},
    )

    assert too_big.status_code == 413 and "larger than 0 MB" in too_big.json()["detail"]["message"]
    assert fits.status_code == 201
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").json()["inputs"] == [
        {"name": "ok.wav", "bytes": 16, "task": None}
    ]


@requires_postgres
def test_a_case_of_another_session_is_not_found(client, db_session):
    sid = _session_with_package(client, db_session)

    assert client.get(f"/sessions/{sid}/cases/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/sessions/{sid}/poc", params={"case": str(uuid.uuid4())}).status_code == 404


@requires_postgres
def test_a_waiting_case_is_removed_over_the_api_and_a_sent_one_is_not(
    client, db_session, monkeypatch
):
    sid = _session_with_package(client, db_session)
    waiting = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{waiting['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    sent = _submitted_case(client, sid, monkeypatch)

    assert client.delete(f"/sessions/{sid}/cases/{waiting['id']}").status_code == 204
    refused = client.delete(f"/sessions/{sid}/cases/{sent['id']}")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "case_state"
    assert "only a case still waiting" in refused.json()["detail"]["message"]
    assert client.get(f"/sessions/{sid}/cases/{waiting['id']}").status_code == 404
    # The one that was sent is still there, under the number it had.
    listed = client.get(f"/sessions/{sid}/cases").json()["cases"]
    assert [(c["id"], c["number"]) for c in listed] == [(sent["id"], 2)]
    # Removed once: a second request, or one for a case that never was, finds none.
    assert client.delete(f"/sessions/{sid}/cases/{waiting['id']}").status_code == 404
    assert client.delete(f"/sessions/{sid}/cases/{uuid.uuid4()}").status_code == 404
    assert client.delete(f"/sessions/{sid}/cases/not-a-case").status_code == 404


@requires_postgres
def test_a_case_is_removed_only_through_its_own_session(client, db_session):
    sid = _session_with_package(client, db_session)
    other = client.post("/sessions", json={"user_id": "case-user", "title": "Other"}).json()
    case = client.post(f"/sessions/{sid}/cases").json()

    assert client.delete(f"/sessions/{other['id']}/cases/{case['id']}").status_code == 404
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").status_code == 200


@requires_postgres
def test_a_request_for_a_case_removed_on_its_way_is_not_found(client, db_session, monkeypatch):
    """The case was there when the route looked and gone when the service took its lock."""
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    step = case_service.complete_step

    def removed_first(output_dir, case_id, **kwargs):
        case_service.delete_case(output_dir, case_id)
        return step(output_dir, case_id, **kwargs)

    monkeypatch.setattr(case_service, "complete_step", removed_first)

    res = client.post(f"/sessions/{sid}/cases/{case['id']}/step", json={"task": "T_report"})

    assert res.status_code == 404
    assert res.json()["detail"]["message"] == "case not found"


# ---------------------------------------------------------------------------
# A document result (a generated report)
# ---------------------------------------------------------------------------

REPORT = {
    "status": "DRAFT",
    "title": "Quarterly report",
    "sections": [
        {"id": "summary", "title": "Summary", "text": "Deliveries were on time. [kpis.xlsx]"},
        {"id": "actions", "title": "Actions", "text": "| Action | Owner |"},
    ],
}


def _report_log():
    return "\n".join(
        [
            "=== POC OUTPUT BEGIN ===",
            "--- output/result.json ---",
            json.dumps(REPORT),
            "--- output/report_draft.md ---",
            "# Quarterly report",
            "=== POC OUTPUT END ===",
        ]
    )


def test_a_report_made_of_sections_is_the_result_even_without_field_names():
    result = case_service.parse_run_output(_report_log(), {"fields": ["executive_summary"]})

    assert result["record"] == REPORT
    assert result["document"] == "# Quarterly report"


def test_a_report_is_approved_on_its_sections_not_on_the_field_list(out):
    spec = {"fields": ["executive_summary"], "required_fields": ["executive_summary"]}
    case = _running_case(out)
    case_service.finish_run(
        out, case["id"], phase="succeeded", log=_report_log(), message=None, spec=spec
    )

    edited = {
        **REPORT,
        "sections": [{**REPORT["sections"][0], "text": "Edited."}, REPORT["sections"][1]],
    }
    approved = case_service.review(
        out, case["id"], action="approve", role="Reviewer", record=edited, comment="", spec=spec
    )

    assert approved["status"] == "approved"
    assert approved["record"]["sections"][0]["text"] == "Edited."


def test_a_report_with_an_emptied_section_is_not_approved():
    emptied = {**REPORT, "sections": [{**REPORT["sections"][0], "text": " "}]}

    assert case_service.record_problems(emptied, None) == ["section Summary is empty"]


# ---------------------------------------------------------------------------
# Answers to several questions, and a process with no reviewer
# ---------------------------------------------------------------------------

QA_SPEC = {
    "fields": ["query_id", "answer", "access_decision"],
    "required_fields": ["query_id", "answer"],
    "allowed_values": {"access_decision": ["allowed", "denied"]},
}
ANSWERS = [
    {"query_id": "Q1", "answer": "Forty.", "access_decision": "allowed"},
    {"query_id": "Q2", "answer": "Not for this role.", "access_decision": "denied"},
]


def _answers_log():
    return "\n".join(
        [
            "=== POC OUTPUT BEGIN ===",
            "--- output/checks.json ---",
            json.dumps({"records": 2}),
            "--- output/result.json ---",
            json.dumps(ANSWERS),
            "=== POC OUTPUT END ===",
        ]
    )


def test_several_records_stay_a_list():
    assert case_service.parse_run_output(_answers_log(), QA_SPEC)["record"] == ANSWERS


def test_without_a_reviewer_the_result_completes_the_case(out):
    case = _running_case(out)

    done = case_service.finish_run(
        out,
        case["id"],
        phase="succeeded",
        log=_answers_log(),
        message=None,
        spec=QA_SPEC,
        review_needed=False,
    )

    assert done["status"] == "completed"
    assert done["record"] == ANSWERS


def test_each_record_of_a_list_is_checked():
    broken = [ANSWERS[0], {**ANSWERS[1], "access_decision": "maybe"}]

    assert case_service.record_problems(broken, QA_SPEC) == [
        "#2: access_decision must be one of allowed, denied"
    ]


def test_an_approved_record_that_carries_its_review_status_says_so(out):
    spec = {
        **SPEC,
        "fields": [*SPEC["fields"], "review_status"],
        "allowed_values": {
            **SPEC["allowed_values"],
            "review_status": ["pending review", "approved", "returned"],
        },
    }
    case = _running_case(out)
    case_service.finish_run(
        out,
        case["id"],
        phase="succeeded",
        log=_log(record={**RECORD, "review_status": "pending review"}),
        message=None,
        spec=spec,
    )

    approved = case_service.review(
        out, case["id"], action="approve", role="Reviewer", record=None, comment="", spec=spec
    )

    assert approved["record"]["review_status"] == "approved"


def test_a_dotted_field_is_a_column_checked_on_every_row():
    spec = {
        "fields": ["po_number", "line_items", "line_item.article_code", "line_item.quantity"],
        "required_fields": ["po_number", "line_items", "line_item.article_code"],
    }
    record = {
        "po_number": "PO-1",
        "line_items": [
            {"article_code": "A-1", "quantity": "2"},
            {"article_code": "", "quantity": "1"},
        ],
    }

    assert case_service.record_problems(record, spec) == ["line_item 2: article_code is required"]


def test_a_report_spec_whose_fields_are_section_objects_reads_as_names():
    spec = {"fields": [{"id": "executive_summary", "title": "Summary"}, "period", {"x": 1}]}

    assert case_service.normalize_spec(spec)["fields"] == ["executive_summary", "period"]
    assert case_service.parse_run_output(_report_log(), spec)["record"] == REPORT


# ---------------------------------------------------------------------------
# Several people giving parts of the input
# ---------------------------------------------------------------------------


def test_each_person_gives_their_part_and_the_last_one_sends_the_case(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "kpis.xlsx", b"x", task="T_kpi")

    with pytest.raises(case_service.CaseStateError):
        case_service.complete_step(out, case["id"], task="T_audit", role="Quality", note="")

    case_service.complete_step(out, case["id"], task="T_kpi", role="Procurement", note="Q2 numbers")
    case_service.save_input(out, case["id"], "audit.pdf", b"y", task="T_audit")
    sent = case_service.mark_submitted(
        out, case["id"], run_id="r1", role="Quality", note="", task="T_audit"
    )

    assert sent["status"] == "running"
    assert sent["steps_done"] == ["T_kpi", "T_audit"]
    assert sent["notes"]["T_kpi"] == "Q2 numbers"
    assert {f["name"]: f["task"] for f in sent["inputs"]} == {
        "audit.pdf": "T_audit",
        "kpis.xlsx": "T_kpi",
    }


def test_a_case_returned_to_a_later_step_keeps_the_earlier_ones_done(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "kpis.xlsx", b"x", task="T_kpi")
    case_service.complete_step(out, case["id"], task="T_kpi", role="Procurement", note="")
    case_service.save_input(out, case["id"], "audit.pdf", b"y", task="T_audit")
    case_service.mark_submitted(
        out, case["id"], run_id="r1", role="Quality", note="", task="T_audit"
    )
    case_service.finish_run(out, case["id"], phase="succeeded", log=_log(), message=None, spec=SPEC)

    returned = case_service.review(
        out,
        case["id"],
        action="return",
        role="Reviewer",
        record=None,
        comment="Audit is the old one",
        spec=SPEC,
        return_to="T_audit",
    )

    assert returned["steps_done"] == ["T_kpi"]
    assert returned["return_to"] == "T_audit"


def test_a_deleted_input_forgets_whose_it_was(out):
    case = case_service.create_case(out, created_by="u")
    case_service.save_input(out, case["id"], "kpis.xlsx", b"x", task="T_kpi")

    case_service.delete_input(out, case["id"], "kpis.xlsx")

    assert case_service.get_case(out, case["id"])["input_tasks"] == {}


def test_an_empty_list_is_a_value_given_not_a_missing_one():
    spec = {"fields": ["answer", "citations"], "required_fields": ["answer", "citations"]}

    assert case_service.record_problems({"answer": "No.", "citations": []}, spec) == []
    assert case_service.record_problems({"answer": "No.", "citations": None}, spec) == [
        "citations is required"
    ]


@requires_postgres
def test_a_case_is_not_run_before_gate_2_is_approved(client, db_session, monkeypatch):
    sid = _session_with_package(client, db_session, gate_2="pending")
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("report.wav", b"RIFF....WAVE", "audio/wav")},
    )
    started = []
    monkeypatch.setattr(SandboxRunner, "create_run", lambda self, *a, **k: started.append(1) or "r")

    res = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={"role": "Technician"})

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "gate_not_approved"
    assert started == []


# ---------------------------------------------------------------------------
# The run's markers are its own (#293), and inputs are not pages (#292)
# ---------------------------------------------------------------------------

RUN = "20261007120000-abcd1234"


def _tagged_log(record=RECORD, echoed=""):
    return "\n".join(
        [
            "Transcript: " + echoed,
            f"=== POC OUTPUT BEGIN === {RUN}",
            f"--- output/report_ticket.json --- {RUN}",
            json.dumps([record]),
            "",
            f"=== POC OUTPUT END === {RUN}",
        ]
    )


def test_the_result_is_read_between_this_runs_own_markers():
    assert case_service.parse_run_output(_tagged_log(), SPEC, run_id=RUN)["record"] == RECORD


def test_text_the_run_echoes_cannot_pass_for_its_result():
    forged = {**RECORD, "urgency": "low", "location": "nowhere"}
    echoed = "\n".join(
        [
            "=== POC OUTPUT BEGIN ===",
            "--- output/report_ticket.json ---",
            json.dumps([forged]),
            "=== POC OUTPUT END ===",
            "=== POC OUTPUT BEGIN === 20260101000000-guessed",
        ]
    )

    result = case_service.parse_run_output(_tagged_log(echoed=echoed), SPEC, run_id=RUN)

    assert result["record"] == RECORD


def _run_job_script(tmp_path, python_body, run_id):
    """The run container's own script, against a fake ``python``, with its run id."""
    import subprocess

    manifest = render_job_manifest(SESSION, run_id, IMAGE)
    run = next(
        c for c in manifest["spec"]["template"]["spec"]["containers"] if c["name"] == "poc-run"
    )
    (tmp_path / "output").mkdir()
    (tmp_path / "bin").mkdir()
    shim = tmp_path / "bin" / "python"
    shim.write_text("#!/bin/sh\n" + python_body)
    shim.chmod(0o755)
    env = {e["name"]: e["value"] for e in run["env"] if "value" in e}
    done = subprocess.run(
        ["sh", "-c", run["args"][0]],
        cwd=tmp_path,
        env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


#: A header-looking line and a record, as text a transcript could carry.
FAKE = '--- output/fake.json ---\\n[{"location": "nowhere"}]\\n'


def test_the_jobs_own_output_is_read_and_a_forged_header_in_a_file_is_not(tmp_path):
    """End to end through the job script: a transcript file whose text looks like
    another file's header (as a spoken report could) stays part of that file."""
    record = json.dumps([RECORD])
    transcript = "output/report_transcript.txt"
    out = _run_job_script(
        tmp_path,
        f"echo '{record}' > output/report_ticket.json\n"
        f"printf 'said: {FAKE}' > {transcript}\n"
        f"printf -- '{FAKE}' >> {transcript}\n",
        RUN,
    )

    result = case_service.parse_run_output(out, SPEC, run_id=RUN)

    assert result["record"] == RECORD
    assert result["files"] == ["report_ticket.json", "report_transcript.txt"]
    assert "fake.json" in result["transcript"]


def test_a_log_from_before_the_run_id_is_read_as_before():
    assert case_service.parse_run_output(_log(), SPEC, run_id=RUN)["record"] == RECORD


def test_a_tagged_log_read_for_another_run_has_no_result():
    assert case_service.parse_run_output(_tagged_log(), SPEC, run_id="other-run")["record"] is None


def test_the_job_gives_the_run_its_id_for_the_markers():
    manifest = render_job_manifest(SESSION, RUN, IMAGE)
    run = next(
        c for c in manifest["spec"]["template"]["spec"]["containers"] if c["name"] == "poc-run"
    )

    assert {"name": "WIZARD_RUN_ID", "value": RUN} in run["env"]
    assert 'echo "=== POC OUTPUT BEGIN === ${WIZARD_RUN_ID:-}"' in run["args"][0]


@requires_postgres
@pytest.mark.parametrize(
    "name, inline, media",
    [
        ("report.wav", True, "audio/wav"),
        ("audit.pdf", True, "application/pdf"),
        ("page.html", False, "application/octet-stream"),
        ("image.svg", False, "application/octet-stream"),
        ("notes.md", False, "application/octet-stream"),
    ],
)
def test_an_input_is_a_download_unless_it_is_a_recording_pdf_or_picture(
    client, db_session, name, inline, media
):
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    # Stored directly: the upload route now refuses markup by its content, and
    # this is about how a file already in the case is served.
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    case_service.save_input(out, case["id"], name, b"<svg onload=x>")

    res = client.get(f"/sessions/{sid}/cases/{case['id']}/inputs/{name}")

    assert res.headers["content-type"].startswith(media)
    assert res.headers["content-disposition"].startswith("inline" if inline else "attachment")
    assert res.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------------------
# A failed case run tells its own error (#29)
# ---------------------------------------------------------------------------

_MANIFEST_TRACEBACK = """Traceback (most recent call last):
  File "/workspace/poc/run_poc.py", line 325, in main
    manifest = DocumentManifest.load(manifest_path, search_roots=[base_dir, sample_dir])
ValueError: the manifest has no list of documents under any of ('documents', 'manifest')
"""


def test_the_reason_of_a_failed_run_names_no_path_of_the_sandbox():
    log = (
        "Traceback (most recent call last):\n"
        "FileNotFoundError: [Errno 2] No such file or directory: "
        "'/workspace/poc/sample_input/poc_input/access_manifest.json'\n"
    )
    assert case_service.run_failure_message("failed", log, "backoff") == (
        "FileNotFoundError: [Errno 2] No such file or directory: "
        "'sample_input/poc_input/access_manifest.json'"
    )
    other = "ImportError: cannot import name 'x' from '/usr/lib/python3.12/site-packages/y/z.py'"
    assert case_service.run_failure_message("failed", other, None) == (
        "ImportError: cannot import name 'x' from 'z.py'"
    )
    # A URL is not a path.
    url = "openai.NotFoundError: https://example.invalid/openai/deployments/m not found"
    assert case_service.run_failure_message("failed", url, None) == url


def test_only_the_end_of_a_long_failed_log_is_read_for_its_reason(monkeypatch):
    monkeypatch.setattr(case_service, "FAILURE_LOG_BYTES", 200)
    log = "ValueError: an early warning\n" + "progress line\n" * 100 + "KeyError: 'late'\n"

    tail = case_service.failure_log_tail(log)

    assert len(tail.encode()) <= 200 and tail.endswith("KeyError: 'late'\n")
    assert tail.startswith("progress line")  # cut at a line start
    assert case_service.run_failure_message("failed", log, "backoff") == "KeyError: 'late'"


def _submitted_case(client, sid, monkeypatch, files=(("report.wav", b"RIFF....WAVE"),)):
    from wizard_api.services.sandbox_runner import SandboxRunner

    case = client.post(f"/sessions/{sid}/cases").json()
    for name, data in files:
        client.post(
            f"/sessions/{sid}/cases/{case['id']}/inputs",
            files={"file": (name, data, "application/octet-stream")},
        )
    monkeypatch.setattr(SandboxRunner, "create_run", lambda self, *a, **k: "run-9")
    assert client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={}).status_code == 200
    return case


@requires_postgres
def test_a_failed_case_run_shows_the_error_from_its_log_not_the_jobs_words(
    client, db_session, monkeypatch
):
    from wizard_api.services.sandbox_runner import RunStatus, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = _submitted_case(client, sid, monkeypatch)
    monkeypatch.setattr(
        SandboxRunner,
        "status",
        lambda self, run_id, **k: RunStatus(
            run_id, "failed", exit_code=1, message="Job has reached the specified backoff limit"
        ),
    )
    read = []
    monkeypatch.setattr(
        SandboxRunner, "read_log", lambda self, run_id: read.append(run_id) or _MANIFEST_TRACEBACK
    )

    settled = client.get(f"/sessions/{sid}/cases/{case['id']}").json()

    assert read == ["run-9"]
    assert settled["status"] == "failed"
    assert settled["run_message"] == (
        "ValueError: the manifest has no list of documents under any of ('documents', 'manifest')"
    )
    assert "/workspace" not in json.dumps(settled)


@requires_postgres
def test_a_failed_case_run_whose_log_cannot_be_read_settles_with_a_generic_reason(
    client, db_session, monkeypatch
):
    """With no log, the case still settles; the Job's own words stay in the
    server log and are not shown (errors carry no internal detail)."""
    from wizard_api.services.sandbox_runner import RunStatus, SandboxRunner

    sid = _session_with_package(client, db_session)
    case = _submitted_case(client, sid, monkeypatch)
    monkeypatch.setattr(
        SandboxRunner,
        "status",
        lambda self, run_id, **k: RunStatus(run_id, "failed", exit_code=1, message="backoff"),
    )

    def unreadable(self, run_id):
        raise RuntimeError("the pod log is gone")

    monkeypatch.setattr(SandboxRunner, "read_log", unreadable)

    settled = client.get(f"/sessions/{sid}/cases/{case['id']}").json()

    assert settled["status"] == "failed"
    assert settled["run_message"] == "the run ended: failed"
    assert "backoff" not in settled["run_message"]


# ---------------------------------------------------------------------------
# A case run of a corpus-based package keeps the corpus (#28)
# ---------------------------------------------------------------------------

_ACCESS_MANIFEST = {
    "documents": [
        {"file": "documents/policy.pdf", "allowed_roles": ["employee", "manager"]},
        {"file": "documents/pricing.pdf", "allowed_roles": ["manager"]},
    ]
}
_BUNDLE = {
    "documents_directory": "poc_input/documents",
    "access_manifest": "poc_input/access_manifest.json",
    "query_set": "poc_input/query_set.json",
    "path_resolution": "Resolve all paths relative to this bundle file.",
}


def _write_files(root, files):
    for rel, data in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        with open(path, "wb") as fh:
            fh.write(body)


def _rag_sample_input(root):
    _write_files(
        root,
        {
            "poc_input_bundle.json": _BUNDLE,
            "poc_input/access_manifest.json": _ACCESS_MANIFEST,
            "poc_input/query_set.json": {"queries": [{"role": "employee", "question": "old"}]},
            "poc_input/documents/policy.pdf": b"%PDF-1.4 policy",
            "poc_input/documents/pricing.pdf": b"%PDF-1.4 pricing",
        },
    )


def test_the_corpus_its_manifest_and_bundle_are_package_documents(tmp_path):
    _rag_sample_input(tmp_path)

    kept, slots = case_service.package_documents(tmp_path)

    assert kept == {
        "poc_input_bundle.json",
        "poc_input/access_manifest.json",
        "poc_input/documents/policy.pdf",
        "poc_input/documents/pricing.pdf",
    }
    # The package's own questions are its example input: the case's take their place.
    assert slots == {"query_set.json": "poc_input/query_set.json"}


def test_a_manifest_is_found_by_what_it_names_not_by_its_file_name(tmp_path):
    _write_files(
        tmp_path,
        {
            "catalogue.json": {"files": {"a.pdf": {"classification": "internal"}}},
            "a.pdf": b"%PDF a",
            # Names no file in the package: not a manifest, so not kept.
            "expected.json": {"items": [{"name": "nothing-here.pdf"}]},
            "sample.wav": b"RIFF",
        },
    )

    kept, slots = case_service.package_documents(tmp_path)

    assert kept == {"catalogue.json", "a.pdf"}
    assert slots == {}


def test_a_package_without_a_manifest_keeps_none_of_its_example_inputs(tmp_path):
    # A UC05-shaped bundle names only inputs; the case brings its own.
    _write_files(
        tmp_path,
        {
            "poc_input_bundle.json": {"inputs": {"meeting_audio": "input/meeting.wav"}},
            "input/meeting.wav": b"RIFF",
        },
    )

    assert case_service.package_documents(tmp_path) == (set(), {})


def test_a_manifest_cannot_reach_outside_sample_input(tmp_path):
    sample = tmp_path / "sample_input"
    _write_files(
        tmp_path,
        {
            "secret.txt": b"not for the run",
            "sample_input/m.json": {"documents": [{"file": "../secret.txt"}]},
        },
    )

    assert case_service.package_documents(sample) == (set(), {})


def test_a_case_input_takes_its_slot_and_cannot_overwrite_a_document(tmp_path):
    sample, inputs = tmp_path / "sample_input", tmp_path / "inputs"
    _rag_sample_input(sample)
    _write_files(inputs, {"query_set.json": {"queries": []}, "extra.txt": b"x"})

    placed = case_service.case_package_inputs(sample, inputs)

    by_rel = {rel: src for src, rel in placed}
    assert by_rel["poc_input/query_set.json"] == inputs / "query_set.json"
    assert by_rel["extra.txt"] == inputs / "extra.txt"
    assert by_rel["poc_input/documents/policy.pdf"] == sample / "poc_input/documents/policy.pdf"
    assert len(by_rel) == len(placed)

    _write_files(inputs, {"poc_input_bundle.json": {"documents_directory": "elsewhere"}})
    with pytest.raises(case_service.InputClashError, match="poc_input_bundle.json"):
        case_service.case_package_inputs(sample, inputs)


def _rag_session(client, db_session):
    sid = _session_with_package(client, db_session)
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    _rag_sample_input(os.path.join(out, "poc", "sample_input"))
    return sid


@requires_postgres
def test_the_package_of_a_rag_case_run_keeps_the_corpus_and_the_manifest(client, db_session):
    sid = _rag_session(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    query_set = json.dumps({"queries": [{"role": "manager", "question": "new"}]}).encode()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("query_set.json", query_set, "application/json")},
    )

    zipped = client.get(f"/sessions/{sid}/poc", params={"case": case["id"]})

    assert zipped.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(zipped.content))
    names = archive.namelist()
    for rel in (
        "poc_input_bundle.json",
        "poc_input/access_manifest.json",
        "poc_input/documents/policy.pdf",
        "poc_input/documents/pricing.pdf",
    ):
        assert f"poc/sample_input/{rel}" in names
    # The case's questions, in the place the bundle names, and only once.
    assert names.count("poc/sample_input/poc_input/query_set.json") == 1
    assert archive.read("poc/sample_input/poc_input/query_set.json") == query_set
    # The package's example input and old output stay out, as before.
    assert "poc/sample_input/developer.wav" not in names
    assert "poc/output/old.json" not in names


@requires_postgres
def test_a_case_input_named_like_a_package_document_is_refused_before_the_run(
    client, db_session, monkeypatch
):
    from wizard_api.services.sandbox_runner import SandboxRunner

    sid = _rag_session(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs",
        files={"file": ("poc_input_bundle.json", b"{}", "application/json")},
    )
    started = []
    monkeypatch.setattr(
        SandboxRunner, "create_run", lambda self, *a, **k: started.append(1) or "run-9"
    )

    submitted = client.post(f"/sessions/{sid}/cases/{case['id']}/submit", json={})
    zipped = client.get(f"/sessions/{sid}/poc", params={"case": case["id"]})

    assert (
        submitted.status_code == 409
        and "poc_input_bundle.json" in submitted.json()["detail"]["message"]
    )
    assert started == []
    assert client.get(f"/sessions/{sid}/cases/{case['id']}").json()["status"] == "draft"
    assert zipped.status_code == 409


@requires_postgres
def test_cases_model_lists_compatible_reusable_poc_inputs_and_from_poc_copies_explicitly(
    client, db_session
):
    sid = _session_with_package(client, db_session)
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    sample_dir = Path(out) / "poc" / "sample_input"
    # Replace the dummy placeholder with a valid WAV and add an incompatible JSON file.
    buf = io.BytesIO()
    import wave

    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 40)
    wav_bytes = buf.getvalue()
    (sample_dir / "developer.wav").write_bytes(wav_bytes)
    (sample_dir / "placeholder.json").write_text('{"note": "not audio"}', encoding="utf-8")

    # Restrict contract to audio so placeholder.json is excluded from reusable suggestions.
    draft_path = Path(out) / artifact_sync.DRAFT_BLUEPRINT_FILE
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    draft.setdefault("technical_spec", {})["input_types"] = ["audio"]
    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    model = client.get(f"/sessions/{sid}/cases/model")
    assert model.status_code == 200
    reusable = model.json()["reusable_poc_inputs"]
    assert [item["name"] for item in reusable] == ["developer.wav"]

    case = client.post(f"/sessions/{sid}/cases").json()
    reused = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
        json={"filename": "developer.wav", "task": "T_report"},
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["name"] == "developer.wav"
    assert reused.json()["bytes"] == len(wav_bytes)

    # Incompatible -> 415, duplicate -> 409, missing -> 404.
    incompatible = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
        json={"filename": "placeholder.json", "task": "T_report"},
    )
    assert incompatible.status_code == 415
    duplicate = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
        json={"filename": "developer.wav", "task": "T_report"},
    )
    assert duplicate.status_code == 409
    missing = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
        json={"filename": "missing.wav", "task": "T_report"},
    )
    assert missing.status_code == 404


@requires_postgres
def test_from_poc_rejects_a_step_with_no_types_in_the_session_contract(
    client, db_session, monkeypatch
):
    sid = _session_with_package(client, db_session)
    _diagram(monkeypatch, BPMN)
    out = Path(session_service.get_session(db_session, uuid.UUID(sid)).output_dir)
    (out / artifact_sync.DRAFT_BLUEPRINT_FILE).write_text(
        json.dumps({"technical_spec": {"input_types": ["txt"]}}), encoding="utf-8"
    )
    (out / "poc" / "sample_input" / "report.txt").write_text("Fault report", encoding="utf-8")
    case = client.post(f"/sessions/{sid}/cases").json()
    url = f"/sessions/{sid}/cases/{case['id']}"

    result = client.post(f"{url}/inputs/from-poc", json={"filename": "report.txt", "task": "T_rec"})

    assert result.status_code == 415, result.text
    assert result.json()["detail"]["error"] == "input_type_not_accepted"
    assert client.get(url).json()["inputs"] == []


@requires_postgres
def test_from_poc_refuses_names_that_leave_the_input_directory(client, db_session):
    sid = _session_with_package(client, db_session)
    case = client.post(f"/sessions/{sid}/cases").json()
    for name in ("../run_poc.py", "/etc/passwd", "..\\run_poc.py"):
        res = client.post(
            f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
            json={"filename": name, "task": "T_report"},
        )
        assert res.status_code == 422, (name, res.text)
    # The plain name of a package file outside sample_input/ is not found there.
    res = client.post(
        f"/sessions/{sid}/cases/{case['id']}/inputs/from-poc",
        json={"filename": "run_poc.py", "task": "T_report"},
    )
    assert res.status_code == 404
