"""Two stacks in one Rahti project: every manifest deploy.sh applies is instance-scoped.

``deploy.sh`` substitutes ``NAME_PLACEHOLDER`` with ``wizard-v2`` (the staging
stack) or ``wizard-v2-<instance>``. A name that is not built from the
placeholder is shared by every instance in the project — a second stack would
then adopt the staging stack's pods, database, storage, token or image — and
nothing else would notice. These tests render the manifests exactly the way
``deploy.sh manifests`` and ``deploy.sh secrets`` apply them (``deploy.sh
render`` needs no cluster).
"""

import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

OPENSHIFT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "openshift"
DEPLOY = OPENSHIFT_DIR / "deploy.sh"
PROJECT = "proj"
STAGING = ""
SECOND = "s4"

# What deploy.sh applies (in order) plus the secrets file it applies on demand.
MANIFESTS = [
    "rbac.yaml",
    "networkpolicy-sandbox.yaml",
    "postgres.yaml",
    "pvc-sessions.yaml",
    "services.yaml",
    "route.yaml",
    "deployment-api.yaml",
    "deployment-web.yaml",
    "secrets.yaml.example",
]

# The names the staging stack has always had. Rendering with INSTANCE empty
# must reproduce them exactly, or an existing deployment would be duplicated
# instead of updated.
STAGING_RESOURCES = {
    ("ServiceAccount", "wizard-v2-api"),
    ("Role", "wizard-v2-api-sandbox"),
    ("RoleBinding", "wizard-v2-api-sandbox"),
    ("NetworkPolicy", "wizard-v2-poc-run"),
    ("PersistentVolumeClaim", "wizard-v2-db-data"),
    ("Deployment", "wizard-v2-db"),
    ("Service", "wizard-v2-db"),
    ("PersistentVolumeClaim", "wizard-v2-sessions"),
    ("Service", "wizard-v2-web"),
    ("Service", "wizard-v2-api"),
    ("Route", "wizard-v2-web"),
    ("Deployment", "wizard-v2-api"),
    ("Deployment", "wizard-v2-web"),
    ("Secret", "wizard-v2-db"),
    ("Secret", "wizard-v2-web"),
    ("Secret", "wizard-v2-token"),
}


def run_deploy(*args: str, instance: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(DEPLOY), *args],
        capture_output=True,
        text=True,
        env={"PROJECT": PROJECT, "INSTANCE": instance, "PATH": "/usr/bin:/bin"},
    )


def render(manifest: str, instance: str) -> str:
    result = run_deploy("render", manifest, instance=instance)
    assert result.returncode == 0, result.stderr
    return result.stdout


def documents(instance: str) -> list[dict]:
    """Every Kubernetes object the instance consists of, Lists flattened."""
    docs: list[dict] = []
    for manifest in MANIFESTS:
        for doc in yaml.safe_load_all(render(manifest, instance)):
            if doc is None:
                continue
            docs.extend(doc["items"] if doc.get("kind") == "List" else [doc])
    return docs


def named(docs: list[dict]) -> set[tuple[str, str]]:
    return {(d["kind"], d["metadata"]["name"]) for d in docs}


def one(docs: list[dict], kind: str, name: str) -> dict:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def env_of(container: dict) -> dict[str, dict]:
    return {e["name"]: e for e in container["env"]}


def secret_ref(env_entry: dict) -> str:
    return env_entry["valueFrom"]["secretKeyRef"]["name"]


@pytest.fixture(scope="module", params=[STAGING, SECOND], ids=["staging", "second"])
def instance(request) -> str:
    return request.param


@pytest.fixture(scope="module")
def name(instance: str) -> str:
    return "wizard-v2" if instance == STAGING else f"wizard-v2-{instance}"


@pytest.fixture(scope="module")
def docs(instance: str) -> list[dict]:
    return documents(instance)


def test_rendering_leaves_no_placeholders(instance: str) -> None:
    for manifest in MANIFESTS:
        assert "PLACEHOLDER" not in render(manifest, instance), manifest


def test_the_staging_stack_keeps_its_historical_names() -> None:
    assert named(documents(STAGING)) == STAGING_RESOURCES


def test_a_second_instance_is_the_same_stack_under_its_own_prefix() -> None:
    expected = {
        (kind, n.replace("wizard-v2-", f"wizard-v2-{SECOND}-", 1)) for kind, n in STAGING_RESOURCES
    }
    assert named(documents(SECOND)) == expected


def test_a_second_instance_references_nothing_of_the_staging_stack() -> None:
    """The failure this guards against: a name written out in full instead of
    from the placeholder. Comments are dropped by the YAML round-trip, so only
    values count."""
    rendered = yaml.safe_dump_all(documents(SECOND))
    staging_only = re.compile(
        r"(?<![\w-])wizard-v2-(api|web|db|db-data|sessions|token|poc-runner)(?![\w-])"
    )
    assert not staging_only.findall(rendered), staging_only.findall(rendered)


def test_deployments_select_their_own_pods(docs: list[dict]) -> None:
    for d in (d for d in docs if d["kind"] == "Deployment"):
        selector = d["spec"]["selector"]["matchLabels"]
        labels = d["spec"]["template"]["metadata"]["labels"]
        assert selector.items() <= labels.items(), d["metadata"]["name"]


def test_services_select_pods_of_this_instance(docs: list[dict]) -> None:
    pod_labels = [
        d["spec"]["template"]["metadata"]["labels"] for d in docs if d["kind"] == "Deployment"
    ]
    for s in (d for d in docs if d["kind"] == "Service"):
        selector = s["spec"]["selector"]
        assert any(selector.items() <= labels.items() for labels in pod_labels), s["metadata"][
            "name"
        ]


def test_the_route_reaches_this_instances_web(docs: list[dict], name: str) -> None:
    route = one(docs, "Route", f"{name}-web")
    assert route["spec"]["to"]["name"] == f"{name}-web"
    assert route["spec"]["to"]["name"] == one(docs, "Service", f"{name}-web")["metadata"]["name"]
    # No fixed host: OpenShift derives <route>-<project>.…, which is what
    # gives each instance its own URL.
    assert "host" not in route["spec"]


def test_the_web_app_talks_to_this_instances_api(docs: list[dict], name: str) -> None:
    web = one(docs, "Deployment", f"{name}-web")["spec"]["template"]["spec"]["containers"][0]
    env = env_of(web)
    assert env["WIZARD_API_URL"]["value"] == f"http://{name}-api:8100"
    assert secret_ref(env["WIZARD_API_TOKEN"]) == f"{name}-token"
    assert secret_ref(env["NEXT_SERVER_ACTIONS_ENCRYPTION_KEY"]) == f"{name}-web"


def test_the_api_uses_this_instances_database_token_and_storage(
    docs: list[dict], name: str
) -> None:
    api = one(docs, "Deployment", f"{name}-api")["spec"]["template"]["spec"]
    env = env_of(api["containers"][0])
    assert secret_ref(env["WIZARD_DATABASE_URL"]) == f"{name}-db"
    assert secret_ref(env["WIZARD_API_TOKEN"]) == f"{name}-token"
    assert env["WIZARD_INSTANCE_NAME"]["value"] == name
    claims = {
        v["persistentVolumeClaim"]["claimName"]
        for v in api["volumes"]
        if "persistentVolumeClaim" in v
    }
    assert claims == {f"{name}-sessions"}
    # The agent container (T9) runs this instance's image too, not another stack's.
    assert {c["image"] for c in api["containers"]} == {api["containers"][0]["image"]}

    db = one(docs, "Deployment", f"{name}-db")["spec"]["template"]["spec"]
    assert {v["persistentVolumeClaim"]["claimName"] for v in db["volumes"]} == {f"{name}-db-data"}
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert secret_ref(env_of(db["containers"][0])[var]) == f"{name}-db"


def test_the_api_runs_sandbox_jobs_in_this_instances_runner_image(
    docs: list[dict], name: str
) -> None:
    """Otherwise an s4 run executes in staging's runner, with staging's gaik version."""
    api = one(docs, "Deployment", f"{name}-api")["spec"]["template"]["spec"]["containers"][0]
    image = env_of(api)["WIZARD_POC_RUNNER_IMAGE"]["value"]
    assert image.endswith(f"/{name}-poc-runner:latest")
    assert "PLACEHOLDER" not in image


def test_the_secrets_file_serves_this_instance(docs: list[dict], name: str) -> None:
    db_secret = one(docs, "Secret", f"{name}-db")
    assert f"@{name}-db:5432/" in db_secret["stringData"]["database-url"]
    assert one(docs, "Secret", f"{name}-token")["stringData"]["WIZARD_API_TOKEN"]
    assert one(docs, "Secret", f"{name}-web")["stringData"]["NEXT_SERVER_ACTIONS_ENCRYPTION_KEY"]


def test_model_provider_keys_stay_project_wide(docs: list[dict], name: str) -> None:
    """gaik-demo-api-keys is shared with the demo app and every instance; the
    secrets file must not redefine it, or `oc apply` would replace the keys the
    other consumers rely on."""
    api = one(docs, "Deployment", f"{name}-api")["spec"]["template"]["spec"]["containers"][0]
    env = env_of(api)
    for var in (
        "CLAUDE_CODE_USE_FOUNDRY",
        "ANTHROPIC_FOUNDRY_API_KEY",
        "ANTHROPIC_FOUNDRY_RESOURCE",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        # The agent's Phase 4 schema generation calls Azure OpenAI from the
        # api container; without these the wizard stops before any PoC.
        "AZURE_API_KEY",
        "AZURE_ENDPOINT",
        "AZURE_API_VERSION",
        "AZURE_DEPLOYMENT",
    ):
        assert secret_ref(env[var]) == "gaik-demo-api-keys", var
        assert env[var]["valueFrom"]["secretKeyRef"].get("optional") is True, var
    assert ("Secret", "gaik-demo-api-keys") not in named(docs)


def test_the_api_runs_as_its_own_service_account_with_only_the_sandbox_rights(
    docs: list[dict], name: str
) -> None:
    """Jobs, pods and pod logs; no secrets. Without rbac.yaml the api ran as the
    namespace default account and either could not create Jobs or, where that
    account had been given `edit`, could read every Secret in the project."""
    api = one(docs, "Deployment", f"{name}-api")["spec"]["template"]["spec"]
    assert api["serviceAccountName"] == f"{name}-api"
    one(docs, "ServiceAccount", f"{name}-api")
    binding = one(docs, "RoleBinding", f"{name}-api-sandbox")
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": f"{name}-api"}]
    assert binding["roleRef"]["name"] == f"{name}-api-sandbox"
    role = one(docs, "Role", f"{name}-api-sandbox")
    resources = {r for rule in role["rules"] for r in rule["resources"]}
    # jobs/status is its own resource for RBAC: read_namespaced_job_status
    # is Forbidden without it even when `jobs` may be read.
    assert resources == {"jobs", "jobs/status", "pods", "pods/log"}
    assert "secrets" not in resources


def test_images_are_per_instance(docs: list[dict], name: str) -> None:
    for component in ("api", "web"):
        container = one(docs, "Deployment", f"{name}-{component}")["spec"]["template"]["spec"][
            "containers"
        ][0]
        assert (
            container["image"]
            == f"image-registry.apps.2.rahti.csc.fi/{PROJECT}/{name}-{component}:latest"
        )


@pytest.mark.parametrize("bad", ["S4", "s4_x", "-s4", "s4-", "sprint 4"])
def test_an_instance_name_that_is_not_a_dns_label_is_refused(bad: str) -> None:
    result = run_deploy("render", "services.yaml", instance=bad)
    assert result.returncode != 0
    assert "INSTANCE" in result.stdout + result.stderr


def test_render_needs_no_cluster_but_still_needs_a_project() -> None:
    result = subprocess.run(
        ["bash", str(DEPLOY), "render", "services.yaml"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0
    assert "PROJECT" in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The toolkit version is pinned in two images and must be the same in both
# ---------------------------------------------------------------------------

IMPL_DIR = OPENSHIFT_DIR.parents[1]


def _gaik_version_pin(dockerfile: Path) -> str:
    match = re.search(r"^ARG GAIK_VERSION=(\S+)$", dockerfile.read_text(), re.M)
    assert match, f"{dockerfile} has no ARG GAIK_VERSION pin"
    return match.group(1)


def test_the_api_and_the_runner_pin_the_same_gaik_version() -> None:
    """The api generates the extraction schema with gaik (Phase 4) and the
    runner executes the PoC with gaik; two versions would mean a schema the
    run does not read the same way. Bump both with the registry sync."""
    api = _gaik_version_pin(IMPL_DIR / "wizard_api" / "Dockerfile")
    runner = _gaik_version_pin(IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile")
    assert api == runner, f"wizard_api pins gaik {api}, poc-runner pins {runner}"


def test_the_images_pin_the_gaik_version_the_guidance_is_validated_for() -> None:
    """The agent writes PoCs to the guidance synced against
    gaik_validated_version.txt; an older image lacks options the guidance
    uses (RunSettings(citations=...) is 0.8.3+) and those runs fail."""
    validated_file = IMPL_DIR / "solution_wizard" / "gaik_validated_version.txt"
    validated = validated_file.read_text().strip()
    api = _gaik_version_pin(IMPL_DIR / "wizard_api" / "Dockerfile")
    assert api == validated, f"images pin gaik {api}, the guidance is validated for {validated}"


def _gaik_extras(dockerfile: Path) -> set[str]:
    match = re.search(r'^ARG GAIK_EXTRAS="([^"]+)"$', dockerfile.read_text(), re.M)
    assert match, f"{dockerfile} has no ARG GAIK_EXTRAS"
    return {e.strip() for e in match.group(1).split(",") if e.strip()}


def test_the_api_and_the_runner_install_the_same_gaik_extras() -> None:
    """The agent imports the components it designs with inside the api image
    (#256); a run executes them in the runner. An extra present in one and not
    the other means a call the agent could not check, or a run that cannot
    import what the agent checked."""
    api = _gaik_extras(IMPL_DIR / "wizard_api" / "Dockerfile")
    runner = _gaik_extras(IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile")
    assert api == runner, f"only api: {sorted(api - runner)}, only runner: {sorted(runner - api)}"


def _package_pins_beside_gaik(dockerfile: Path) -> dict[str, str]:
    """The packages installed beside gaik, by name, each with its exact version."""
    pip_line = r'^RUN pip install --no-cache-dir "gaik\[[^"]+\]==[^"]+" (.+)$'
    match = re.search(pip_line, dockerfile.read_text(), re.M)
    assert match, f"{dockerfile} has no gaik pip install line"
    pins: dict[str, str] = {}
    for spec in match.group(1).split():
        pin = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!-]*)", spec.strip('"')
        )
        assert pin, f"{dockerfile.parent.name}/Dockerfile installs {spec} without one exact version"
        pins[pin.group(1).lower()] = pin.group(2)
    return pins


def _packages_beside_gaik(dockerfile: Path) -> set[str]:
    return set(_package_pins_beside_gaik(dockerfile))


def test_the_api_and_the_runner_install_the_same_packages_beside_gaik() -> None:
    """The package check looks up a PoC's imports in the api image as a stand-in
    for the runner. A package only the runner has (reportlab before this test)
    holds a PoC back as "not ready" although its run would import it."""
    api = _packages_beside_gaik(IMPL_DIR / "wizard_api" / "Dockerfile")
    runner = _packages_beside_gaik(IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile")
    assert api == runner, f"only api: {sorted(api - runner)}, only runner: {sorted(runner - api)}"


def test_the_api_and_the_runner_pin_the_same_versions_beside_gaik() -> None:
    """Unpinned, the two images resolved these packages at their own build times
    and could drift apart, so the api's package check judged a PoC against other
    versions than its run used. Each is pinned to one exact version, the same in
    both images; bump them together."""
    api = _package_pins_beside_gaik(IMPL_DIR / "wizard_api" / "Dockerfile")
    runner = _package_pins_beside_gaik(IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile")
    differ = {
        name: (api[name], runner[name])
        for name in sorted(set(api) & set(runner))
        if api[name] != runner[name]
    }
    assert not differ, f"api and runner pin different versions (api, runner): {differ}"


def test_the_runner_has_reportlab_for_the_scaffolded_pdf_report() -> None:
    """A PoC whose output types include pdf imports pdf_report.py, which imports
    reportlab. The runner printed "PDF report generation failed: No module named
    'reportlab'" on every such run (s4, 5 Oct 2026). It is installed and the build's
    smoke test imports it, so a missing one fails the build instead of the run."""
    dockerfile = (IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"pip install[^\n]*\breportlab\b", dockerfile)
    smoke = dockerfile.split("importlib.import_module", 1)[0]
    assert '"reportlab"' in smoke


def test_the_runner_and_the_api_both_install_and_smoke_import_pandas() -> None:
    """Agent-written PoCs that compute figures from a spreadsheet import pandas, and
    no gaik extra in 0.8.2 provides it. The package check looks imports up in the
    api image because it mirrors the runner, so both need it, and both builds import
    it so that a missing one fails the build instead of a run."""
    for path in (
        IMPL_DIR / "deploy" / "poc-runner" / "Dockerfile",
        IMPL_DIR / "wizard_api" / "Dockerfile",
    ):
        dockerfile = path.read_text(encoding="utf-8")
        assert re.search(r"pip install[^\n]*\"?pandas", dockerfile), path.name
        smoke = dockerfile.split("importlib.import_module", 1)[0]
        assert '"pandas"' in smoke, path.name
