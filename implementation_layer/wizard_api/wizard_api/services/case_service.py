"""Cases: the generated solution used as a working process, not only a package.

A case is one pass through the use case's BPMN: someone gives the input (a voice
report, documents), the PoC runs in the sandbox on that input, and a reviewer
approves, returns or rejects what it produced. The UI builds its roles and
screens from the BPMN and its review form from ``target_output_spec``; this
module keeps each case's state and inputs and reads the run's result back.

Cases live on disk beside the session's package (``<output_dir>/cases/<id>/``),
like the package and its sample input do: ``case.json`` for the state and
``inputs/`` for the files. A sandbox run of a case gets the package with that
case's inputs in place of ``sample_input/`` (see the ``case`` parameter of the
package download), so two cases never share or overwrite each other's input.
"""

from __future__ import annotations

import base64
import binascii
import bisect
import fcntl
import itertools
import json
import os
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from wizard_api.services import poc_service

CASES_DIR = "cases"
CASE_FILE = "case.json"
INPUTS_DIR = "inputs"
#: Beside the case folders: when each removed case had been opened, so the
#: cases that are left keep their numbers (``list_cases``).
REMOVED_FILE = "removed.json"
#: A case being removed is first set aside under this prefix, in one rename,
#: and deleted from there: whatever stops the deletion half way, what is left
#: is no longer a case and is swept away later.
REMOVED_PREFIX = ".removed-"
#: How many removed cases are remembered one by one. Past this the oldest are
#: kept as counts only (``_fold``), so the file stays small however often
#: cases are opened and removed.
MAX_REMOVED_REMEMBERED = 1000

#: draft → running → review → approved | rejected, with review → returned →
#: running for a correction, and running → failed when the run did not finish.
#: A process with no reviewer goes running → completed.
STATUSES = (
    "draft",
    "running",
    "review",
    "returned",
    "approved",
    "rejected",
    "failed",
    "completed",
)
EDITABLE = ("draft", "returned", "failed")
#: A case in one of these was never sent: it has no run, no result and no
#: decision, so removing it loses nothing but its input (``delete_case``).
REMOVABLE = ("draft",)
#: A case in one of these is done: it no longer counts against the session's
#: caps, so a long-lived session keeps taking new cases.
CLOSED = ("approved", "rejected", "completed")

#: What one case and one session may hold (#297). An upload is at most
#: ``poc_service.MAX_INPUT_BYTES``; these bound what many of them add up to,
#: on the api's volume and in the package zip, which is built in memory.
MAX_INPUTS_PER_CASE = 20
MAX_CASE_INPUT_BYTES = 200 * 1024 * 1024
#: Defaults for the session-wide limits; a deployment sets its own with
#: ``WIZARD_MAX_CASES_PER_SESSION`` and ``WIZARD_MAX_SESSION_INPUT_MB``. Every
#: session shares the api's volume (5 GiB on Rahti), so the input of one session
#: is bounded as a whole, not only per case: 100 full cases would be 20 GB.
MAX_CASES_PER_SESSION = 100
MAX_SESSION_INPUT_BYTES = 1024 * 1024 * 1024

OUTPUT_BEGIN = "=== POC OUTPUT BEGIN ==="
OUTPUT_END = "=== POC OUTPUT END ==="
FILES_BEGIN = "=== POC FILES BEGIN ==="
FILES_END = "=== POC FILES END ==="
#: What the run container prints of each output file, and of all of them
#: together (``head -c`` in deploy/openshift/sandbox-job.yaml; a test keeps the
#: two in step). A file cut there is not a parse error but a result too large.
OUTPUT_FILE_LIMIT = 64 * 1024
OUTPUT_TOTAL_LIMIT = 256 * 1024


class CaseNotFoundError(LookupError):
    pass


class CaseStateError(ValueError):
    """The action does not fit the case's current status."""


class InputExistsError(poc_service.InputRejectedError):
    """A file of that name is already in the case."""


class InputClashError(ValueError):
    """A case input would take the place of one of the package's own documents."""


#: How long a submission may stay claimed without a run before it is given back.
CLAIM_MAX_AGE = timedelta(seconds=120)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _cases_root(output_dir: str) -> Path:
    return Path(output_dir) / CASES_DIR


def _case_dir(output_dir: str, case_id: str) -> Path:
    try:
        name = str(uuid.UUID(case_id))
    except ValueError as exc:
        raise CaseNotFoundError(case_id) from exc
    # A UUID names no other folder; the check says so where the path is made,
    # for a reader and for the code scanner, now that a case can be removed.
    root = os.path.normpath(_cases_root(output_dir))
    folder = os.path.normpath(os.path.join(root, name))
    if not folder.startswith(root + os.sep):
        raise CaseNotFoundError(case_id)
    return Path(folder)


def _write(output_dir: str, case: dict[str, Any]) -> dict[str, Any]:
    path = _case_dir(output_dir, case["id"]) / CASE_FILE
    tmp = path.with_suffix(".tmp")
    # The input listing is read from disk each time, so it is not stored.
    stored = {k: v for k, v in case.items() if k != "inputs"}
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return case


@contextmanager
def _locked(output_dir: str, case_id: str):
    """One writer per case at a time (#294).

    Every read-modify-write of ``case.json`` runs under this lock: two uploads
    at once lost each other's ``input_tasks`` entry, two submits both passed
    the status check and started two Jobs, two reviews both passed
    ``status == review``. A file lock, so the api's workers share it.
    """
    folder = _case_dir(output_dir, case_id)
    if not folder.is_dir():
        raise CaseNotFoundError(case_id)
    try:
        fh = open(folder / ".lock", "w", encoding="utf-8")
    except FileNotFoundError as exc:
        # Removed between the check and the open (delete_case).
        raise CaseNotFoundError(case_id) from exc
    with fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@contextmanager
def _session_locked(output_dir: str):
    """One writer at a time for what the session's cases add up to.

    Opening a case and adding an input both check a session-wide total, which
    the per-case lock cannot guard: two requests at once both passed the count
    and both went in. Taken before a case's lock, never after it.
    """
    root = _cases_root(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ".lock", "w", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _limit(env: str, default: int, unit: int = 1) -> int:
    """A positive whole number from ``env`` times ``unit``, else ``default``."""
    try:
        value = int(os.getenv(env, "").strip())
    except ValueError:
        return default
    return value * unit if value > 0 else default


def max_cases_per_session() -> int:
    return _limit("WIZARD_MAX_CASES_PER_SESSION", MAX_CASES_PER_SESSION)


def max_session_input_bytes() -> int:
    return _limit("WIZARD_MAX_SESSION_INPUT_MB", MAX_SESSION_INPUT_BYTES, 1024 * 1024)


def _open_case_dirs(output_dir: str) -> list[Path]:
    """The folders of the session's cases that are not closed. A folder whose
    ``case.json`` cannot be read yet (a case being opened) counts as open."""
    root = _cases_root(output_dir)
    if not root.is_dir():
        return []
    open_dirs = []
    for folder in root.iterdir():
        # A case's folder is named by its id; one set aside for removal is not.
        if not folder.is_dir() or folder.name.startswith(REMOVED_PREFIX):
            continue
        try:
            status = json.loads((folder / CASE_FILE).read_text(encoding="utf-8")).get("status")
        except (OSError, ValueError):
            status = None
        if status not in CLOSED:
            open_dirs.append(folder)
    return open_dirs


def _session_input_bytes(output_dir: str) -> int:
    return sum(
        p.stat().st_size
        for case in _open_case_dirs(output_dir)
        if (case / INPUTS_DIR).is_dir()
        for p in (case / INPUTS_DIR).iterdir()
        if p.is_file()
    )


def _event(case: dict[str, Any], role: str, action: str, detail: str = "") -> None:
    case["events"].append({"at": _now(), "role": role, "action": action, "detail": detail})


def create_case(output_dir: str, *, created_by: str) -> dict[str, Any]:
    limit = max_cases_per_session()
    with _session_locked(output_dir):
        if len(_open_case_dirs(output_dir)) >= limit:
            raise CaseStateError(
                f"the session already has {limit} open cases; finish one, or remove one that "
                "is still waiting for its input, before opening another"
            )
        _sweep_removed(output_dir)
        case_id = str(uuid.uuid4())
        (_case_dir(output_dir, case_id) / INPUTS_DIR).mkdir(parents=True)
    case = {
        "id": case_id,
        "created_at": _now(),
        "created_by": created_by,
        "status": "draft",
        "round": 1,
        "note": "",
        "comment": "",
        "run_id": None,
        "run_message": None,
        "result": None,
        "record": None,
        "events": [],
        # Several people may give parts of the input, each in their own user
        # task: which tasks are done, which task each file came from, what
        # each one wrote, and where a returned case goes back to.
        "steps_done": [],
        "input_tasks": {},
        "notes": {},
        "return_to": None,
        # Whether it came back to its input to be run again (review "rerun").
        "rerun": False,
    }
    return _write(output_dir, case)


def get_case(output_dir: str, case_id: str) -> dict[str, Any]:
    path = _case_dir(output_dir, case_id) / CASE_FILE
    try:
        case = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CaseNotFoundError(case_id) from exc
    for key, default in (
        ("steps_done", []),
        ("input_tasks", {}),
        ("notes", {}),
        ("return_to", None),
        ("rerun", False),
    ):
        case.setdefault(key, default)
    case["inputs"] = [
        {**f, "task": case["input_tasks"].get(f["name"])} for f in list_inputs(output_dir, case_id)
    ]
    return case


def list_cases(output_dir: str) -> list[dict[str, Any]]:
    root = _cases_root(output_dir)
    if not root.is_dir():
        return []
    cases = []
    for entry in root.iterdir():
        try:
            case = get_case(output_dir, entry.name)
        except CaseNotFoundError:
            continue
        cases.append({k: case[k] for k in ("id", "created_at", "status", "round")})
    cases.sort(key=lambda c: c["created_at"])
    # A case's number is its place among every case the session has had, the
    # removed ones included: removing one must not renumber the ones after it.
    # A case is remembered as removed just before it goes, so one that is
    # still listed does not count yet: the numbers hold at every moment of a
    # removal, and after one that did not finish.
    folded, removed = _removed(output_dir)
    listed = {c["created_at"] for c in cases}
    removed = [at for at in removed if at not in listed]
    # A count stands for removed cases opened up to its moment, so it counts
    # only for the cases opened after that: one opened before them keeps the
    # number it was given.
    until = [at for at, _ in folded]
    before = [0, *itertools.accumulate(count for _, count in folded)]
    for place, case in enumerate(cases, start=1):
        opened = case["created_at"]
        case["number"] = (
            place + before[bisect.bisect_left(until, opened)] + bisect.bisect_left(removed, opened)
        )
    return cases[::-1]


def _removed(output_dir: str) -> tuple[list[tuple[str, int]], list[str]]:
    """The removed cases, oldest first: the ones kept as counts only, as
    (when the last of them had been opened, how many), and when each of the
    rest had been opened."""
    try:
        data = json.loads((_cases_root(output_dir) / REMOVED_FILE).read_text(encoding="utf-8"))
        opened = sorted(at for at in data.get("opened") or [] if isinstance(at, str))
        folded = sorted(
            (at, int(count))
            for at, count in data.get("folded") or []
            if isinstance(at, str) and int(count) > 0
        )
        # A file written before a count said which cases it covers: its one
        # count is for every case, as it was read then.
        earlier = int(data.get("earlier") or 0)
        if earlier > 0:
            folded.insert(0, ("", earlier))
    except (OSError, ValueError, AttributeError, TypeError):
        return [], []
    return folded, opened


def _fold(
    folded: list[tuple[str, int]], removed: list[str], kept: list[str]
) -> list[tuple[str, int]]:
    """``folded`` with the removed cases opened at ``removed`` added as counts.

    Two counts become one when no case in ``kept`` (when each case the session
    still has was opened) lies between them: only such a case could tell them
    apart. So there are never more counts than cases left, plus one.
    """
    kept = sorted(kept)
    merged: list[tuple[str, int]] = []
    for at, count in sorted([*folded, *((at, 1) for at in removed)]):
        if merged:
            last_at, last_count = merged[-1]
            # No case opened after the last count's moment and up to this one's.
            if bisect.bisect_right(kept, last_at) == bisect.bisect_right(kept, at):
                merged[-1] = (at, last_count + count)
                continue
        merged.append((at, count))
    return merged


def _opening_times(output_dir: str) -> list[str]:
    """When each case the session still has was opened."""
    times = []
    for folder in _cases_root(output_dir).iterdir():
        if not folder.is_dir() or folder.name.startswith(REMOVED_PREFIX):
            continue
        try:
            at = json.loads((folder / CASE_FILE).read_text(encoding="utf-8")).get("created_at")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(at, str):
            times.append(at)
    return times


def _remember_removed(output_dir: str, created_at: str) -> None:
    folded, opened = _removed(output_dir)
    if created_at in opened:
        return  # a removal tried again
    bisect.insort(opened, created_at)
    over = len(opened) - MAX_REMOVED_REMEMBERED
    if over > 0:
        folded = _fold(folded, opened[:over], _opening_times(output_dir))
        opened = opened[over:]
    path = _cases_root(output_dir) / REMOVED_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"folded": folded, "opened": opened}), encoding="utf-8")
    os.replace(tmp, path)


def delete_case(output_dir: str, case_id: str) -> None:
    """Remove a case that was never sent, with the input given to it so far.

    Only a case still waiting for its input: one that has run or been decided
    on is the record of what was done, and stays. A waiting case counts against
    the session's caps like any open case and nothing else closes it, so a
    session full of abandoned ones could not open another.
    """
    with _session_locked(output_dir), _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        if case["status"] not in REMOVABLE:
            raise CaseStateError(
                f"the case is {case['status']}; only a case still waiting for its input "
                "can be removed"
            )
        folder = _case_dir(output_dir, case_id)
        # Remembered first; it counts only once the case is gone (list_cases).
        _remember_removed(output_dir, case["created_at"])
        # Set aside in one step, then deleted. Deleting file by file in place
        # could stop after ``case.json`` and leave a folder that still held a
        # place in the session but was no case anyone could open or remove.
        aside = folder.with_name(f"{REMOVED_PREFIX}{folder.name}")
        os.rename(folder, aside)
        _sweep_removed(output_dir)


def _sweep_removed(output_dir: str) -> None:
    """Delete what removals set aside, this one's and any an earlier one left."""
    root = _cases_root(output_dir)
    if not root.is_dir():
        return
    for folder in root.iterdir():
        if folder.name.startswith(REMOVED_PREFIX) and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


# -- inputs ---------------------------------------------------------------------


def inputs_dir(output_dir: str, case_id: str) -> Path:
    return _case_dir(output_dir, case_id) / INPUTS_DIR


def list_inputs(output_dir: str, case_id: str) -> list[dict[str, Any]]:
    folder = inputs_dir(output_dir, case_id)
    if not folder.is_dir():
        return []
    return [
        {"name": p.name, "bytes": p.stat().st_size} for p in sorted(folder.iterdir()) if p.is_file()
    ]


def _require_editable(case: dict[str, Any]) -> None:
    if case["status"] not in EDITABLE:
        raise CaseStateError(f"the case is {case['status']}; its input can no longer change")


def save_input(
    output_dir: str, case_id: str, filename: str, data: bytes, *, task: str | None = None
) -> str:
    """Store one input file of a case. Same rules as the package's sample input.

    ``task`` is the user task (BPMN id) whose person gave the file.
    """
    with _session_locked(output_dir), _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        _require_editable(case)
        if len(case["inputs"]) >= MAX_INPUTS_PER_CASE:
            raise poc_service.InputRejectedError(
                f"the case already has {MAX_INPUTS_PER_CASE} input files; remove one first"
            )
        if sum(f["bytes"] for f in case["inputs"]) + len(data) > MAX_CASE_INPUT_BYTES:
            raise poc_service.InputTooLargeError(
                f"the case's input would exceed {MAX_CASE_INPUT_BYTES // (1024 * 1024)} MB in all"
            )
        session_limit = max_session_input_bytes()
        if _session_input_bytes(output_dir) + len(data) > session_limit:
            raise poc_service.InputTooLargeError(
                f"the session's case input would exceed {session_limit // (1024 * 1024)} MB in all"
            )
        name = _save_into(inputs_dir(output_dir, case_id), filename, data)
        if task:
            case["input_tasks"][name] = task[:200]
            _write(output_dir, case)
        return name


def _save_into(folder: Path, filename: str, data: bytes) -> str:
    if len(data) > poc_service.MAX_INPUT_BYTES:
        raise poc_service.InputRejectedError(
            f"the file is larger than {poc_service.MAX_INPUT_BYTES // (1024 * 1024)} MB"
        )
    if not data:
        raise poc_service.InputRejectedError("the file is empty")
    name = poc_service.safe_input_name(filename)
    folder.mkdir(parents=True, exist_ok=True)
    target = (folder / name).resolve()
    if target.parent != folder.resolve():
        raise poc_service.InputRejectedError(f"'{filename}' resolves outside the input directory")
    # Never over another person's file of the same name (#294): the case would
    # keep one of the two and credit it to whoever uploaded last.
    if target.exists():
        raise InputExistsError(f"a file named '{name}' is already in the case; remove it first")
    target.write_bytes(data)
    return name


def input_path(output_dir: str, case_id: str, filename: str) -> Path | None:
    name = poc_service.safe_input_name(filename)
    folder = inputs_dir(output_dir, case_id)
    path = folder / name
    return path if poc_service.regular_file(path, folder) else None


def delete_input(output_dir: str, case_id: str, filename: str) -> bool:
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        _require_editable(case)
        path = input_path(output_dir, case_id, filename)
        if path is None:
            return False
        path.unlink()
        if case["input_tasks"].pop(path.name, None) is not None:
            _write(output_dir, case)
        return True


# -- the workflow ----------------------------------------------------------------


def complete_step(
    output_dir: str, case_id: str, *, task: str, role: str, note: str
) -> dict[str, Any]:
    """One person's part of the input is done; the case waits for the next one."""
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        _require_editable(case)
        task = task.strip()[:200]
        if not task:
            raise CaseStateError("name the task that is done")
        if not any(f.get("task") == task for f in case["inputs"]):
            raise CaseStateError("add this step's input before marking it done")
        if task not in case["steps_done"]:
            case["steps_done"].append(task)
        case["notes"][task] = note.strip()
        _event(case, role, "step", note.strip())
        return _write(output_dir, case)


def _require_submittable(case: dict[str, Any]) -> None:
    _require_editable(case)
    if not case["inputs"]:
        raise CaseStateError("add the input before submitting the case")


def claim_submission(output_dir: str, case_id: str) -> dict[str, Any]:
    """Take the case for a run before the Job exists (#294).

    The case becomes ``running`` with no run yet, so a second submit at the
    same moment is refused instead of starting a second Job. ``mark_submitted``
    completes the claim with the run's id; ``release_submission`` gives the
    case back, with its previous run and message, when no run could be started.
    """
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        _require_submittable(case)
        case.update(
            status="running",
            claimed_from={
                "status": case["status"],
                "run_id": case.get("run_id"),
                "run_message": case.get("run_message"),
            },
            run_id=None,
            run_message=None,
            claimed_at=_now(),
        )
        return _write(output_dir, case)


def release_submission(output_dir: str, case_id: str) -> dict[str, Any]:
    """Give a claimed case back as it was: no run was started for it."""
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        if case["status"] != "running" or case.get("run_id"):
            return case
        before = case.pop("claimed_from", None)
        if isinstance(before, dict):
            case.update(
                status=before.get("status") or "draft",
                run_id=before.get("run_id"),
                run_message=before.get("run_message"),
            )
        else:
            # A claim written before the previous run was kept: status only.
            case["status"] = before or "draft"
        case.pop("claimed_at", None)
        return _write(output_dir, case)


def release_stale_claim(
    output_dir: str, case_id: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """A claim the api never completed (it died between the claim and the Job)
    is given back once it is old enough that no run can still be coming."""
    case = get_case(output_dir, case_id)
    if case["status"] != "running" or case.get("run_id"):
        return case
    try:
        claimed_at = datetime.fromisoformat(case.get("claimed_at") or "")
    except ValueError:
        return release_submission(output_dir, case_id)
    if (now or datetime.now(UTC)) - claimed_at < CLAIM_MAX_AGE:
        return case
    return release_submission(output_dir, case_id)


def mark_submitted(
    output_dir: str,
    case_id: str,
    *,
    run_id: str,
    role: str,
    note: str,
    task: str | None = None,
) -> dict[str, Any]:
    """The run exists: the case is running on it. Completes a claim, or submits
    an editable case outright (the service's own callers and tests)."""
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        if case["status"] == "running" and not case.get("run_id"):
            case.pop("claimed_from", None)
            case.pop("claimed_at", None)
        else:
            _require_submittable(case)
        case.update(status="running", run_id=run_id, run_message=None, note=note.strip())
        if task:
            if task not in case["steps_done"]:
                case["steps_done"].append(task)
            case["notes"][task] = note.strip()
        _event(case, role, "submit", case["note"])
        return _write(output_dir, case)


def finish_run(
    output_dir: str,
    case_id: str,
    *,
    phase: str,
    log: str | None,
    message: str | None,
    spec: dict[str, Any] | None,
    review_needed: bool = True,
) -> dict[str, Any]:
    """Settle a running case from its run: the result for review, or why it failed.

    When the process has no review task (the person who asked reads the answer
    themselves), a result completes the case.
    """
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        if case["status"] != "running":
            return case
        result = (
            parse_run_output(log or "", spec, run_id=case.get("run_id"))
            if phase == "succeeded"
            else None
        )
        if result and result.get("record") is not None:
            case.update(
                status="review" if review_needed else "completed",
                result=result,
                record=result["record"],
                run_message=None,
            )
            _event(case, "ai", "result")
        else:
            if phase == "succeeded" and result and result.get("truncated"):
                cut = ", ".join(f"output/{n}" for n in result["truncated"])
                reason = (
                    f"the result {cut} is larger than the {OUTPUT_FILE_LIMIT // 1024} KB the run "
                    "can hand over, so it was cut and could not be read"
                )
            else:
                reason = (
                    message or "the run finished but wrote no result matching the output fields"
                    if phase == "succeeded"
                    else run_failure_message(phase, log, message)
                )
            case.update(status="failed", run_message=reason)
            _event(case, "ai", "failed", reason)
        return _write(output_dir, case)


def review(
    output_dir: str,
    case_id: str,
    *,
    action: str,
    role: str,
    record: dict[str, Any] | list[dict[str, Any]] | None,
    comment: str,
    spec: dict[str, Any] | None,
    return_to: str | None = None,
) -> dict[str, Any]:
    with _locked(output_dir, case_id):
        case = get_case(output_dir, case_id)
        if case["status"] != "review":
            raise CaseStateError(f"the case is {case['status']}, not waiting for review")
        comment = comment.strip()
        if action == "approve":
            record = record if record is not None else case["record"]
            problems = record_problems(record, spec)
            if problems:
                raise CaseStateError("; ".join(problems))
            record = _mark_approved(record, spec)
            case.update(status="approved", record=record)
            _event(case, role, "approve", _changes(case["result"]["record"], record))
        elif action in ("return", "rerun"):
            # "return" is the reviewer sending the case back, and says why.
            # "rerun" is the person trying the solution choosing to run it
            # again on other input: the same way back, with no reason owed.
            # Which of the two it was is kept on the case, not read from the
            # comment's words.
            if action == "return" and not comment:
                raise CaseStateError("say what needs correcting")
            # Back to the step named, or to the first; the steps after it are redone.
            done = case["steps_done"]
            keep = done[: done.index(return_to)] if return_to in done else []
            case.update(
                status="returned",
                comment=comment,
                rerun=action == "rerun",
                round=case["round"] + 1,
                return_to=return_to,
                steps_done=keep,
            )
            _event(case, role, action, comment)
        elif action == "reject":
            if not comment:
                raise CaseStateError("say why the case is rejected")
            case.update(status="rejected", comment=comment)
            _event(case, role, "reject", comment)
        else:
            raise CaseStateError(f"unknown action {action!r}")
        return _write(output_dir, case)


def _mark_approved(record: Any, spec: dict[str, Any] | None) -> Any:
    """A record that carries its own review status says it was approved, when
    its spec allows that value (a meeting record's ``review_status``)."""
    allowed = ((spec or {}).get("allowed_values") or {}).get("review_status") or []
    if isinstance(record, dict) and "review_status" in record and "approved" in allowed:
        return {**record, "review_status": "approved"}
    return record


def _changes(before: Any, after: Any) -> str:
    if isinstance(before, list) and isinstance(after, list):
        return ", ".join(
            f"#{i + 1}"
            for i, (a, b) in enumerate(zip(before, after, strict=False))
            if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)
        )
    if not isinstance(before, dict) or not isinstance(after, dict):
        return ""
    changed = [
        k
        for k in after
        if json.dumps(after.get(k), sort_keys=True) != json.dumps(before.get(k), sort_keys=True)
    ]
    return ", ".join(changed)


_FORMATS = {
    "DD/MM/YYYY": r"(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/\d{4}",
    "YYYY-MM-DD": r"\d{4}-\d{2}-\d{2}",
    "HH:MM": r"([01]\d|2[0-3]):[0-5]\d",
}


def markdown_document(text: str) -> dict[str, Any] | None:
    """A Markdown report as a document record: its ``#`` title and ``##`` sections.

    None when it has no ``##`` section, so a stray note or README is not taken
    for a report.
    """
    title = None
    sections: list[dict[str, str]] = []
    for line in text.splitlines():
        if line.startswith("# ") and title is None and not sections:
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append({"title": line[3:].strip(), "text": ""})
        elif sections:
            sections[-1]["text"] += line + "\n"
    for section in sections:
        section["text"] = section["text"].strip()
    if not sections:
        return None
    return {"title": title, "sections": sections}


def is_document(record: Any) -> bool:
    """A result made of sections of text (a report), rather than a flat record."""
    sections = record.get("sections") if isinstance(record, dict) else None
    return (
        isinstance(sections, list)
        and bool(sections)
        and all(isinstance(s, dict) and "text" in s for s in sections)
    )


def record_problems(record: Any, spec: dict[str, Any] | None) -> list[str]:
    """What stops a reviewed record from being approved: the same checks the form makes."""
    if isinstance(record, list):
        # One record per item (answers to several questions): each is checked.
        return [
            f"#{i + 1}: {problem}"
            for i, item in enumerate(record)
            for problem in record_problems(item, spec)
        ]
    if not isinstance(record, dict):
        return ["the record is not an object"]
    if is_document(record):
        # A generated document (report sections): reviewed as text, not as fields.
        return [
            f"section {s.get('title') or s.get('id') or i + 1} is empty"
            for i, s in enumerate(record["sections"])
            if not str(s.get("text") or "").strip()
        ]
    if not spec:
        return []
    problems = []
    for field in spec.get("fields") or []:
        if "." in field:
            continue  # a column of a table field, checked per row below
        problem = _value_problem(spec, field, record.get(field))
        if problem:
            problems.append(f"{field} {problem}")
    for field in spec.get("fields") or []:
        if "." not in field:
            continue
        table, column = field.split(".", 1)
        rows = record.get(_table_of(spec, table, record))
        for i, row in enumerate(rows if isinstance(rows, list) else []):
            if isinstance(row, dict):
                problem = _value_problem(spec, field, row.get(column))
                if problem:
                    problems.append(f"{table} {i + 1}: {column} {problem}")
    return problems


def _table_of(spec: dict[str, Any], prefix: str, record: dict[str, Any]) -> str:
    """The list field a dotted field belongs to: ``line_item.x`` → ``line_items``."""
    for name in (prefix, f"{prefix}s", f"{prefix}es"):
        if isinstance(record.get(name), list):
            return name
    return prefix


def _value_problem(spec: dict[str, Any], field: str, value: Any) -> str | None:
    # An empty list is a value given ("no citations" for a refused answer);
    # missing is null or blank text.
    empty = value is None or (isinstance(value, str) and not value.strip())
    if field in (spec.get("required_fields") or []) and empty:
        return "is required"
    if empty or not isinstance(value, str):
        return None
    allowed = (spec.get("allowed_values") or {}).get(field)
    if isinstance(allowed, list) and value not in allowed:
        return f"must be one of {', '.join(allowed)}"
    description = (spec.get("field_descriptions") or {}).get(field) or ""
    for token, pattern in _FORMATS.items():
        if token in description and not re.fullmatch(pattern, value):
            return f"must be {token}"
    return None


def normalize_spec(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    """The output spec with its field list as names.

    The agent writes ``fields`` as names for a record, but as objects for a
    report (``{"id": "executive_summary", "title": …, "instructions": …}``);
    everything downstream reads names.
    """
    if not isinstance(spec, dict):
        return spec
    names = []
    for field in spec.get("fields") or []:
        name = (
            field
            if isinstance(field, str)
            else ((field.get("id") or field.get("name")) if isinstance(field, dict) else None)
        )
        if isinstance(name, str) and name:
            names.append(name)
    return {**spec, "fields": names}


# -- the package a case run gets ------------------------------------------------

#: Where a document manifest keeps its records, and the field of a record that
#: names its file: the keys the scaffolded ``document_manifest.py`` reads.
_MANIFEST_RECORD_KEYS = ("documents", "manifest", "files", "items", "entries")
_MANIFEST_FILE_KEYS = ("file", "file_name", "filename", "path", "document", "name")
#: The bundle files the scaffolded ``input_bundle.py`` looks for.
_BUNDLE_NAMES = ("poc_input_bundle.json", "input_bundle.json", "bundle.json")
#: A manifest or bundle larger than this is not read as one.
_PACKAGE_JSON_LIMIT = 2 * 1024 * 1024


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > _PACKAGE_JSON_LIMIT:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _manifest_names(data: Any) -> list[str]:
    """The file names a document manifest's records give, or [] when it is none."""
    records: list[Any] = []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in _MANIFEST_RECORD_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                records = value
                break
            if isinstance(value, dict):
                records = [{"file": k, **v} for k, v in value.items() if isinstance(v, dict)]
                break
    names = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in _MANIFEST_FILE_KEYS:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip().replace("\\", "/"))
                break
    return names


def _json_strings(node: Any):
    if isinstance(node, dict):
        for value in node.values():
            yield from _json_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _json_strings(value)
    elif isinstance(node, str):
        yield node


def _inside(rel: str, files: set[str]) -> str | None:
    """``rel`` normalised, when it stays inside ``sample_input/`` and is one of ``files``."""
    norm = os.path.normpath(rel)
    if norm.startswith("..") or os.path.isabs(norm):
        return None
    return norm if norm in files else None


def _resolve(name: str, folders: list[str], files: set[str], by_name: dict[str, list[str]]):
    """The package file a manifest or bundle names: against each folder, else by bare name."""
    if not name or "\n" in name or len(name) > 400 or os.path.isabs(name):
        return None
    for folder in folders:
        found = _inside(os.path.join(folder, name), files)
        if found:
            return found
    same = by_name.get(os.path.basename(name), [])
    return same[0] if len(same) == 1 else None


def _dirs_named(name: str, folders: list[str], files: set[str]) -> list[str]:
    """The files under a folder a bundle names (``documents_directory``)."""
    for folder in folders:
        norm = os.path.normpath(os.path.join(folder, name))
        if norm.startswith("..") or os.path.isabs(norm) or norm == ".":
            continue
        under = [f for f in files if f.startswith(norm + os.sep)]
        if under:
            return under
    return []


def package_documents(sample_dir: str | os.PathLike) -> tuple[set[str], dict[str, str]]:
    """The package's own documents a case run keeps, and the places a case input fills.

    A corpus-based PoC (RAG) keeps its documents and their access manifest in
    ``sample_input/``; a case brings only its questions, and a run without the
    corpus failed at once (#28). What counts is read from the package itself,
    not from a list of use cases:

    - a *manifest* is a JSON file whose records name files that are in
      ``sample_input/``; it and every file it names are kept;
    - a *bundle* (``poc_input_bundle.json``) that names a kept file, or a
      folder holding one, is kept too, so the run still finds the manifest
      through it.

    Everything else (sample recordings, a sample query set) is the package's
    example input and is left out, as before. A file a kept bundle names but
    which is not kept is a slot: a case input of that file name takes its place
    (the case's ``query_set.json`` at ``poc_input/query_set.json``).

    Returns the kept files and the slots by file name, both relative to
    ``sample_dir``.
    """
    root = Path(sample_dir)
    if not root.is_dir():
        return set(), {}
    files = set(poc_service.regular_files(root))
    by_name: dict[str, list[str]] = {}
    for rel in sorted(files):
        by_name.setdefault(os.path.basename(rel), []).append(rel)
    bundles = {
        rel: data
        for rel in sorted(files)
        if os.path.basename(rel) in _BUNDLE_NAMES and (data := _read_json(root / rel)) is not None
    }
    bundle_dirs = [os.path.dirname(rel) for rel in bundles]
    kept: set[str] = set()
    for rel in sorted(files):
        if not rel.endswith(".json") or rel in bundles:
            continue
        names = _manifest_names(_read_json(root / rel))
        folders = [os.path.dirname(rel), "", *bundle_dirs]
        documents = {d for n in names if (d := _resolve(n, folders, files, by_name)) and d != rel}
        if documents:
            kept |= {rel, *documents}
    slots: dict[str, str] = {}
    for rel, data in bundles.items():
        folders = [os.path.dirname(rel), ""]
        named: set[str] = set()
        for value in _json_strings(data):
            text = value.strip()
            found = _resolve(text, folders, files, {}) if text else None
            if found:
                named.add(found)
            elif text and len(text) <= 400 and "\n" not in text:
                named |= set(_dirs_named(text, folders, files))
        if named & kept:
            kept.add(rel)
            for other in named - kept:
                slots.setdefault(os.path.basename(other), other)
    return kept, slots


def case_package_inputs(
    sample_dir: str | os.PathLike, inputs: str | os.PathLike
) -> list[tuple[Path, str]]:
    """What a case run's ``sample_input/`` holds: (source file, path under it).

    The package's own documents (``package_documents``) and the case's inputs.
    A case input fills the slot of its name, else lands at the top. An input
    that would land on one of the package's documents is refused with
    ``InputClashError``: the run would read the case's file as the corpus or the
    manifest, and nobody would see why.
    """
    root = Path(sample_dir)
    kept, slots = package_documents(root)
    placed = [(root / rel, rel) for rel in sorted(kept)]
    folder = Path(inputs)
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if not poc_service.regular_file(path, folder):
                continue
            target = slots.get(path.name, path.name)
            if target in kept:
                raise InputClashError(
                    f"the case input {path.name} has the name of one of the package's own "
                    f"documents ({poc_service.SAMPLE_INPUT_DIR}/{target}); rename it"
                )
            placed.append((path, target))
    return placed


# -- reading a run's result ------------------------------------------------------


_EXCEPTION_LINE = re.compile(
    r"^(?:[A-Za-z_][\w.]*\.)?[A-Z]\w*(?:Error|Exception|Interrupt|Exit)\b(?:: .*)?$"
)
_ERROR_LINE = re.compile(r"^(?:ERROR|FATAL|CRITICAL)\b[: ]")
_REASON_CHARS = 240


def failure_reason(log: str) -> str | None:
    """Why the run failed, in one line of its own log, or None when it does not say.

    A failed run ends in a traceback, and the person was left to find its last
    line under the stack (UC03, UC04 on s4). That line is the reason: the last
    exception line before the output markers, else the last ``ERROR:`` line,
    else nothing. Cut to a readable length; the log keeps the rest.
    """
    body = log.split(OUTPUT_BEGIN, 1)[0]
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    for line in reversed(lines):
        if _EXCEPTION_LINE.match(line):
            return _shorten(line)
    for line in reversed(lines):
        if _ERROR_LINE.match(line):
            return _shorten(line)
    return None


def _shorten(line: str) -> str:
    line = line.strip()
    return line if len(line) <= _REASON_CHARS else line[: _REASON_CHARS - 1].rstrip() + "…"


#: How much of a failed run's log is read for its reason: the end, where the
#: traceback is. The same bound as the log kept for the agent (run_context).
FAILURE_LOG_BYTES = 64 * 1024

#: Where the run unpacks the package (sandbox-job.yaml); a path under it is told
#: relative to the package, as the person knows it.
_RUN_ROOTS = ("/workspace/poc/", "/workspace/")
#: Any other absolute path (site-packages, /tmp, the image's own folders). Not
#: one inside a URL: the character before its first slash is not a word
#: character, a dot, a colon or another slash.
_ABSOLUTE_PATH = re.compile(r"(?<![\w.:/~-])/(?:[\w.@+-]+/)+([\w.@+-]*)")


def failure_log_tail(log: str) -> str:
    """The last ``FAILURE_LOG_BYTES`` of a failed run's log, cut at a line start."""
    data = log.encode("utf-8", "replace")
    if len(data) <= FAILURE_LOG_BYTES:
        return log
    tail = data[-FAILURE_LOG_BYTES:].decode("utf-8", "replace")
    newline = tail.find("\n")
    return tail[newline + 1 :] if newline >= 0 else tail


def without_internal_paths(text: str) -> str:
    """``text`` with the sandbox's own paths taken out.

    A path in the package is told relative to it (``sample_input/a.pdf``);
    any other absolute path by its file name only, so the message names the
    file without showing how the runner's image is laid out.
    """
    for root in _RUN_ROOTS:
        text = text.replace(root, "")
    return _ABSOLUTE_PATH.sub(lambda m: m.group(1) or "/", text)


def run_failure_message(phase: str, log: str | None, message: str | None) -> str:
    """What to tell about a run that did not succeed.

    A stopped run says so in the runner's words (its ten-minute limit); a
    failed one says what its log says, before the Job's own words ("reached
    the specified backoff limit"), which name no cause. Only the end of the
    log is read, and the reason carries no path of the sandbox's own.
    """
    if phase == "timeout" and message:
        return message
    reason = failure_reason(failure_log_tail(log or ""))
    if reason:
        return without_internal_paths(reason)
    return message or f"the run ended: {phase}"


def output_files(log: str, run_id: str | None = None) -> dict[str, str]:
    """The files the run printed between the output markers, by name, as printed.

    Each marker line ends with the run's id (#293), and with ``run_id`` only
    those lines count: a PoC that echoes its input (a transcript, a document)
    could otherwise print a marker of its own and pass that text off as the
    result. A log from before the id was added has bare markers and is read
    as it was.
    """
    tag = f" {run_id}" if run_id and f"{OUTPUT_BEGIN} {run_id}" in log else ""
    begin_marker, end_marker = f"{OUTPUT_BEGIN}{tag}\n", f"{OUTPUT_END}{tag}"
    begin = log.find(begin_marker)
    if begin < 0:
        if tag or log.find(OUTPUT_BEGIN) < 0:
            return {}
        begin_marker = OUTPUT_BEGIN
        begin = log.find(begin_marker)
    end = log.find(end_marker, begin + len(begin_marker))
    block = log[begin + len(begin_marker) : end if end > begin else len(log)]
    if not block.startswith("\n"):
        block = "\n" + block
    header = rf"\n--- output/([^\n]+?) ---{re.escape(tag)} *\n"
    parts = re.split(header, block)
    # re.split gives [before, name1, body1, name2, body2, ...].
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def output_downloads(log: str, run_id: str) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    """The files of ``output/`` the run printed base64 for download, and the ones it skipped.

    ``sandbox-job.yaml`` prints every top-level file after the text block, a PDF
    report included, which the text block leaves out. Only marker lines that end
    with ``run_id`` count, as for the text block (#293). Names are base names
    (the script runs ``basename``); anything else is dropped, and so is a file
    whose body does not decode or does not match the size the script announced
    (a log cut short by rotation).
    """
    tag = f" {run_id}"
    begin_marker, end_marker = f"{FILES_BEGIN}{tag}\n", f"\n{FILES_END}{tag}"
    begin = log.find(begin_marker)
    if begin < 0:
        return {}, []
    end = log.find(end_marker, begin)
    block = "\n" + log[begin + len(begin_marker) : end if end > begin else len(log)]
    header = re.compile(rf"\n--- (file|skipped) (.+?) (\d+) ---{re.escape(tag)} *(?=\n|$)")
    files: dict[str, bytes] = {}
    skipped: list[dict[str, Any]] = []
    matches = list(header.finditer(block))
    for i, m in enumerate(matches):
        kind, name, size = m.group(1), m.group(2), int(m.group(3))
        if name in (".", "..") or "/" in name or "\\" in name:
            continue
        if kind == "skipped":
            skipped.append({"name": name, "size": size})
            continue
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        encoded = "".join(block[m.end() : body_end].split())
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(data) == size:
            files[name] = data
    return files, skipped


def parse_run_output(
    log: str,
    spec: dict[str, Any] | None,
    run_id: str | None = None,
    files: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The files the run printed between the output markers, and which is which.

    The run container prints each top-level json/txt/md file of ``output/``
    between two markers (sandbox-job.yaml). The record is the JSON whose keys
    are the output fields; a JSON with ``passed`` is the grounding check; a
    ``*transcript*.txt`` is the transcript. ``output_files`` says which marker
    lines count (#293); a caller that already read them passes them in.
    """
    if files is None:
        files = output_files(log, run_id)
    fields = set((normalize_spec(spec) or {}).get("fields") or [])
    validation = None
    transcript = document = ""
    # (overlap with the output fields, order printed, record) for each JSON that
    # could be the result. The first JSON with any shared key used to win, so a
    # side file printed earlier (a review note naming one field) became the
    # record and the real one could not be approved.
    candidates: list[tuple[int, int, Any]] = []
    truncated: list[str] = []
    printed = sum(len(body.encode("utf-8")) for body in files.values())
    for name, body in files.items():
        body = body.strip()
        if name.endswith(".json"):
            try:
                data = json.loads(body)
            except ValueError:
                # A JSON the run wrote whole does not stop parsing; one cut by
                # the container's limit does (#298). Said so, not "no result".
                size = len(body.encode("utf-8"))
                if size >= OUTPUT_FILE_LIMIT or printed >= OUTPUT_TOTAL_LIMIT:
                    truncated.append(name)
                continue
            first = data[0] if isinstance(data, list) and data else data
            if not isinstance(first, dict):
                continue
            if "passed" in first and "passed" not in fields:
                # A grounding check, never the record, even when it names fields.
                if validation is None:
                    validation = first
                continue
            overlap = len(fields & set(first)) if fields else 0
            if overlap or is_document(first):
                # Several records (one per question) stay a list; one is the record.
                many = isinstance(data, list) and len(data) > 1
                chosen = data if many and all(isinstance(d, dict) for d in data) else first
                candidates.append((overlap, -len(candidates), chosen))
        elif "transcript" in name and name.endswith(".txt"):
            transcript = body
        elif name.endswith(".md") and not document:
            document = body
    record = max(candidates, key=lambda c: (c[0], c[1]))[2] if candidates else None
    if record is None and document:
        # A report written only as Markdown is still the result: read as the
        # same sections a JSON report has, so review and approval work as usual.
        record = markdown_document(document)
    return {
        "record": record,
        "validation": validation,
        "transcript": transcript,
        "document": document,
        "files": sorted(files),
        "truncated": truncated,
    }


# -- what looks wrong in a run's result ------------------------------------------

#: A field that holds where an answer comes from, by its name or one word of it.
_SOURCES_NAMES = frozenset({"source", "citation", "reference", "lähde", "lahde", "viite"})
_SOURCES_WORDS = frozenset(
    {"sources", "citations", "references", "lähteet", "lahteet", "viitteet", "viittaukset"}
)
_NO_SOURCES = (
    r"(?:none\b|no (?:sources|citations|references)\b|n/?a\b|null\b"
    r"|ei (?:ole|lähteitä|lahteita|viitteitä|viitteita)\b|[-–—]\s*$)"
)
#: A value of a sources field that says there are none.
_SAYS_NONE = re.compile(rf"^\W*{_NO_SOURCES}", re.IGNORECASE)
#: A "Sources: …" line inside an answer text; group 1 is what follows the label.
_SOURCES_LINE = re.compile(
    r"^[ \t>*_#-]*(?:sources?|citations?|references?|lähteet|lahteet|viitteet)[*_]*[ \t]*"
    r":[*_]*[ \t]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
# What only a run is given: an extracted value does not speak of these.
_RUN_INPUT_NOUN = (
    r"(?:input|inputs|question|questions|query|queries|context|passage|passages"
    r"|excerpt|excerpts)"
)
# What a source can lack as well: "No attachments were provided" is a correct
# value of a field about an e-mail, not a model without its input.
_SOURCE_NOUN = (
    r"(?:text|content|document|documents|transcript|file|files|attachment|attachments|audio)"
)
_INPUT_NOUN = rf"(?:{_RUN_INPUT_NOUN}|{_SOURCE_NOUN})"
# Partitive, as after "ei annettu"; the last part of a compound counts too.
_RUN_INPUT_NOUN_FI = r"\w*(?:syötettä|syötteitä|kysymystä|kysymyksiä|otetta|otteita)"
_SOURCE_NOUN_FI = (
    r"\w*(?:tekstiä|sisältöä|asiakirjaa|asiakirjoja|dokumenttia|dokumentteja"
    r"|tiedostoa|tiedostoja|liitettä|liitteitä|litterointia|äänitettä)"
)
_NOT_GIVEN = r"(?:was|were|has\s+been|have\s+been)\s+(?:provided|given|supplied|attached)"
_NOT_GIVEN_FI = r"ei\s+(?:ole\s+|ollut\s+)?(?:annettu|toimitettu|liitetty)"
#: A text written by a model that was given nothing to work on. Kept short and
#: anchored: "please provide a medical certificate", "no discounts were given"
#: and "alennusta ei annettu" are answers.
_NO_INPUT = re.compile(
    # "Please provide the question and the passages", at the start of the text.
    r"^\W*(?:i(?:'m|\s+am)\s+sorry[,.]?\s+(?:but\s+)?)?(?:please|kindly)\s+"
    rf"(?:provide|share|supply)\b[^.!?\n]{{0,80}}?\b{_INPUT_NOUN}\b"
    # "no policy passages were provided"
    rf"|\bno\s+(?:\w+\s+){{0,3}}?{_RUN_INPUT_NOUN}\s+{_NOT_GIVEN}\b"
    r"|^\W*(?:ole\s+hyvä\s+ja|voisitko|voitko)\s+"
    r"(?:anna|antaa|toimita|toimittaa|lähetä|lähettää)\b"
    # "kysymystä ei annettu", "ei ole annettu otteita"
    rf"|\b{_RUN_INPUT_NOUN_FI}\s+{_NOT_GIVEN_FI}\b"
    rf"|\b{_NOT_GIVEN_FI}\s+(?:\w+\s+){{0,2}}?{_RUN_INPUT_NOUN_FI}\b",
    re.IGNORECASE,
)
#: "No documents were provided": said of a source it is a value, said by a model
#: of its own run it is not. Told only next to ``_SPEAKS_OF_THE_RUN``.
_NO_SOURCE = re.compile(
    rf"\bno\s+(?:\w+\s+){{0,3}}?{_SOURCE_NOUN}\s+{_NOT_GIVEN}\b"
    rf"|\b{_SOURCE_NOUN_FI}\s+{_NOT_GIVEN_FI}\b"
    rf"|\b{_NOT_GIVEN_FI}\s+(?:\w+\s+){{0,2}}?{_SOURCE_NOUN_FI}\b",
    re.IGNORECASE,
)
#: The model speaking of what it could not do: "I cannot answer", "so there is
#: nothing to extract", "provided to me", "en voi vastata", "ei voi muodostaa".
_SPEAKS_OF_THE_RUN = re.compile(
    r"\b(?:i|we)\s+(?:cannot|can['’]?t|can\s+not|could\s+not|couldn['’]t|am\s+unable"
    r"|was\s+unable|do\s+not\s+have|don['’]t\s+have|have\s+no)\b"
    r"|\bso\s+(?:there\s+is\s+|there['’]s\s+)?nothing\b"
    r"|\bnothing\s+to\s+(?:answer|extract|summari[sz]e|analy[sz]e|transcribe|classify|report)\b"
    r"|\b(?:to|with)\s+me\b"
    r"|\b(?:en|emme)\s+(?:voi|pysty|osaa)\b|\bei\s+voi(?:da)?\b|\bminulle\b",
    re.IGNORECASE,
)
#: How many record numbers one warning names.
_WARNING_RECORDS_TOLD = 10


def _is_blank(value: Any) -> bool:
    """Nothing in it: null, blank text, or a list or object of only such values."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return all(_is_blank(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_is_blank(v) for v in value)
    return False


def _says_none(value: Any) -> bool:
    """A sources value with no source in it: blank, or text such as "None"."""
    if _is_blank(value):
        return True
    if isinstance(value, str):
        return bool(_SAYS_NONE.match(value))
    if isinstance(value, (list, tuple)):
        return all(_says_none(v) for v in value)
    return False


def _is_sources_field(name: str) -> bool:
    """``sources``, ``cited_sources``, ``policyCitations``, ``lähteet``; not ``source_language``."""
    words = re.split(r"[^0-9a-zäöå]+", re.sub(r"(?<=[a-zäöå])(?=[A-ZÄÖÅ])", "_", name).lower())
    return name.strip().lower() in _SOURCES_NAMES or any(w in _SOURCES_WORDS for w in words)


def _has_sources(record: dict[str, Any], sources_fields: set[str]) -> bool | None:
    """Whether the record names a source; None when it has no place for one.

    A sources field the record lacks is one with nothing in it. A "Sources:"
    line with nothing after the colon is not read: the list may follow it.
    """
    found = [not _says_none(record.get(name)) for name in sources_fields]
    for name, value in record.items():
        if name not in sources_fields and isinstance(value, str):
            found.extend(
                not _says_none(m.group(1))
                for m in _SOURCES_LINE.finditer(value)
                if m.group(1).strip()
            )
    return any(found) if found else None


def _says_no_input(text: str) -> bool:
    """Whether a text reads as written by a model that was given nothing to work on."""
    if _NO_INPUT.search(text):
        return True
    return bool(_NO_SOURCE.search(text) and _SPEAKS_OF_THE_RUN.search(text))


def _is_text_type(declared: Any) -> bool:
    """``str``, ``string``, ``text``, ``list[string]``; not ``int``, ``date`` or ``bool``."""
    return not isinstance(declared, str) or bool(re.search(r"str|text", declared, re.IGNORECASE))


def _free_texts(record: dict[str, Any], spec: dict[str, Any] | None):
    """The texts of a record that a model wrote freely.

    A field the spec gives allowed values, or a type other than text, holds a
    value of that field and never the model's words about its run.
    """
    allowed = (spec or {}).get("allowed_values")
    types = (spec or {}).get("field_types")
    for name, value in record.items():
        if isinstance(allowed, dict) and allowed.get(name):
            continue
        if isinstance(types, dict) and not _is_text_type(types.get(name)):
            continue
        yield from _json_strings(value)


def _records_text(numbers: list[int], total: int) -> str:
    if total == 1:
        return "The result"
    told = ", ".join(str(n) for n in numbers[:_WARNING_RECORDS_TOLD])
    more = len(numbers) - _WARNING_RECORDS_TOLD
    noun = "Record" if len(numbers) == 1 else "Records"
    return f"{noun} {told}" + (f" and {more} more" if more > 0 else "") + f" of {total}"


def output_warnings(
    result: dict[str, Any] | None, spec: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """What looks wrong in a run's result, whatever the use case. Informs; decides nothing.

    A test run "succeeded" when its Job exited 0, and the PoC tab offered the
    approval on that alone. In a policy Q&A walk-through the first answer was
    "Please provide the employee's question and the numbered policy passages",
    the answers were shifted by one question, and one said "Sources: None — no
    policy passages were provided" (12 Nov 2026). Nothing said so until asked.

    ``result`` is what ``parse_run_output`` returns. Four shapes are told, each
    once, with the 1-based numbers of the records it was seen in:

    - ``empty_record``: a record whose every field is empty;
    - ``required_field_empty``: a field the spec requires, empty in some records
      and filled in others (one warning per field);
    - ``sources_missing``: a sources or citations field, or a "Sources:" line in
      a text, that is empty or says none while other records name sources;
    - ``no_input_answer``: a text, a section of a report included, in which the
      model asks for its input or says it was given none. "No attachments were
      provided" alone is a value about the source and is not told; nor is any
      text of a field the spec gives allowed values or a type other than text.

    No model is asked, and a run with warnings is still a succeeded run: the
    person and the agent are told, and look.
    """
    record = (result or {}).get("record")
    records = record if isinstance(record, list) else [record]
    records = [r for r in records if isinstance(r, dict)]
    total = len(records)
    spec = normalize_spec(spec) if isinstance(spec, dict) else None
    warnings: list[dict[str, Any]] = []

    def warn(code: str, numbers: list[int], message: str, field: str | None = None) -> None:
        warning: dict[str, Any] = {"code": code, "message": message, "records": numbers}
        if field is not None:
            warning["field"] = field
        warnings.append(warning)

    empty = [i for i, r in enumerate(records, 1) if _is_blank(r)]
    if empty:
        verb = "has" if len(empty) == 1 else "have"
        warn(
            "empty_record",
            empty,
            f"{_records_text(empty, total)} {verb} no values: every field is empty.",
        )

    required = (spec or {}).get("required_fields")
    for field in required if isinstance(required, list) else []:
        if not isinstance(field, str) or "." in field:
            continue  # a column of a table field is the review's to check, per row
        blank = [i for i, r in enumerate(records, 1) if _is_blank(r.get(field))]
        # A record with nothing in it is told once, above.
        told = [i for i in blank if i not in empty]
        if told and len(blank) < total:
            warn(
                "required_field_empty",
                told,
                f"The required field {field[:60]} is empty in "
                f"{_records_text(told, total).lower()} and filled in others.",
                field=field,
            )

    # By the spec's field names or the records' own; a table column is not one.
    named = [*((spec or {}).get("fields") or []), *(key for r in records for key in r)]
    sources_fields = {
        name
        for name in named
        if isinstance(name, str) and "." not in name and _is_sources_field(name)
    }
    sourced = [_has_sources(r, sources_fields) for r in records]
    without = [i for i, has in enumerate(sourced, 1) if has is False and i not in empty]
    if without and any(sourced):
        verb = "names" if len(without) == 1 else "name"
        warn(
            "sources_missing",
            without,
            f"{_records_text(without, total)} {verb} no sources, and other records do.",
        )

    no_input = [
        i
        for i, r in enumerate(records, 1)
        if any(_says_no_input(text) for text in _free_texts(r, spec))
    ]
    if no_input:
        verb = "reads" if len(no_input) == 1 else "read"
        warn(
            "no_input_answer",
            no_input,
            f"{_records_text(no_input, total)} {verb} as if the step was given no input "
            '(a text such as "please provide" or "no … were provided").',
        )
    return warnings


# -- the process the UI is built from -------------------------------------------

_BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
_KINDS = (
    "userTask",
    "manualTask",
    "serviceTask",
    "sendTask",
    "scriptTask",
    "task",
    "startEvent",
    "endEvent",
    "exclusiveGateway",
    "parallelGateway",
)


class BpmnParseError(ValueError):
    """The session's workflow.bpmn is not well-formed XML."""


def process_from_bpmn(xml: str) -> dict[str, Any]:
    """Lanes, nodes and sequence flows of the BPMN, in the shape the case UI reads.

    A lane holding a user or manual task is a role; one holding only service
    tasks is the system. Data objects a task writes or reads are kept by name,
    so the input screen knows what to ask for.

    A file that does not parse is a ``BpmnParseError``, which each caller
    answers in its own way; left unhandled it turned every read of a running
    case into a 500, so the case was never settled from its run (#295).
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise BpmnParseError(f"workflow.bpmn does not parse: {exc}") from exc
    proc = root.find(f"{_BPMN}process")
    if proc is None:
        return {"lanes": [], "nodes": [], "flows": []}
    data_names = {d.get("id"): d.get("name") for d in proc.iter(f"{_BPMN}dataObjectReference")}
    nodes: dict[str, dict[str, Any]] = {}
    for kind in _KINDS:
        for el in proc.iter(f"{_BPMN}{kind}"):
            nodes[el.get("id")] = {
                "id": el.get("id"),
                "kind": kind,
                # "[A2S] Transcribe …": the component code is for the diagram reader.
                "name": re.sub(r"^\[[A-Z0-9]+\]\s*", "", el.get("name") or ""),
                "lane": None,
                "inputs": [
                    data_names.get(a.findtext(f"{_BPMN}sourceRef"))
                    for a in el.iter(f"{_BPMN}dataInputAssociation")
                ],
                "outputs": [
                    data_names.get(a.findtext(f"{_BPMN}targetRef"))
                    for a in el.iter(f"{_BPMN}dataOutputAssociation")
                ],
            }
    lanes = []
    for lane in proc.iter(f"{_BPMN}lane"):
        refs = [r.text for r in lane.iter(f"{_BPMN}flowNodeRef")]
        for ref in refs:
            if ref in nodes:
                nodes[ref]["lane"] = lane.get("id")
        human = any(nodes.get(r, {}).get("kind") in ("userTask", "manualTask") for r in refs)
        lanes.append({"id": lane.get("id"), "name": lane.get("name") or "", "human": human})
    flows = [
        {"from": f.get("sourceRef"), "to": f.get("targetRef"), "name": f.get("name") or ""}
        for f in proc.iter(f"{_BPMN}sequenceFlow")
    ]
    return {"lanes": lanes, "nodes": list(nodes.values()), "flows": flows}


_YES = re.compile(r"^(yes|kyllä|approved?|hyväksytty)$", re.IGNORECASE)
_HUMAN = ("userTask", "manualTask")


def _is_task(node: dict[str, Any]) -> bool:
    return bool(re.search(r"Task$|^task$", node["kind"]))


def _walk(process: dict[str, Any]) -> list[dict[str, Any]]:
    """The tasks met walking from the start event, taking the approve branch."""
    by_id = {n["id"]: n for n in process["nodes"]}
    flows = process["flows"]
    start = next((n for n in process["nodes"] if n["kind"] == "startEvent"), None)
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    node_id = start["id"] if start else None
    while node_id and node_id not in seen:
        seen.add(node_id)
        node = by_id.get(node_id)
        if node and _is_task(node):
            steps.append(node)
        out = [f for f in flows if f["from"] == node_id]
        chosen = next((f for f in out if _YES.match(f["name"])), out[0] if out else None)
        node_id = chosen["to"] if chosen else None
    return steps


def process_problem(process: dict[str, Any]) -> str | None:
    """Why the process cannot be walked, or None when it can.

    ``reviewer_task`` answers "nobody reviews" for a process it cannot walk
    (no start event, nothing reachable from it). That answer must not let an
    AI result complete a case without a person: such a process is reported
    instead, and a case run under it goes to review.
    """
    if not any(n["kind"] == "startEvent" for n in process["nodes"]):
        return "workflow.bpmn has no start event"
    if not _walk(process):
        return "no task can be reached from the start event of workflow.bpmn"
    return None


def reviewer_task(process: dict[str, Any]) -> str | None:
    """The task of the person who reviews the result, or None when nobody does.

    The same rule the case UI applies (lib/case-process.ts): walk from the
    start event, taking the approve branch at a gateway; everyone before the
    first AI step gives a part of the input, and the first person after it
    reviews. The server used to count user tasks instead, so a process with
    two input tasks and no reviewer went to review with no review screen, and
    the case stuck there (#296). This is computed once, here, and served with
    the model.
    """
    steps = _walk(process)
    first_ai = next((i for i, n in enumerate(steps) if n["kind"] not in _HUMAN), None)
    if first_ai is None:
        return None
    return next((n["id"] for n in steps[first_ai:] if n["kind"] in _HUMAN), None)
