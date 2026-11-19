"""SandboxRunner: create a run, follow it, report where it got to (#91).

The Kubernetes client is faked so the whole lifecycle is exercised without a
cluster — what matters here is that the Job we submit is the one the reviewed
manifest describes, that output arrives during the run rather than at the end,
and that a run cut off at the deadline is not reported as a plain failure.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from wizard_api.services.sandbox_runner import (
    CHECK_DEADLINE_SECONDS,
    CHECK_KIND,
    CONTAINER_START_TIMEOUT_SECONDS,
    JOB_NAME_PREFIX,
    RUN_CONTAINER,
    RUN_KIND_LABEL,
    SESSION_LABEL,
    RunNotFoundError,
    SandboxNotConfiguredError,
    SandboxRunner,
    job_name,
    new_run_id,
    render_job_manifest,
    runs_use_shared_key,
    status_from_job,
)

IMAGE = "registry.example/gaik/wizard-v2-poc-runner:latest"
SESSION = "0b5b7b2b-a9ce-4896-b224-8d73614a9bb7"


# ---------------------------------------------------------------------------
# Run ids and names
# ---------------------------------------------------------------------------


def test_the_run_id_is_a_legal_job_name_component():
    rid = new_run_id(SESSION, now=datetime(2026, 9, 29, 8, 30, 0, tzinfo=UTC))

    assert rid == "20260929083000-614a9bb7"
    assert job_name(rid).startswith(JOB_NAME_PREFIX)
    # DNS-1123 label: lowercase alphanumerics and dashes only.
    assert all(c.islower() or c.isdigit() or c == "-" for c in job_name(rid))


def test_a_session_id_with_nothing_usable_still_yields_a_name():
    rid = new_run_id("///", now=datetime(2026, 9, 29, 8, 30, 0, tzinfo=UTC))

    assert rid == "20260929083000"


# ---------------------------------------------------------------------------
# The manifest we submit is the manifest that was reviewed
# ---------------------------------------------------------------------------


def test_the_rendered_job_keeps_the_isolation_the_manifest_sets():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE)

    spec = manifest["spec"]
    assert spec["activeDeadlineSeconds"] == 600
    assert spec["backoffLimit"] == 0
    pod = spec["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    # Scratch space only — no hostPath, no PVC.
    for volume in pod["volumes"]:
        assert set(volume) <= {"name", "emptyDir"}


def test_the_rendered_job_names_the_session_the_run_and_the_image():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE)

    assert manifest["metadata"]["name"] == "wizard-v2-poc-run-run-1"
    assert manifest["metadata"]["labels"]["wizard-v2/session-id"] == SESSION
    images = {c["image"] for c in manifest["spec"]["template"]["spec"]["containers"]}
    images |= {c["image"] for c in manifest["spec"]["template"]["spec"]["initContainers"]}
    assert images == {IMAGE}


def _fetch_env(manifest):
    init = manifest["spec"]["template"]["spec"]["initContainers"][0]
    return {e["name"]: e for e in init["env"]}


def test_the_job_of_the_staging_stack_addresses_the_staging_api(monkeypatch):
    monkeypatch.delenv("WIZARD_INSTANCE_NAME", raising=False)
    env = _fetch_env(render_job_manifest(SESSION, "r1", IMAGE))

    assert env["WIZARD_API_URL"]["value"] == "http://wizard-v2-api:8100"
    assert env["WIZARD_API_TOKEN"]["valueFrom"]["secretKeyRef"]["name"] == "wizard-v2-token"


def test_the_job_of_a_second_stack_addresses_its_own_api_and_token(monkeypatch):
    """A Job from the s4 stack that fetched from wizard-v2-api would run the
    staging stack's session (or none), with the staging token."""
    monkeypatch.setenv("WIZARD_INSTANCE_NAME", "wizard-v2-s4")
    env = _fetch_env(render_job_manifest(SESSION, "r1", IMAGE))

    assert env["WIZARD_API_URL"]["value"] == "http://wizard-v2-s4-api:8100"
    assert env["WIZARD_API_TOKEN"]["valueFrom"]["secretKeyRef"]["name"] == "wizard-v2-s4-token"


def test_an_image_still_carrying_the_registry_placeholder_is_refused():
    """Submitting it would create a Job that dies on ImagePullBackOff — the
    same check the shell script makes, before anything exists in the cluster."""
    with pytest.raises(SandboxNotConfiguredError, match="placeholder"):
        render_job_manifest(SESSION, "run-1", "image-registry/PROJECT_PLACEHOLDER/runner:latest")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _job(**status):
    return SimpleNamespace(status=SimpleNamespace(**status))


def test_a_finished_run_is_succeeded():
    assert status_from_job("r", _job(succeeded=1, conditions=[])).phase == "succeeded"


def test_a_running_run_is_running():
    assert status_from_job("r", _job(active=1, conditions=[])).phase == "running"


def test_a_run_that_has_not_started_is_pending():
    assert status_from_job("r", _job(conditions=[])).phase == "pending"


def test_a_deadline_is_reported_as_a_timeout_not_a_failure():
    """ "Your run was cut off at ten minutes" is a different thing to tell
    someone than "your PoC failed"."""
    job = _job(
        failed=1,
        conditions=[SimpleNamespace(type="Failed", reason="DeadlineExceeded", message="…")],
    )

    status = status_from_job("r", job)

    assert status.phase == "timeout"
    assert "ten-minute" in status.message


def test_a_real_failure_keeps_its_message():
    job = _job(
        failed=1,
        conditions=[SimpleNamespace(type="Failed", reason="BackoffLimitExceeded", message="boom")],
    )

    status = status_from_job("r", job)

    assert status.phase == "failed"
    assert status.message == "boom"


def test_finished_covers_every_terminal_phase():
    assert status_from_job("r", _job(succeeded=1, conditions=[])).finished
    assert not status_from_job("r", _job(active=1, conditions=[])).finished


# ---------------------------------------------------------------------------
# The lifecycle, against a fake cluster
# ---------------------------------------------------------------------------


class FakeBatch:
    def __init__(self, job=None, existing=None):
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self._job = job or _job(active=1, conditions=[])
        # Jobs already in the project, as list_namespaced_job returns them.
        self.existing: list = list(existing or [])

    def create_namespaced_job(self, namespace, body, _request_timeout=None):
        self.created.append({"namespace": namespace, "body": body, "timeout": _request_timeout})

    def list_namespaced_job(self, namespace, label_selector, _request_timeout=None):
        wanted = dict(pair.split("=", 1) for pair in label_selector.split(","))
        items = [j for j in self.existing if wanted.items() <= j.metadata.labels.items()]
        return SimpleNamespace(items=items)

    def read_namespaced_job_status(self, name, namespace):
        return self._job

    def delete_namespaced_job(self, name, namespace, propagation_policy):
        self.deleted.append(name)


class FakeLogStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self):
        yield from self._chunks


def _pod(started=True, phase="Running"):
    """A pod whose run container is (or is not yet) a process."""
    state = SimpleNamespace(running=SimpleNamespace() if started else None, terminated=None)
    return SimpleNamespace(
        status=SimpleNamespace(
            phase=phase,
            container_statuses=[SimpleNamespace(name=RUN_CONTAINER, state=state)],
        )
    )


class FakeCore:
    def __init__(self, chunks, pod_after=0, pods=None):
        self._chunks = chunks
        self._calls = 0
        self._pod_after = pod_after
        self._pods = list(pods) if pods is not None else None
        self.pod_reads = 0
        self.log_args: dict = {}

    def read_namespaced_pod(self, name, namespace):
        self.pod_reads += 1
        if self._pods is None:
            return _pod()
        return self._pods.pop(0) if len(self._pods) > 1 else self._pods[0]

    def list_namespaced_pod(self, namespace, label_selector):
        self._calls += 1
        if self._calls <= self._pod_after:
            return SimpleNamespace(items=[])
        return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name="pod-1"))])

    def read_namespaced_pod_log(self, **kwargs):
        self.log_args = kwargs
        return FakeLogStream(self._chunks)


def _runner(batch=None, core=None):
    return SandboxRunner(
        namespace="gaik-staging", image=IMAGE, batch=batch or FakeBatch(), core=core or FakeCore([])
    )


def test_creating_a_run_submits_the_job_and_returns_its_id():
    batch = FakeBatch()

    run_id = _runner(batch=batch).create_run(SESSION)

    assert batch.created[0]["namespace"] == "gaik-staging"
    assert batch.created[0]["body"]["metadata"]["name"] == job_name(run_id)


def test_creating_a_job_gives_up_well_before_a_case_claim_goes_stale():
    from wizard_api.services.case_service import CLAIM_MAX_AGE
    from wizard_api.services.sandbox_runner import CREATE_TIMEOUT_S

    batch = FakeBatch()
    _runner(batch=batch).create_run(SESSION)

    assert batch.created[0]["timeout"] == CREATE_TIMEOUT_S
    assert CREATE_TIMEOUT_S * 2 <= CLAIM_MAX_AGE.total_seconds()


def test_logs_arrive_line_by_line_while_the_run_is_going():
    """The acceptance criterion: incrementally, not only at completion."""
    core = FakeCore([b"loading pipeline\n", b"extracting\nwriting output\n"])

    lines = list(_runner(core=core).stream_logs("run-1"))

    assert lines == ["loading pipeline", "extracting", "writing output"]
    assert core.log_args["follow"] is True
    assert core.log_args["container"] == RUN_CONTAINER


def test_a_line_split_across_chunks_comes_out_whole():
    """A failed run's last line, cut by the network read, is still one line."""
    core = FakeCore(
        [
            b"Traceback (most recent call last):\nValueError",
            b": Section 'kpi_overview' has 23 units\nP\xc3",
            b"\xa4\xc3\xa4ttyi",
        ]
    )

    lines = list(_runner(core=core).stream_logs("run-1"))

    assert lines == [
        "Traceback (most recent call last):",
        "ValueError: Section 'kpi_overview' has 23 units",
        "Päättyi",
    ]


def test_the_stream_waits_for_the_pod_to_be_scheduled():
    """A pod takes a moment to appear; that is not an error."""
    core = FakeCore([b"ready\n"], pod_after=2)

    lines = list(_runner(core=core).stream_logs("run-1", poll_seconds=0))

    assert lines == ["ready"]


def _labelled_job(session_id, **status):
    job = _job(**status)
    job.metadata = SimpleNamespace(labels={SESSION_LABEL: session_id})
    return job


def test_a_run_is_reported_to_the_session_that_started_it():
    runner = _runner(batch=FakeBatch(_labelled_job(SESSION, succeeded=1, conditions=[])))

    runner.check_run_of_session("run-1", SESSION)
    assert runner.status("run-1", session_id=SESSION).phase == "succeeded"


def test_another_sessions_run_is_not_found_rather_than_forbidden():
    """B3 (#143): a run id is a string the caller chose; the Job's label decides."""
    runner = _runner(batch=FakeBatch(_labelled_job("some-other-session", succeeded=1)))

    with pytest.raises(RunNotFoundError):
        runner.check_run_of_session("run-1", SESSION)
    with pytest.raises(RunNotFoundError):
        runner.status("run-1", session_id=SESSION)


def test_a_job_without_the_session_label_is_not_any_sessions_run():
    runner = _runner(batch=FakeBatch(_job(succeeded=1)))  # no metadata at all

    with pytest.raises(RunNotFoundError):
        runner.check_run_of_session("run-1", SESSION)


def test_a_run_whose_job_is_gone_is_not_found():
    class Gone(FakeBatch):
        def read_namespaced_job_status(self, name, namespace):
            err = RuntimeError("not found")
            err.status = 404
            raise err

    with pytest.raises(RunNotFoundError):
        _runner(batch=Gone()).check_run_of_session("run-1", SESSION)


def test_a_cluster_error_other_than_404_is_not_turned_into_not_found():
    class Broken(FakeBatch):
        def read_namespaced_job_status(self, name, namespace):
            err = RuntimeError("boom")
            err.status = 500
            raise err

    with pytest.raises(RuntimeError, match="boom"):
        _runner(batch=Broken()).check_run_of_session("run-1", SESSION)


def test_the_status_without_a_session_stays_unchecked_for_hand_runs():
    assert _runner().status("run-1").phase == "running"


def test_the_stream_waits_for_the_run_container_not_only_the_pod():
    """The pod is listed while its init container still runs; reading the log
    then is a 400 PodInitializing and ended the stream before the run was
    recorded as succeeded (#143)."""
    core = FakeCore([b"ready\n"], pods=[_pod(started=False), _pod(started=False), _pod()])

    lines = list(_runner(core=core).stream_logs("run-1", poll_seconds=0))

    assert lines == ["ready"]
    assert core.pod_reads == 3
    assert core.log_args  # the log was read only after the container started


def test_a_run_that_already_finished_can_still_be_followed():
    state = SimpleNamespace(running=None, terminated=SimpleNamespace(exit_code=0))
    pod = SimpleNamespace(
        status=SimpleNamespace(
            phase="Succeeded", container_statuses=[SimpleNamespace(name=RUN_CONTAINER, state=state)]
        )
    )
    core = FakeCore([b"done\n"], pods=[pod])

    assert list(_runner(core=core).stream_logs("run-1", poll_seconds=0)) == ["done"]


def test_a_pod_that_failed_before_the_run_container_started_is_named():
    core = FakeCore([], pods=[_pod(started=False, phase="Failed")])

    with pytest.raises(SandboxNotConfiguredError, match="package fetch"):
        list(_runner(core=core).stream_logs("run-1", poll_seconds=0))
    assert core.log_args == {}


class _SettlingBatch(FakeBatch):
    """A Job whose status moves on between reads, as it does right after a pod exits."""

    def __init__(self, jobs):
        super().__init__()
        self._jobs = list(jobs)
        self.reads = 0

    def read_namespaced_job_status(self, name, namespace):
        self.reads += 1
        return self._jobs.pop(0) if len(self._jobs) > 1 else self._jobs[0]


def test_the_final_status_waits_for_the_job_to_settle_after_the_log_ends():
    """The log ends when the container exits; the Job's status follows a moment
    later. Read at once, a succeeded run was reported as still running, and the
    successful run was never recorded."""
    batch = _SettlingBatch([_job(active=1), _job(active=1), _job(succeeded=1, conditions=[])])

    status = _runner(batch=batch).final_status("run-1", poll_seconds=0)

    assert status.phase == "succeeded"
    assert batch.reads == 3


def test_the_final_status_does_not_wait_for_a_run_that_is_already_finished():
    batch = _SettlingBatch([_job(failed=1, conditions=[])])

    assert _runner(batch=batch).final_status("run-1", poll_seconds=0).phase == "failed"
    assert batch.reads == 1


def test_the_final_status_gives_up_after_its_wait_and_reports_what_it_saw():
    batch = _SettlingBatch([_job(active=1)])

    status = _runner(batch=batch).final_status("run-1", wait_seconds=0, poll_seconds=0)

    assert status.phase == "running"
    assert batch.reads == 1


def test_the_container_gets_its_own_longer_wait_than_the_pod():
    """An image pull on a cold node takes longer than the 120 s the pod wait
    allows; sharing that deadline reported a slow start as a failed run."""
    assert CONTAINER_START_TIMEOUT_SECONDS >= 300


def test_a_container_that_never_starts_is_named_after_its_wait(monkeypatch):
    import wizard_api.services.sandbox_runner as sr

    monkeypatch.setattr(sr, "CONTAINER_START_TIMEOUT_SECONDS", 0)
    core = FakeCore([b"never\n"], pods=[_pod(started=False)])

    with pytest.raises(SandboxNotConfiguredError, match="did not start in time"):
        list(_runner(core=core).stream_logs("run-1", poll_seconds=0))
    assert core.log_args == {}


def test_deleting_a_run_removes_its_job():
    batch = FakeBatch()

    _runner(batch=batch).delete_run("run-1")

    assert batch.deleted == [job_name("run-1")]


# ---------------------------------------------------------------------------
# Refusing to run half-configured
# ---------------------------------------------------------------------------


def test_a_missing_namespace_is_named_rather_than_guessed():
    runner = SandboxRunner(namespace=None, image=IMAGE, batch=FakeBatch(), core=FakeCore([]))

    with pytest.raises(SandboxNotConfiguredError, match="namespace"):
        runner.create_run(SESSION)


def test_a_missing_runner_image_is_named_rather_than_guessed():
    runner = SandboxRunner(namespace="x", image=None, batch=FakeBatch(), core=FakeCore([]))

    with pytest.raises(SandboxNotConfiguredError, match="runner image"):
        runner.create_run(SESSION)


# ---------------------------------------------------------------------------
# Finding the manifest (the #180 mistake, in a different file)
# ---------------------------------------------------------------------------


def test_the_manifest_is_found_in_a_checkout():
    from wizard_api.services.sandbox_runner import resolve_manifest

    found = resolve_manifest()

    assert found is not None
    assert found.name == "sandbox-job.yaml"


def test_an_explicit_manifest_path_wins(monkeypatch, tmp_path):
    from wizard_api.services.sandbox_runner import resolve_manifest

    elsewhere = tmp_path / "sandbox-job.yaml"
    elsewhere.write_text("kind: Job\n")
    monkeypatch.setenv("WIZARD_SANDBOX_MANIFEST", str(elsewhere))

    assert resolve_manifest() == elsewhere


def test_a_missing_manifest_names_the_variable_to_set(monkeypatch, tmp_path):
    """Path arithmetic from the module lands on "/" in the image — the mistake
    #180 was about. A deployment that keeps the manifest elsewhere says so."""
    from wizard_api.services import sandbox_runner

    monkeypatch.setenv("WIZARD_SANDBOX_MANIFEST", str(tmp_path / "nope.yaml"))

    with pytest.raises(SandboxNotConfiguredError, match="WIZARD_SANDBOX_MANIFEST"):
        sandbox_runner.render_job_manifest(SESSION, "run-1", IMAGE)


# ---------------------------------------------------------------------------
# The preflight (#252): same Job, same limits, a different command
# ---------------------------------------------------------------------------


def test_a_real_run_carries_no_run_kind_and_runs_the_entrypoint():
    manifest = render_job_manifest(SESSION, "run-1", IMAGE)

    assert RUN_KIND_LABEL not in manifest["metadata"]["labels"]
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert "python run_poc.py" in container["args"][0]


def test_the_preflight_runs_the_check_script_not_the_package():
    manifest = render_job_manifest(SESSION, "run-1-chk", IMAGE, kind=CHECK_KIND)

    assert manifest["metadata"]["labels"][RUN_KIND_LABEL] == CHECK_KIND
    assert manifest["spec"]["template"]["metadata"]["labels"][RUN_KIND_LABEL] == CHECK_KIND
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["command"][:2] == ["python", "-c"]
    assert "PREFLIGHT" in container["command"][2]
    assert "args" not in container


def test_the_preflight_keeps_the_sandbox_limits_and_a_shorter_deadline():
    manifest = render_job_manifest(SESSION, "run-1-chk", IMAGE, kind=CHECK_KIND)

    spec = manifest["spec"]
    assert spec["activeDeadlineSeconds"] == CHECK_DEADLINE_SECONDS < 600
    assert spec["backoffLimit"] == 0
    pod = spec["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    container = pod["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    # the fetch step is untouched: the check reads the same package a run does
    assert pod["initContainers"][0]["name"] == "fetch-poc"


def test_creating_a_preflight_names_it_apart_and_labels_it():
    batch = FakeBatch()
    rid = _runner(batch=batch).create_run(SESSION, kind=CHECK_KIND)

    assert rid.endswith("-chk")
    body = batch.created[0]["body"]
    assert body["metadata"]["name"] == job_name(rid)
    assert body["metadata"]["labels"][RUN_KIND_LABEL] == CHECK_KIND


def test_the_run_kind_of_a_job_is_read_from_its_label():
    check = SimpleNamespace(
        metadata=SimpleNamespace(labels={SESSION_LABEL: SESSION, RUN_KIND_LABEL: CHECK_KIND}),
        status=SimpleNamespace(),
    )
    real = _labelled_job(SESSION, succeeded=1)

    assert _runner(batch=FakeBatch(check)).run_kind("r-chk") == CHECK_KIND
    assert _runner(batch=FakeBatch(real)).run_kind("r") is None


def test_the_package_fetch_names_the_sessions_owner():
    # With WIZARD_REQUIRE_USER_HEADER set the api serves a session only to its
    # owner, so the run's fetch says who that is.
    manifest = render_job_manifest(SESSION, "r1", IMAGE, user_id="dev@gaik.local")
    fetch = next(
        c
        for c in manifest["spec"]["template"]["spec"]["initContainers"]
        if c["name"] == "fetch-poc"
    )

    assert _fetch_env(manifest)["WIZARD_USER_ID"]["value"] == "dev@gaik.local"
    assert '-H "X-Wizard-User-Id: ${WIZARD_USER_ID:-}"' in fetch["command"][-1]


def test_a_user_id_stays_a_value_and_never_becomes_yaml_or_shell():
    tricky = "a\"; echo other $(date) `date` 'b"
    manifest = render_job_manifest(SESSION, "r1", IMAGE, user_id=tricky)
    fetch = next(
        c
        for c in manifest["spec"]["template"]["spec"]["initContainers"]
        if c["name"] == "fetch-poc"
    )

    assert _fetch_env(manifest)["WIZARD_USER_ID"]["value"] == tricky
    assert "echo other" not in fetch["command"][-1]
    with pytest.raises(ValueError):
        render_job_manifest(SESSION, "r1", IMAGE, user_id="a\nX-Other: 1")


def test_a_case_run_keeps_the_owner_and_its_case():
    case = "3f1c2a4e-5b6d-4e7f-8a9b-0c1d2e3f4a5b"
    manifest = render_job_manifest(SESSION, "r1", IMAGE, case_id=case, user_id="u1")

    assert _fetch_env(manifest)["WIZARD_USER_ID"]["value"] == "u1"
    assert any(
        f"/poc?case={case}" in part
        for c in manifest["spec"]["template"]["spec"]["initContainers"]
        for part in c["command"]
    )


# ---------------------------------------------------------------------------
# How many runs may be going at once
# ---------------------------------------------------------------------------
# Each run and preflight reserves 1 CPU and 1 GiB from the project quota that
# the project's other apps also deploy from.


def _active_job(user="someone@example.org", instance="wizard-v2", **labels):
    from wizard_api.services.sandbox_runner import INSTANCE_LABEL, USER_LABEL, user_label

    metadata = SimpleNamespace(
        name="wizard-v2-poc-run-x",
        labels={
            "app": "wizard-v2-poc-run",
            INSTANCE_LABEL: instance,
            USER_LABEL: user_label(user),
            **labels,
        },
        creation_timestamp="2026-11-04T10:00:00Z",
    )
    return SimpleNamespace(metadata=metadata, status=SimpleNamespace(active=1, conditions=[]))


def test_a_new_job_carries_its_stack_and_a_digest_of_its_user():
    from wizard_api.services.sandbox_runner import INSTANCE_LABEL, USER_LABEL, user_label

    batch = FakeBatch()
    _runner(batch=batch).create_run(SESSION, user_id="ann@example.org")

    labels = batch.created[0]["body"]["metadata"]["labels"]
    assert labels[INSTANCE_LABEL] == "wizard-v2"
    assert labels[USER_LABEL] == user_label("ann@example.org")
    assert "@" not in labels[USER_LABEL]


def test_no_new_job_while_the_stack_has_as_many_going_as_it_may(monkeypatch):
    from wizard_api.services.sandbox_runner import RunLimitError

    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS", "2")
    batch = FakeBatch(existing=[_active_job("a@x.org"), _active_job("b@x.org")])

    with pytest.raises(RunLimitError):
        _runner(batch=batch).create_run(SESSION, user_id="c@x.org")
    assert batch.created == []


def test_no_new_job_while_the_user_has_as_many_going_as_they_may(monkeypatch):
    from wizard_api.services.sandbox_runner import RunLimitError

    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS_PER_USER", "1")
    batch = FakeBatch(existing=[_active_job("ann@example.org")])

    with pytest.raises(RunLimitError):
        _runner(batch=batch).create_run(SESSION, user_id="ann@example.org")
    _runner(batch=batch).create_run(SESSION, user_id="bob@example.org")
    assert len(batch.created) == 1


def test_finished_jobs_and_other_stacks_do_not_count(monkeypatch):
    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS", "1")
    done = _active_job()
    done.status = SimpleNamespace(succeeded=1, conditions=[])
    batch = FakeBatch(existing=[done, _active_job(instance="wizard-v2-s4")])

    _runner(batch=batch).create_run(SESSION, user_id="ann@example.org")

    assert len(batch.created) == 1


def test_the_ops_gauge_counts_unfinished_jobs_with_the_clients_it_loads(monkeypatch):
    # The gauge builds its own runner, as the API does: no clients are passed in,
    # so the count must load them first instead of calling a client that is None.
    from wizard_api import ops_metrics
    from wizard_api.services import sandbox_runner

    done = _active_job()
    done.status = SimpleNamespace(succeeded=1, conditions=[])
    batch = FakeBatch(existing=[_active_job("a@x.org"), _active_job("b@x.org"), done])

    def load(runner):
        runner._batch, runner._core = batch, FakeCore([])

    monkeypatch.setenv("WIZARD_SANDBOX_NAMESPACE", "gaik-staging")
    monkeypatch.setenv("WIZARD_POC_RUNNER_IMAGE", IMAGE)
    monkeypatch.setattr(sandbox_runner, "_K8S_AVAILABLE", True)
    monkeypatch.setattr(sandbox_runner.SandboxRunner, "_load_clients", load)

    assert ops_metrics._sandbox_active() == {"active": 2.0}


def _check_job(version, image=IMAGE, name="20261104100000-abc-chk", user=None, **status):
    from wizard_api.services.sandbox_runner import (
        CHECK_KIND,
        IMAGE_LABEL,
        RUN_KIND_LABEL,
        VERSION_LABEL,
        image_label,
    )

    job = _active_job(
        *([user] if user else []),
        **{
            SESSION_LABEL: SESSION,
            RUN_KIND_LABEL: CHECK_KIND,
            VERSION_LABEL: version,
            IMAGE_LABEL: image_label(image),
        },
    )
    job.metadata.name = JOB_NAME_PREFIX + name
    job.status = SimpleNamespace(conditions=[], **status)
    return job


def test_a_preflight_of_the_same_package_is_reused_while_it_is_going_or_passed():
    for status in ({"active": 1}, {"succeeded": 1}):
        runner = _runner(batch=FakeBatch(existing=[_check_job("0123abcd", **status)]))
        assert runner.reusable_check(SESSION, "0123abcd") == "20261104100000-abc-chk"
        assert runner.reusable_check(SESSION, "ffff0000") is None


def test_a_failed_preflight_is_not_reused():
    failed = _check_job("0123abcd")
    failed.status = SimpleNamespace(
        conditions=[SimpleNamespace(type="Failed", reason="BackoffLimitExceeded", message="x")]
    )

    assert _runner(batch=FakeBatch(existing=[failed])).reusable_check(SESSION, "0123abcd") is None


def test_a_preflight_is_labelled_with_the_version_it_checks():
    from wizard_api.services.sandbox_runner import CHECK_KIND, VERSION_LABEL

    batch = FakeBatch()
    _runner(batch=batch).create_run(SESSION, kind=CHECK_KIND, version="0123abcd")

    assert batch.created[0]["body"]["metadata"]["labels"][VERSION_LABEL] == "0123abcd"
    with pytest.raises(ValueError):
        _runner(batch=FakeBatch()).create_run(SESSION, kind=CHECK_KIND, version="x y")


# ---------------------------------------------------------------------------
# The limits under concurrent requests, and preflight reuse
# ---------------------------------------------------------------------------


class ClusterBatch(FakeBatch):
    """A fake cluster whose created Jobs are listed afterwards, with list latency.

    The latency widens the window between counting and creating, the window that
    let parallel requests of one user each get a Job.
    """

    def __init__(self, existing=None, list_latency=0.02, missing=()):
        super().__init__(existing=existing)
        self._list_latency = list_latency
        self._missing = set(missing)
        import threading

        self._lock = threading.Lock()

    def create_namespaced_job(self, namespace, body, _request_timeout=None):
        job = SimpleNamespace(
            metadata=SimpleNamespace(
                name=body["metadata"]["name"],
                labels=dict(body["metadata"]["labels"]),
                creation_timestamp=datetime.now(UTC).isoformat(),
            ),
            status=SimpleNamespace(active=1, conditions=[]),
        )
        with self._lock:
            super().create_namespaced_job(namespace, body, _request_timeout)
            self.existing.append(job)

    def list_namespaced_job(self, namespace, label_selector, _request_timeout=None):
        import time

        with self._lock:
            snapshot = list(self.existing)
        time.sleep(self._list_latency)
        wanted = dict(pair.split("=", 1) for pair in label_selector.split(","))
        return SimpleNamespace(
            items=[j for j in snapshot if wanted.items() <= j.metadata.labels.items()]
        )

    def read_namespaced_job_status(self, name, namespace):
        if name in self._missing:
            raise JobNotFoundError()
        for job in self.existing:
            if job.metadata.name == name:
                return job
        raise JobNotFoundError()

    def delete_namespaced_job(self, name, namespace, propagation_policy):
        with self._lock:
            super().delete_namespaced_job(name, namespace, propagation_policy)
            self.existing = [j for j in self.existing if j.metadata.name != name]


class JobNotFoundError(Exception):
    """What the client raises for a Job that is gone."""

    status = 404


def _parallel(n, fn):
    from concurrent.futures import ThreadPoolExecutor

    from wizard_api.services.sandbox_runner import RunLimitError

    def attempt(i):
        try:
            return fn(i)
        except RunLimitError:
            return "busy"

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(attempt, range(n)))


def test_parallel_runs_of_one_user_stay_within_the_users_limit(monkeypatch):
    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS_PER_USER", "2")
    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS", "10")
    batch = ClusterBatch()
    runner = _runner(batch=batch)

    results = _parallel(
        8, lambda i: runner.create_run(SESSION, run_id=f"r{i}", user_id="ann@x.org")
    )

    assert len(batch.created) == 2
    assert results.count("busy") == 6


def test_parallel_runs_of_many_users_stay_within_the_stacks_limit(monkeypatch):
    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS", "3")
    batch = ClusterBatch()

    def run(i):
        return _runner(batch=batch).create_run(SESSION, run_id=f"r{i}", user_id=f"u{i}@x.org")

    _parallel(8, run)

    assert len(batch.created) == 3


def test_two_simultaneous_preflights_of_one_version_share_one_job():
    batch = ClusterBatch()
    runner = _runner(batch=batch)

    results = _parallel(
        4, lambda i: runner.start_check(SESSION, "0123abcd", user_id="ann@x.org")["run_id"]
    )

    assert len(batch.created) == 1
    assert len(set(results)) == 1


def test_starting_a_preflight_deletes_the_sessions_older_unfinished_ones():
    old = _check_job("aaaa0000", name="20261104100000-old-chk", active=1)
    stale_image = _check_job(
        "0123abcd", image="registry.example/old:1", name="20261104100001-img-chk", active=1
    )
    passed_old = _check_job("bbbb0000", name="20261104100002-done-chk", succeeded=1)
    batch = ClusterBatch(existing=[old, stale_image, passed_old])

    started = _runner(batch=batch).start_check(SESSION, "0123abcd", user_id="ann@x.org")

    assert started["reused"] is False
    assert sorted(batch.deleted) == [
        job_name("20261104100000-old-chk"),
        job_name("20261104100001-img-chk"),
    ]
    assert len(batch.created) == 1


def test_a_superseded_preflight_does_not_cost_the_user_a_slot(monkeypatch):
    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS_PER_USER", "1")
    batch = ClusterBatch(existing=[_check_job("aaaa0000", user="ann@x.org", active=1)])

    _runner(batch=batch).start_check(SESSION, "0123abcd", user_id="ann@x.org")

    assert len(batch.created) == 1


def test_a_sessions_own_preflight_does_not_count_against_its_run(monkeypatch):
    from wizard_api.services.sandbox_runner import RunLimitError

    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS_PER_USER", "1")
    batch = ClusterBatch(existing=[_check_job("0123abcd", user="ann@x.org", active=1)])

    _runner(batch=batch).create_run(SESSION, user_id="ann@x.org")
    assert len(batch.created) == 1
    # Another session's run of the same user: that preflight and this run count.
    with pytest.raises(RunLimitError):
        _runner(batch=batch).create_run("other-session-0001", user_id="ann@x.org")


def test_a_preflight_reaped_between_listing_and_reading_is_not_reused():
    gone = _check_job("0123abcd", active=1)
    batch = ClusterBatch(existing=[gone], missing={gone.metadata.name})

    started = _runner(batch=batch).start_check(SESSION, "0123abcd", user_id="ann@x.org")

    assert started["reused"] is False
    assert len(batch.created) == 1


def test_a_preflight_that_passed_on_another_runner_image_is_not_reused():
    passed = _check_job("0123abcd", image="registry.example/old:1", succeeded=1)
    runner = _runner(batch=FakeBatch(existing=[passed]))

    assert runner.reusable_check(SESSION, "0123abcd") is None
    assert _runner(batch=FakeBatch(existing=[_check_job("0123abcd", succeeded=1)])).reusable_check(
        SESSION, "0123abcd"
    )


def test_a_job_is_labelled_with_the_image_of_its_rendered_manifest():
    from wizard_api.services.sandbox_runner import IMAGE_LABEL, image_label

    manifest = render_job_manifest(SESSION, "r1-chk", IMAGE, kind=CHECK_KIND)

    assert manifest["metadata"]["labels"][IMAGE_LABEL] == image_label(IMAGE)
    assert len(image_label(IMAGE)) <= 63


def test_the_busy_messages_name_no_counts(monkeypatch):
    from wizard_api.services.sandbox_runner import RunLimitError

    monkeypatch.setenv("WIZARD_MAX_ACTIVE_RUNS", "1")
    batch = FakeBatch(existing=[_active_job("a@x.org")])
    with pytest.raises(RunLimitError) as exc:
        _runner(batch=batch).create_run(SESSION, user_id="c@x.org")

    assert not any(ch.isdigit() for ch in str(exc.value))


def _secret_refs(manifest: dict) -> dict[str, set[str]]:
    """Secret names each container's env reads, by container name."""
    spec = manifest["spec"]["template"]["spec"]
    refs: dict[str, set[str]] = {}
    for container in (spec.get("initContainers") or []) + spec["containers"]:
        for entry in container.get("env") or []:
            ref = (entry.get("valueFrom") or {}).get("secretKeyRef")
            if ref:
                refs.setdefault(container["name"], set()).add(ref["name"])
    return refs


def test_a_run_reads_the_shared_model_key_unless_another_secret_is_set(monkeypatch):
    monkeypatch.delenv("WIZARD_POC_RUNNER_SECRET", raising=False)
    assert _secret_refs(render_job_manifest(SESSION, "r1", IMAGE))[RUN_CONTAINER] == {
        "gaik-demo-api-keys"
    }


def test_a_run_reads_its_model_settings_from_the_secret_the_setting_names(monkeypatch):
    monkeypatch.setenv("WIZARD_POC_RUNNER_SECRET", "wizard-v2-poc-run-keys")
    for manifest in (
        render_job_manifest(SESSION, "r1", IMAGE),
        render_job_manifest(SESSION, "r1-chk", IMAGE, kind=CHECK_KIND),
    ):
        refs = _secret_refs(manifest)
        assert refs[RUN_CONTAINER] == {"wizard-v2-poc-run-keys"}
        # The package fetch keeps the stack's own token Secret.
        assert refs["fetch-poc"] == {"wizard-v2-token"}


@pytest.mark.parametrize(
    ("value", "shared"),
    [
        (None, True),
        ("", True),
        ("gaik-demo-api-keys", True),
        ("Not_A_Secret_Name", True),  # no run starts with it, and code edits wait
        ("wizard-v2-poc-run-keys", False),
    ],
)
def test_the_runs_use_the_shared_key_unless_the_setting_names_another_secret(
    monkeypatch, value, shared
):
    if value is None:
        monkeypatch.delenv("WIZARD_POC_RUNNER_SECRET", raising=False)
    else:
        monkeypatch.setenv("WIZARD_POC_RUNNER_SECRET", value)

    assert runs_use_shared_key() is shared


@pytest.mark.parametrize("name", ["Has_Upper", "-leading", "a/b", "x" * 300])
def test_a_runner_secret_that_is_not_a_secret_name_is_refused(monkeypatch, name):
    monkeypatch.setenv("WIZARD_POC_RUNNER_SECRET", name)
    with pytest.raises(SandboxNotConfiguredError, match="WIZARD_POC_RUNNER_SECRET"):
        render_job_manifest(SESSION, "r1", IMAGE)
