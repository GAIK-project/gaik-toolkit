"""The sandbox Job's isolation settings (S5-1 / #89).

The PoC this Job runs is code an agent generated from a user's description, so
the isolation is the feature, not a detail. These tests read the rendered
manifest and fail if any of it is weakened — a manifest is easy to relax by
accident and nothing else would notice.
"""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

OPENSHIFT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "openshift"
TEMPLATE = OPENSHIFT_DIR / "sandbox-job.yaml"
SUBMIT = OPENSHIFT_DIR / "scripts" / "submit-sandbox-job.sh"
SESSION_ID = "7f3a9c21-0000-4000-8000-abc123456789"
IMAGE = "registry.example.invalid/wizard-v2-poc-runner:test"


@pytest.fixture(scope="module")
def job() -> dict:
    """The manifest as submit-sandbox-job.sh renders it."""
    out = subprocess.run(
        [str(SUBMIT), SESSION_ID, IMAGE],
        capture_output=True,
        text=True,
        check=True,
        env={"DRY_RUN": "1", "PATH": "/usr/bin:/bin"},
    )
    return yaml.safe_load(out.stdout)


@pytest.fixture(scope="module")
def pod_spec(job: dict) -> dict:
    return job["spec"]["template"]["spec"]


def test_rendering_leaves_no_placeholders(job: dict) -> None:
    rendered = yaml.safe_dump(job)
    assert "PLACEHOLDER" not in rendered
    assert job["metadata"]["labels"]["wizard-v2/session-id"] == SESSION_ID


def test_run_is_killed_after_ten_minutes(job: dict) -> None:
    assert job["spec"]["activeDeadlineSeconds"] == 600


def test_a_failed_run_is_not_retried(job: dict, pod_spec: dict) -> None:
    assert job["spec"]["backoffLimit"] == 0
    assert pod_spec["restartPolicy"] == "Never"


def test_every_container_declares_cpu_and_memory_limits(pod_spec: dict) -> None:
    containers = pod_spec["containers"] + pod_spec.get("initContainers", [])
    assert containers
    for c in containers:
        limits = c["resources"]["limits"]
        assert limits["cpu"], c["name"]
        assert limits["memory"], c["name"]


def test_the_poc_cannot_reach_the_kubernetes_api(pod_spec: dict) -> None:
    assert pod_spec["automountServiceAccountToken"] is False


def test_containers_run_unprivileged_as_non_root(pod_spec: dict) -> None:
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    for c in pod_spec["containers"] + pod_spec.get("initContainers", []):
        sc = c["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False, c["name"]
        assert sc["readOnlyRootFilesystem"] is True, c["name"]
        assert sc["capabilities"]["drop"] == ["ALL"], c["name"]
        assert not sc.get("privileged"), c["name"]


def test_nothing_from_the_host_or_the_cluster_storage_is_mounted(pod_spec: dict) -> None:
    """The acceptance criterion: a run touches no host filesystem.

    Scratch space is emptyDir, which lives and dies with the pod. A hostPath
    would expose a node directory, and a PVC would hand the run the api's
    session storage.
    """
    for volume in pod_spec["volumes"]:
        assert set(volume) <= {"name", "emptyDir"}, volume
        assert volume["emptyDir"]["sizeLimit"], volume["name"]


def test_the_run_container_gets_no_cluster_secrets_beyond_the_model_settings(
    pod_spec: dict,
) -> None:
    """The service token belongs to the fetch step, not to the generated code.

    The model settings are the key and where to send it: gaik's Azure config
    refuses to start without AZURE_ENDPOINT, so the key alone failed every run.
    """
    run = next(c for c in pod_spec["containers"] if c["name"] == "poc-run")
    secret_keys = {
        e["valueFrom"]["secretKeyRef"]["key"]
        for e in run["env"]
        if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
    }
    assert secret_keys == {
        "AZURE_API_KEY",
        "AZURE_ENDPOINT",
        "AZURE_API_VERSION",
        "AZURE_DEPLOYMENT",
    }
    # A missing key must not keep the pod from starting: the PoC then reports
    # which setting it lacks, which is what the run log is for.
    for e in run["env"]:
        ref = e.get("valueFrom", {}).get("secretKeyRef")
        if ref:
            assert ref["name"] == "gaik-demo-api-keys" and ref["optional"] is True, e["name"]


def test_the_run_container_starts_the_entrypoint_the_scaffolder_writes(
    pod_spec: dict,
) -> None:
    """``poc_service._PACKAGE_ENTRYPOINT`` is ``run_poc.py``, and the templates
    under ``solution_wizard/templates/poc/`` all render that name. A manifest
    naming anything else fails every run at once, before the PoC's own code has
    a chance to be wrong."""
    run = next(c for c in pod_spec["containers"] if c["name"] == "poc-run")
    # Wrapped in a shell that prints the result afterwards (#238); the entrypoint
    # itself is still the first command and its exit code is the Job's.
    assert run["command"] == ["sh", "-c"]
    script = run["args"][0]
    assert script.splitlines()[0] == "python run_poc.py"
    assert 'exit "$rc"' in script
    assert run["workingDir"] == "/workspace/poc"


def test_the_package_fetch_keeps_the_times_of_the_files(tmp_path: Path) -> None:
    """A PoC writes its saved schema model again when output_schema.py is newer
    (GAIK-project/gaik-toolkit#247). zipfile.extractall gives every file the
    moment of extraction, the model file last, so an edit made after Phase 4 never
    reached a sandbox run."""
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    fetch = next(
        c
        for c in template["spec"]["template"]["spec"]["initContainers"]
        if c["name"] == "fetch-poc"
    )
    script = fetch["command"][-1]
    code = re.search(r'python -c "(.*?)"\n', script, re.S).group(1)
    assert "extractall" not in code

    package = tmp_path / "poc.zip"
    with zipfile.ZipFile(package, "w") as archive:
        # The order the api writes them in: the model file after the .py.
        archive.writestr(
            zipfile.ZipInfo("poc/schemas/output_schema.py", (2026, 11, 17, 12, 0, 10)), "edited"
        )
        archive.writestr(
            zipfile.ZipInfo("poc/schemas/output_schema_model.json", (2026, 11, 17, 12, 0, 0)), "{}"
        )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    code = code.replace("/workspace/poc.zip", package.as_posix()).replace(
        "/workspace", workspace.as_posix()
    )
    subprocess.run([sys.executable, "-c", code], check=True)

    schemas = workspace / "poc" / "schemas"
    edited = (schemas / "output_schema.py").stat().st_mtime
    model = (schemas / "output_schema_model.json").stat().st_mtime
    assert edited - model == pytest.approx(10, abs=1)


def _run_script(pod_spec: dict, tmp_path: Path, python_body: str) -> subprocess.CompletedProcess:
    """Run the container's script against a fake ``python`` in a scratch /workspace/poc."""
    run = next(c for c in pod_spec["containers"] if c["name"] == "poc-run")
    (tmp_path / "output").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "python"
    shim.write_text("#!/bin/sh\n" + python_body)
    shim.chmod(0o755)
    return subprocess.run(
        ["sh", "-c", run["args"][0]],
        cwd=tmp_path,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_finished_run_prints_its_result_between_markers(pod_spec: dict, tmp_path: Path) -> None:
    """The result files live in an emptyDir that goes with the pod (#238)."""
    done = _run_script(
        pod_spec,
        tmp_path,
        'echo "Processed 1 invoice(s)"\n'
        'echo \'{"supplier_name": "Testitoimittaja Oy"}\' > output/a_result.json\n'
        'echo "notes" > output/notes.txt\n'
        "echo skipped > output/report.pdf\n",
    )

    assert done.returncode == 0
    out = done.stdout
    assert "Processed 1 invoice(s)" in out
    begin, end = out.index("=== POC OUTPUT BEGIN ==="), out.index("=== POC OUTPUT END ===")
    block = out[begin:end]
    assert '"supplier_name": "Testitoimittaja Oy"' in block
    assert "--- output/notes.txt ---" in block
    assert "skipped" not in block  # only json, txt and md


def test_a_failed_run_keeps_its_exit_code_and_still_prints_what_it_wrote(
    pod_spec: dict, tmp_path: Path
) -> None:
    done = _run_script(pod_spec, tmp_path, "echo partial > output/p.json\nexit 3\n")

    assert done.returncode == 3
    assert "partial" in done.stdout
    assert "=== POC OUTPUT END ===" in done.stdout


def test_a_run_without_output_prints_empty_markers(pod_spec: dict, tmp_path: Path) -> None:
    done = _run_script(pod_spec, tmp_path, "exit 0\n")

    assert done.returncode == 0
    assert "=== POC OUTPUT BEGIN ===" in done.stdout and "=== POC OUTPUT END ===" in done.stdout


def test_a_huge_result_is_cut_but_the_end_marker_is_kept(pod_spec: dict, tmp_path: Path) -> None:
    done = _run_script(
        pod_spec, tmp_path, "head -c 1000000 /dev/zero | tr '\\0' 'x' > output/big.json\n"
    )

    assert done.returncode == 0
    begin, end = (
        done.stdout.index("=== POC OUTPUT BEGIN ==="),
        done.stdout.index("=== POC OUTPUT END ==="),
    )
    assert end - begin < 300_000  # the text block is cut; the download copy follows it
    assert "--- file big.json 1000000 ---" in _files_block(done.stdout)


def _files_block(out: str) -> str:
    begin, end = out.index("=== POC FILES BEGIN ==="), out.index("=== POC FILES END ===")
    return out[begin:end]


def test_every_output_file_is_printed_base64_for_download(pod_spec: dict, tmp_path: Path) -> None:
    """A PDF the PoC writes was out of the user's reach (customer test feedback, Oct 2026)."""
    import base64

    done = _run_script(
        pod_spec,
        tmp_path,
        "printf '%%PDF-1.4 binary \\001\\002' > output/report.pdf\n"
        "echo '{\"a\": 1}' > output/result.json\n",
    )

    assert done.returncode == 0
    block = _files_block(done.stdout)
    pdf = (tmp_path / "output" / "report.pdf").read_bytes()
    header = f"--- file report.pdf {len(pdf)} ---"
    assert header in block
    body = block.split(header, 1)[1].split("--- file", 1)[0]
    assert base64.b64decode("".join(body.split())) == pdf
    assert "--- file result.json" in block


def test_a_file_over_the_download_limit_is_named_as_skipped(pod_spec: dict, tmp_path: Path) -> None:
    done = _run_script(pod_spec, tmp_path, "head -c 4500000 /dev/zero > output/huge.bin\nexit 0\n")

    assert done.returncode == 0
    block = _files_block(done.stdout)
    assert "--- skipped huge.bin 4500000 ---" in block
    assert len(done.stdout) < 300_000  # nothing of it was printed
