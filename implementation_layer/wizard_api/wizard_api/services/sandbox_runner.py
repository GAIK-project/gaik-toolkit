"""Run a generated PoC package in an isolated sandbox Job (#91).

The manifest stays the single source of truth for what a run is allowed to do:
this renders `deploy/openshift/sandbox-job.yaml` exactly as
`scripts/submit-sandbox-job.sh` does, then submits it through the Kubernetes API
rather than shelling out to `oc`. The api container has no `oc` binary, and
following a pod's log needs the API anyway, so the script stays for hand-runs
and this is the path the UI uses.

The Kubernetes client is optional, like the Claude SDK in agent_service: the
module imports and its pure parts are testable without a cluster, and the parts
that need one raise a clear error instead of failing at import.
"""

from __future__ import annotations

import codecs
import hashlib
import logging
import os
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised only where the cluster client is installed
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes import watch as k8s_watch

    _K8S_AVAILABLE = True
except ImportError:  # pragma: no cover - the common case in unit tests
    k8s_client = k8s_config = k8s_watch = None  # type: ignore[assignment]
    _K8S_AVAILABLE = False

import yaml

_HERE = Path(__file__).resolve()
_MANIFEST_RELATIVE = Path("deploy") / "openshift" / "sandbox-job.yaml"


def resolve_manifest() -> Path | None:
    """Locate sandbox-job.yaml (env override wins).

    Not a fixed number of `parents[...]`: in a checkout this file sits four
    levels below implementation_layer, and in the image it sits at
    /app/wizard_api/services, where that same arithmetic lands on "/" — the
    mistake #180 was about, in a different file. Each candidate is checked for
    existence instead, and a deployment that has the manifest somewhere else
    sets the variable.
    """
    env = os.getenv("WIZARD_SANDBOX_MANIFEST", "").strip()
    if env:
        return Path(env)

    def ancestor(levels: int, *parts: str | Path) -> Path | None:
        """`_HERE` has fewer ancestors in the image than in a checkout, and
        indexing past the root raises rather than returning nothing."""
        parents = _HERE.parents
        if levels >= len(parents):
            return None
        return parents[levels].joinpath(*parts)

    candidates = (
        # Installed image: the Dockerfile copies the manifest beside the app.
        Path("/manifests/sandbox-job.yaml"),
        # Checkout: …/wizard_api/wizard_api/services → implementation_layer.
        ancestor(3, _MANIFEST_RELATIVE),
        # Editable install from the repo root.
        ancestor(4, "implementation_layer", _MANIFEST_RELATIVE),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    return None


JOB_NAME_PREFIX = "wizard-v2-poc-run-"

#: How long the run container may take to start once its pod exists: the init
#: container's package fetch plus, on a node that has not seen it yet, the pull
#: of the runner image (hundreds of MB). Separate from the 120 s wait for the pod
#: itself, which it used to share. The Job's own activeDeadlineSeconds bounds the
#: run proper.
CONTAINER_START_TIMEOUT_SECONDS = 300
RUN_CONTAINER = "poc-run"

#: The manifest ships a registry placeholder so the file is not tied to one
#: OpenShift project. Submitting it would create a Job that dies on
#: ImagePullBackOff, so it is refused before anything is created — the same
#: check the shell script makes.
_IMAGE_PLACEHOLDER = "PROJECT_PLACEHOLDER"


#: Label the manifest puts on every Job (and its pod) naming the session it runs.
SESSION_LABEL = "wizard-v2/session-id"

#: Label naming what kind of run a Job is. Absent means a real run of the package;
#: ``check`` is the preflight (#252), which calls no model and must never be
#: recorded as the successful run that opens the deployable download.
RUN_KIND_LABEL = "wizard-v2/run-kind"
CHECK_KIND = "check"

#: Run kind of a case run: the package on one case's inputs, not on its own
#: sample input. Like the preflight, never the run that opens the deployable.
CASE_KIND = "case"

#: Label naming the case a run belongs to. A case run fetches the package with
#: that case's own inputs in place of ``sample_input/`` (case_service).
CASE_LABEL = "wizard-v2/case-id"

#: Labels the API adds to the Job itself, so that it can count the runs of its
#: own stack (staging and s4 share one project) and of one user, and find a
#: preflight of the same package again. The user is a digest: a label value
#: cannot hold an email address.
APP_LABEL = "app"
APP_NAME = "wizard-v2-poc-run"
INSTANCE_LABEL = "wizard-v2/instance"
USER_LABEL = "wizard-v2/user"
VERSION_LABEL = "wizard-v2/package-version"
#: A digest of the runner image the Job runs, so a preflight is reused only on
#: the image it passed on. Image references do not fit a label value as such.
IMAGE_LABEL = "wizard-v2/runner-image"
_LABEL_VALUE = re.compile(r"^[a-z0-9]{1,63}$")
CHECK_DEADLINE_SECONDS = 180

logger = logging.getLogger(__name__)

#: Held around count-then-create, and around reuse-or-create of a preflight. The
#: api runs as one replica (the sessions volume is RWO) and FastAPI runs its sync
#: route handlers in a thread pool, so parallel requests of this one process are
#: what could both pass the count before either Job exists. Re-entrant because
#: ``start_check`` creates its Job through ``create_run``.
_CREATE_LOCK = threading.RLock()


class SandboxNotConfiguredError(RuntimeError):
    """Raised when the cluster client or the runner image is missing."""


class RunLimitError(RuntimeError):
    """This stack, or this user, already has as many runs going as it may.

    Every run and preflight is a Job that reserves CPU and memory from the
    project's shared quota, which the apps in the project need for their own
    rollouts. The caller is told to try again once a run has finished.
    """

    retry_after_s = 30


class RunNotFoundError(LookupError):
    """The run does not exist, or belongs to another session.

    One error for both, like the 404 for a session that is not the caller's:
    a caller must not be able to tell a stranger's run from a missing one.
    """


def kubernetes_available() -> bool:
    return _K8S_AVAILABLE


def runner_image() -> str | None:
    image = os.getenv("WIZARD_POC_RUNNER_IMAGE", "").strip()
    return image or None


DEFAULT_RUNNER_SECRET = "gaik-demo-api-keys"
RUNNER_SECRET_ENV = "WIZARD_POC_RUNNER_SECRET"
_SECRET_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]{0,251}[a-z0-9])?$")


def runner_secret() -> str:
    """The Secret a run reads its model settings from (AZURE_API_KEY and the rest).

    The project's shared ``gaik-demo-api-keys`` unless ``WIZARD_POC_RUNNER_SECRET``
    names another one, for example one holding a key with its own spending cap.
    The api and the agent keep the shared key; only the runs change. A name that
    is not a Kubernetes Secret name is refused rather than ignored.
    """
    name = os.getenv(RUNNER_SECRET_ENV, "").strip()
    if not name:
        return DEFAULT_RUNNER_SECRET
    if not _SECRET_NAME.match(name):
        raise SandboxNotConfiguredError(f"{RUNNER_SECRET_ENV} is not a Secret name")
    return name


def runs_use_shared_key() -> bool:
    """Whether the test runs read their model settings from the project's shared Secret.

    While they do, code a user writes in the PoC tab's editor is not saved
    (``poc_service.package_file_read_only``): user-written code runs only with
    a runner key of its own. A ``WIZARD_POC_RUNNER_SECRET`` that is not a
    Secret name counts as the shared one; no run starts with it either.
    """
    try:
        return runner_secret() == DEFAULT_RUNNER_SECRET
    except SandboxNotConfiguredError:
        return True


def instance_name() -> str:
    """Resource-name prefix of this stack (``wizard-v2`` or ``wizard-v2-<instance>``).

    deploy.sh sets it on the api Deployment; the Job addresses its own stack's api
    Service and token Secret with it.
    """
    return os.getenv("WIZARD_INSTANCE_NAME", "").strip() or "wizard-v2"


def sandbox_namespace() -> str | None:
    """The project the Jobs go into. In-cluster this is the pod's own namespace."""
    explicit = os.getenv("WIZARD_SANDBOX_NAMESPACE", "").strip()
    if explicit:
        return explicit
    token_ns = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if token_ns.is_file():
        return token_ns.read_text(encoding="utf-8").strip() or None
    return None


#: Seconds the cluster gets to accept a new Job.
CREATE_TIMEOUT_S = 30


def new_run_id(session_id: str, now: datetime | None = None) -> str:
    """A DNS-1123-safe run id, matching submit-sandbox-job.sh.

    Job names are DNS-1123 labels, so the session id contributes only its
    lowercase alphanumerics and only its last eight characters — enough to tell
    two sessions apart in `oc get jobs` without making the name illegal.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    tail = re.sub(r"[^a-z0-9]", "", session_id.lower())[-8:]
    return f"{stamp}-{tail}" if tail else stamp


def user_label(user_id: str) -> str:
    """The value of ``USER_LABEL`` for one user: a short digest of the id."""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def image_label(image: str) -> str:
    """The value of ``IMAGE_LABEL`` for one runner image reference."""
    return hashlib.sha256(image.encode("utf-8")).hexdigest()[:16]


def _manifest_image(manifest: dict[str, Any]) -> str | None:
    """The image the rendered Job runs the package in."""
    for container in manifest["spec"]["template"]["spec"].get("containers") or []:
        if container.get("name") == RUN_CONTAINER:
            return container.get("image")
    return None


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


def max_active_runs() -> int:
    """Runs and preflights of this stack that may be unfinished at once."""
    return _int_env("WIZARD_MAX_ACTIVE_RUNS", 4)


def max_active_runs_per_user() -> int:
    """Runs and preflights of one user that may be unfinished at once."""
    return _int_env("WIZARD_MAX_ACTIVE_RUNS_PER_USER", 2)


def job_name(run_id: str) -> str:
    return f"{JOB_NAME_PREFIX}{run_id}"


def render_job_manifest(
    session_id: str,
    run_id: str,
    image: str,
    template: Path | None = None,
    kind: str | None = None,
    case_id: str | None = None,
    user_id: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """The Job for one run, rendered from the manifest the reviewer approved.

    Substitution is textual and identical to the shell script's `sed`, so the
    two paths cannot drift into producing different Jobs from the same file.
    """
    path = template or resolve_manifest()
    if path is None or not path.is_file():
        raise SandboxNotConfiguredError(
            "sandbox Job manifest not found — set WIZARD_SANDBOX_MANIFEST to "
            "deploy/openshift/sandbox-job.yaml"
        )
    if _IMAGE_PLACEHOLDER in image:
        raise SandboxNotConfiguredError(
            "the runner image still carries the registry placeholder; set "
            "WIZARD_POC_RUNNER_IMAGE to the image you built"
        )

    text = path.read_text(encoding="utf-8")
    for placeholder, value in (
        ("SESSION_ID_PLACEHOLDER", session_id),
        ("RUN_ID_PLACEHOLDER", run_id),
        ("IMAGE_PLACEHOLDER", image),
        ("NAME_PLACEHOLDER", instance_name()),
    ):
        text = text.replace(placeholder, value)
    manifest = yaml.safe_load(text)
    labels = manifest["metadata"].setdefault("labels", {})
    labels[INSTANCE_LABEL] = instance_name()
    labels[IMAGE_LABEL] = image_label(_manifest_image(manifest) or image)
    if user_id:
        labels[USER_LABEL] = user_label(user_id)
    if version:
        if not _LABEL_VALUE.match(version):
            raise ValueError("not a package version")
        labels[VERSION_LABEL] = version
    if kind == CHECK_KIND:
        _make_preflight(manifest)
    if case_id:
        _make_case_run(manifest, case_id)
    if user_id:
        _set_user(manifest, user_id)
    _use_runner_secret(manifest, runner_secret())
    return manifest


def _use_runner_secret(manifest: dict[str, Any], secret: str) -> None:
    """Point the run container's model settings at ``secret``.

    Only references to the shared model-key Secret change; the package fetch
    keeps its own token Secret. Done on the parsed manifest, like ``_set_user``.
    """
    if secret == DEFAULT_RUNNER_SECRET:
        return
    for container in manifest["spec"]["template"]["spec"].get("containers") or []:
        for entry in container.get("env") or []:
            ref = (entry.get("valueFrom") or {}).get("secretKeyRef")
            if ref and ref.get("name") == DEFAULT_RUNNER_SECRET:
                ref["name"] = secret


def _labels(job: Any) -> dict[str, str]:
    return getattr(getattr(job, "metadata", None), "labels", None) or {}


def _unfinished(job: Any) -> bool:
    """A Job that still holds its share of the quota: not finished, not being deleted."""
    if getattr(getattr(job, "metadata", None), "deletion_timestamp", None):
        return False
    return not status_from_job("", job).finished


def _set_user(manifest: dict[str, Any], user_id: str) -> None:
    """Tell the package fetch which user it acts for (``X-Wizard-User-Id``).

    Set on the parsed manifest as an environment variable, never pasted into its
    text: the id then reaches the shell only as the value of ``$WIZARD_USER_ID``
    inside double quotes, so it cannot become YAML or a command.
    """
    if not user_id.strip() or any(c in user_id for c in "\r\n\x00"):
        raise ValueError("not a user id")
    for container in manifest["spec"]["template"]["spec"].get("initContainers") or []:
        if container.get("name") == "fetch-poc":
            env = [e for e in container.setdefault("env", []) if e.get("name") != "WIZARD_USER_ID"]
            env.append({"name": "WIZARD_USER_ID", "value": user_id})
            container["env"] = env


def _make_case_run(manifest: dict[str, Any], case_id: str) -> None:
    """Point the package fetch at one case's inputs, and label the Job with the case.

    The rest of the Job is the reviewed manifest unchanged: same image, limits
    and run command. The fetch URL gains ``?case=<id>``, which the package
    download answers with that case's inputs as ``sample_input/``.
    """
    if not re.fullmatch(r"[0-9a-f-]{36}", case_id):
        raise ValueError(f"not a case id: {case_id!r}")
    for meta in (manifest["metadata"], manifest["spec"]["template"].setdefault("metadata", {})):
        labels = meta.setdefault("labels", {})
        labels[CASE_LABEL] = case_id
        labels[RUN_KIND_LABEL] = CASE_KIND
    rewritten = 0
    for container in manifest["spec"]["template"]["spec"].get("initContainers") or []:
        command = container.get("command") or []
        for i, part in enumerate(command):
            if isinstance(part, str) and '/poc"' in part:
                command[i] = part.replace('/poc"', f'/poc?case={case_id}"')
                rewritten += 1
    if rewritten != 1:
        raise SandboxNotConfiguredError(
            "the sandbox manifest's package fetch was not found; a case run cannot "
            "be pointed at its inputs"
        )


def _make_preflight(manifest: dict[str, Any]) -> None:
    """Turn a run Job into the preflight: same fetch, same image, same sandbox
    limits, but the container runs the check script instead of ``run_poc.py``."""
    from wizard_api.services.preflight_script import PREFLIGHT_SCRIPT

    manifest["metadata"].setdefault("labels", {})[RUN_KIND_LABEL] = CHECK_KIND
    spec = manifest["spec"]
    spec["activeDeadlineSeconds"] = CHECK_DEADLINE_SECONDS
    template = spec["template"]
    template.setdefault("metadata", {}).setdefault("labels", {})[RUN_KIND_LABEL] = CHECK_KIND
    for container in template["spec"]["containers"]:
        if container.get("name") == RUN_CONTAINER:
            container["command"] = ["python", "-c", PREFLIGHT_SCRIPT]
            container.pop("args", None)


@dataclass(frozen=True)
class RunStatus:
    """Where a run got to. `phase` is what the UI shows."""

    run_id: str
    phase: str  # pending | running | succeeded | failed | timeout | unknown
    exit_code: int | None = None
    message: str | None = None

    @property
    def finished(self) -> bool:
        return self.phase in {"succeeded", "failed", "timeout"}


def status_from_job(run_id: str, job: Any) -> RunStatus:
    """Read a Job's status the way the user needs to hear it.

    A Job that hit `activeDeadlineSeconds` reports failure with a distinct
    reason, and "your run was cut off at ten minutes" is a different thing to
    tell someone than "your PoC failed", so the two are not collapsed.
    """
    status = getattr(job, "status", None)
    if status is None:
        return RunStatus(run_id, "unknown")

    for condition in getattr(status, "conditions", None) or []:
        if getattr(condition, "type", None) == "Failed":
            reason = getattr(condition, "reason", "") or ""
            if reason == "DeadlineExceeded":
                return RunStatus(
                    run_id,
                    "timeout",
                    message="the run passed its ten-minute limit and was stopped",
                )
            return RunStatus(run_id, "failed", message=getattr(condition, "message", None))

    if getattr(status, "succeeded", None):
        return RunStatus(run_id, "succeeded", exit_code=0)
    if getattr(status, "failed", None):
        return RunStatus(run_id, "failed")
    if getattr(status, "active", None):
        return RunStatus(run_id, "running")
    return RunStatus(run_id, "pending")


def _run_container_state(pod: Any) -> str:
    """``started`` (running or already finished), ``never`` (the pod failed
    before the run container could start), or ``waiting``."""
    status = getattr(pod, "status", None)
    for container in getattr(status, "container_statuses", None) or []:
        if getattr(container, "name", None) != RUN_CONTAINER:
            continue
        state = getattr(container, "state", None)
        if getattr(state, "running", None) or getattr(state, "terminated", None):
            return "started"
    if getattr(status, "phase", None) == "Failed":
        return "never"
    return "waiting"


def _lines(chunks) -> Iterator[str]:
    """Whole log lines from a stream of chunks that split wherever they like.

    A chunk ends where the network read ended, not at a newline, and may even
    cut a multi-byte character. Splitting each chunk on its own turned one long
    line into two: the exception line a failed run ends with came out as
    "ValueError" and the rest of it as a separate line, so the reason the PoC
    tab showed was the bare exception name.
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    for chunk in chunks:
        text = decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
        pending += text
        *complete, pending = pending.split("\n")
        for line in complete:
            yield line.rstrip("\r")
    pending += decoder.decode(b"", final=True)
    if pending:
        yield pending.rstrip("\r")


class SandboxRunner:
    """Creates sandbox Jobs and follows their output.

    `client` is injectable so the tests can drive the whole lifecycle without a
    cluster; in production it is built from the in-cluster service account.
    """

    def __init__(
        self,
        *,
        namespace: str | None = None,
        image: str | None = None,
        batch: Any = None,
        core: Any = None,
        template: Path | None = None,
    ) -> None:
        self.namespace = namespace or sandbox_namespace()
        self.image = image or runner_image()
        self.template = template
        self._batch = batch
        self._core = core

    # -- wiring ---------------------------------------------------------------

    def _require_config(self) -> None:
        if self.namespace is None:
            raise SandboxNotConfiguredError(
                "no sandbox namespace — set WIZARD_SANDBOX_NAMESPACE, or run in-cluster"
            )
        if not self.image:
            raise SandboxNotConfiguredError(
                "no runner image — set WIZARD_POC_RUNNER_IMAGE to the image built by "
                "deploy.sh poc-runner"
            )

    def _load_clients(self) -> None:
        if self._batch is not None and self._core is not None:
            return
        if not _K8S_AVAILABLE:
            raise SandboxNotConfiguredError(
                "the kubernetes client is not installed (pip install 'wizard-api[sandbox]')"
            )
        try:
            k8s_config.load_incluster_config()
        except Exception:  # noqa: BLE001 - falls back to a developer kubeconfig
            k8s_config.load_kube_config()
        self._batch = self._batch or k8s_client.BatchV1Api()
        self._core = self._core or k8s_client.CoreV1Api()

    # -- lifecycle ------------------------------------------------------------

    def create_run(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        kind: str | None = None,
        case_id: str | None = None,
        user_id: str | None = None,
        version: str | None = None,
    ) -> str:
        """Submit one run and return its id. The Job fetches the package itself.

        ``kind="check"`` submits the preflight instead of a run of the package;
        ``case_id`` runs the package on that case's inputs; ``version`` labels a
        preflight with the package version it checks.

        Raises ``RunLimitError`` when this stack or this user already has
        ``max_active_runs`` / ``max_active_runs_per_user`` runs unfinished.
        """
        self._require_config()
        self._load_clients()
        rid = run_id or new_run_id(session_id)
        if kind == CHECK_KIND and not rid.endswith("-chk"):
            rid = f"{rid}-chk"
        manifest = render_job_manifest(
            session_id,
            rid,
            self.image,
            self.template,
            kind,
            case_id=case_id,
            user_id=user_id,
            version=version,
        )
        # Count and create as one step: two requests that both counted before
        # either Job existed would both get one (8 of 8 did in a test).
        with _CREATE_LOCK:
            self._check_capacity(user_id, session_id=session_id, kind=kind)
            # Bounded well under case_service.CLAIM_MAX_AGE: a case's claim may only
            # go stale once the request that took it has given up on its Job.
            self._batch.create_namespaced_job(
                namespace=self.namespace, body=manifest, _request_timeout=CREATE_TIMEOUT_S
            )
        return rid

    def start_check(self, session_id: str, version: str, *, user_id: str | None = None) -> dict:
        """Reuse this version's preflight, or start one after removing superseded ones.

        Returns ``run_id``, ``phase`` and ``reused``. Under the creation lock, so
        two page loads of the same version get the same Job, and starting a
        preflight first deletes this session's unfinished preflights of any other
        package version or runner image: nothing reads their result any more,
        and each would hold one of the user's run slots for up to
        ``CHECK_DEADLINE_SECONDS``.
        """
        with _CREATE_LOCK:
            existing = self.reusable_check(session_id, version)
            if existing is not None:
                try:
                    return {
                        "run_id": existing,
                        "phase": self.status(existing).phase,
                        "reused": True,
                    }
                except RunNotFoundError:
                    # Reaped between the listing and the read: there is nothing to reuse.
                    pass
            self._delete_superseded_checks(session_id, version)
            run_id = self.create_run(session_id, kind=CHECK_KIND, user_id=user_id, version=version)
        return {"run_id": run_id, "phase": "pending", "reused": False}

    def _current_image_label(self, session_id: str) -> str:
        """``IMAGE_LABEL`` of the Job a preflight would get now, from the rendered manifest."""
        manifest = render_job_manifest(
            session_id, "probe-chk", self.image, self.template, CHECK_KIND
        )
        return manifest["metadata"]["labels"][IMAGE_LABEL]

    def _delete_superseded_checks(self, session_id: str, version: str) -> None:
        image = self._current_image_label(session_id)
        jobs = self._jobs(**{SESSION_LABEL: session_id, RUN_KIND_LABEL: CHECK_KIND})
        for job in jobs:
            labels = _labels(job)
            current = labels.get(VERSION_LABEL) == version and labels.get(IMAGE_LABEL) == image
            if current or not _unfinished(job):
                continue
            name = job.metadata.name
            try:
                self._batch.delete_namespaced_job(
                    name=name, namespace=self.namespace, propagation_policy="Background"
                )
            except Exception as exc:  # noqa: BLE001 - gone already, or the deadline ends it
                if getattr(exc, "status", None) != 404:
                    logger.warning("could not delete a superseded preflight %s: %s", name, exc)

    def active_jobs(self) -> int:
        """How many of this stack's Jobs are unfinished, preflights included."""
        self._require_config()
        self._load_clients()
        return sum(1 for j in self._jobs() if _unfinished(j))

    def _jobs(self, **labels: str) -> list[Any]:
        selector = ",".join(
            f"{k}={v}"
            for k, v in {APP_LABEL: APP_NAME, INSTANCE_LABEL: instance_name(), **labels}.items()
        )
        return self._batch.list_namespaced_job(
            namespace=self.namespace, label_selector=selector, _request_timeout=CREATE_TIMEOUT_S
        ).items

    def _check_capacity(
        self, user_id: str | None, *, session_id: str | None = None, kind: str | None = None
    ) -> None:
        """Refuse a new Job while too many of this stack's are unfinished.

        Counted from the cluster, so a restart cannot forget a run. A Job from
        before these labels is not counted; it is gone within its ten-minute
        deadline.

        The stack-wide count includes every unfinished Job, preflights too,
        because each holds quota. For the user's own count, a run or case run
        of a session does not count that session's own preflight: the preflight
        checks the package the user is about to run, there is at most one per
        session (``start_check`` deletes superseded ones), and it ends within
        ``CHECK_DEADLINE_SECONDS``. Without this, a preflight and one run elsewhere
        were enough to refuse the user's Run.
        """
        active = [j for j in self._jobs() if _unfinished(j)]
        if len(active) >= max_active_runs():
            raise RunLimitError("the sandbox is busy; try again in a minute")
        if user_id:
            mine = user_label(user_id)

            def counts(job: Any) -> bool:
                labels = _labels(job)
                if labels.get(USER_LABEL) != mine:
                    return False
                own_check = (
                    kind != CHECK_KIND
                    and session_id is not None
                    and labels.get(SESSION_LABEL) == session_id
                    and labels.get(RUN_KIND_LABEL) == CHECK_KIND
                )
                return not own_check

            if sum(1 for j in active if counts(j)) >= max_active_runs_per_user():
                raise RunLimitError(
                    "you already have as many runs going as you may; wait for one to finish"
                )

    def reusable_check(self, session_id: str, version: str) -> str | None:
        """The newest preflight of this package version that has not failed, if any.

        Opening the PoC tab asks for a preflight on every page load; while a
        Job of the same version is going or has passed (finished Jobs stay for
        an hour), that one answers instead of a new Job. Only a Job of the
        runner image a new preflight would use counts: one that passed on the
        image before a rollout says nothing about the image runs now use.
        """
        if not _LABEL_VALUE.match(version):
            return None
        self._require_config()
        self._load_clients()
        jobs = self._jobs(
            **{
                SESSION_LABEL: session_id,
                RUN_KIND_LABEL: CHECK_KIND,
                VERSION_LABEL: version,
                IMAGE_LABEL: self._current_image_label(session_id),
            }
        )
        usable = [
            j
            for j in jobs
            if not getattr(j.metadata, "deletion_timestamp", None)
            and status_from_job("", j).phase not in {"failed", "timeout"}
        ]
        if not usable:
            return None
        newest = max(usable, key=lambda j: str(getattr(j.metadata, "creation_timestamp", "")))
        return newest.metadata.name.removeprefix(JOB_NAME_PREFIX)

    def status(self, run_id: str, *, session_id: str | None = None) -> RunStatus:
        """Where a run got to. With ``session_id``, only if that session started it."""
        self._require_config()
        self._load_clients()
        job = self._read_job(run_id)
        if session_id is not None:
            self._require_run_of(job, run_id, session_id)
        return status_from_job(run_id, job)

    def final_status(
        self, run_id: str, *, wait_seconds: float = 30.0, poll_seconds: float = 1.0
    ) -> RunStatus:
        """The status once the Job has settled, for the end of a log stream.

        The log of a finished run ends the moment its container exits; the Job's
        own ``status`` follows a second or two later, once the controller has
        seen the pod finish. Reading it right at the end of the log returned
        ``running`` for a run that had succeeded: the stream's closing frame said
        the run was still going, and ``last_successful_run`` was never recorded,
        so the deployable package never opened from a live run (it did when the
        stream was attached afterwards). Wait, bounded, for a terminal phase.
        """
        deadline = time.monotonic() + wait_seconds
        while True:
            status = self.status(run_id)
            if status.finished or time.monotonic() >= deadline:
                return status
            time.sleep(poll_seconds)

    def check_run_of_session(self, run_id: str, session_id: str) -> None:
        """Raise ``RunNotFoundError`` unless ``session_id`` started this run (B3, #143).

        The Job carries the session in its ``wizard-v2/session-id`` label, set
        from the manifest at creation. Without this check a run id is just a
        string the caller chose: a successful run of one session could be
        recorded as the successful run of another, which is what opens the
        deployable download.
        """
        self.status(run_id, session_id=session_id)

    def run_kind(self, run_id: str) -> str | None:
        """``check`` for a preflight, ``case`` for a case run, None for a run of the package."""
        self._require_config()
        self._load_clients()
        metadata = getattr(self._read_job(run_id), "metadata", None)
        return (getattr(metadata, "labels", None) or {}).get(RUN_KIND_LABEL)

    def check_version(self, run_id: str) -> str | None:
        """The package version a preflight looked at, which may no longer be the current one."""
        self._require_config()
        self._load_clients()
        metadata = getattr(self._read_job(run_id), "metadata", None)
        return (getattr(metadata, "labels", None) or {}).get(VERSION_LABEL)

    def _read_job(self, run_id: str) -> Any:
        try:
            return self._batch.read_namespaced_job_status(
                name=job_name(run_id), namespace=self.namespace
            )
        except Exception as exc:  # noqa: BLE001 - only the 404 is interpreted here
            if getattr(exc, "status", None) == 404:
                raise RunNotFoundError(run_id) from exc
            raise

    @staticmethod
    def _require_run_of(job: Any, run_id: str, session_id: str) -> None:
        metadata = getattr(job, "metadata", None)
        labels = getattr(metadata, "labels", None) or {}
        if labels.get(SESSION_LABEL) != session_id:
            raise RunNotFoundError(run_id)

    def _run_pod(self, run_id: str) -> str | None:
        pods = self._core.list_namespaced_pod(
            namespace=self.namespace, label_selector=f"job-name={job_name(run_id)}"
        )
        items = getattr(pods, "items", None) or []
        return getattr(items[0].metadata, "name", None) if items else None

    def stream_logs(self, run_id: str, *, poll_seconds: float = 1.0) -> Iterator[str]:
        """Yield log lines as the run produces them.

        The acceptance criterion is that output arrives *during* the run, not at
        the end, so this follows the pod's log rather than reading it once the
        Job is done. A pod takes a moment to be scheduled, so the wait for one
        is part of the stream instead of an error.
        """
        self._require_config()
        self._load_clients()

        pod = None
        deadline = time.monotonic() + 120
        while pod is None and time.monotonic() < deadline:
            pod = self._run_pod(run_id)
            if pod is None:
                time.sleep(poll_seconds)
        if pod is None:
            raise SandboxNotConfiguredError(f"no pod appeared for run {run_id}")
        self._wait_for_run_container(
            pod, run_id, poll_seconds, time.monotonic() + CONTAINER_START_TIMEOUT_SECONDS
        )

        stream = self._core.read_namespaced_pod_log(
            name=pod,
            namespace=self.namespace,
            container=RUN_CONTAINER,
            follow=True,
            _preload_content=False,
        )
        yield from _lines(stream.stream())

    def _wait_for_run_container(
        self, pod: str, run_id: str, poll_seconds: float, deadline: float
    ) -> None:
        """Hold the stream until the run container exists as a process.

        A pod is listed as soon as it is scheduled, but its log can be read only
        once the init container (the package fetch) has finished and ``poc-run``
        has started; before that the cluster answers 400 ``PodInitializing``.
        The UI opens the stream the moment a run is created, so it always landed
        in that window, got the error, and never reached the status check that
        records a successful run (#143) — the Job completed, the session never
        learned it. The wait belongs to the stream, like the wait for the pod.
        """
        while True:
            state = _run_container_state(self._core.read_namespaced_pod(pod, self.namespace))
            if state == "started":
                return
            if state == "never":
                raise SandboxNotConfiguredError(
                    f"run {run_id} did not start: its package fetch step failed"
                )
            if time.monotonic() >= deadline:
                raise SandboxNotConfiguredError(
                    f"the run container of {run_id} did not start in time"
                )
            time.sleep(poll_seconds)

    def read_log(self, run_id: str) -> str:
        """The run container's whole log, once the run has finished.

        A case reads its result from it: the run prints its output files between
        the output markers. Read while the Job still exists (it is reaped an hour
        after it ends), which the case UI does as soon as the run settles.
        """
        self._require_config()
        self._load_clients()
        pod = self._run_pod(run_id)
        if pod is None:
            raise RunNotFoundError(run_id)
        # Unpreloaded: the client's own decoding returns the log as the repr of
        # a string (newlines as "\\n"), and the output files could not be found.
        response = self._core.read_namespaced_pod_log(
            name=pod, namespace=self.namespace, container=RUN_CONTAINER, _preload_content=False
        )
        data = getattr(response, "data", response)
        return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)

    def delete_session_runs(self, session_id: str) -> None:
        """Remove every Job of a session, running or finished, with its pods and logs."""
        self._require_config()
        self._load_clients()
        for job in self._jobs(**{SESSION_LABEL: session_id}):
            try:
                self._batch.delete_namespaced_job(
                    name=job.metadata.name,
                    namespace=self.namespace,
                    propagation_policy="Background",
                )
            except Exception as exc:  # noqa: BLE001 - only "already gone" is fine here
                if getattr(exc, "status", None) != 404:
                    raise

    def delete_run(self, run_id: str) -> None:
        """Remove a Job early. Finished Jobs reap themselves via ttlSecondsAfterFinished."""
        self._require_config()
        self._load_clients()
        self._batch.delete_namespaced_job(
            name=job_name(run_id), namespace=self.namespace, propagation_policy="Background"
        )
