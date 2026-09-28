"""Regression tests for the Report Writer API image build configuration.

The report writer imports ``gaik.software_modules.multi_source_report_generator``.
That module now ships in the published PyPI wheel, so the production API image
installs gaik from PyPI rather than building it from repository source. What
still has to hold is that the report generator's extras are actually requested,
that torch CPU is installed *before* gaik so ``gaik[all-cpu]`` resolves against
it instead of pulling the ~2GB CUDA build, and that the image builds with the
repository root as Docker context (it copies the wizard assets from there).

Run standalone:
    python -m implementation_layer.toolkit_demo_app.api.tests.test_report_writer_image_build
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
API_DOCKERFILE = REPO_ROOT / "implementation_layer" / "toolkit_demo_app" / "api" / "Dockerfile"
API_REQUIREMENTS = (
    REPO_ROOT / "implementation_layer" / "toolkit_demo_app" / "api" / "requirements.txt"
)
DEPLOY_SCRIPT = REPO_ROOT / "implementation_layer" / "toolkit_demo_app" / "openshift" / "deploy.sh"


def test_api_image_installs_published_gaik_with_report_writer_extras():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    requirements = API_REQUIREMENTS.read_text(encoding="utf-8")

    # gaik comes from the published wheel, pinned in requirements.txt.
    assert "uv pip install --system --no-cache -r requirements.txt" in dockerfile
    assert "COPY implementation_layer/src ./implementation_layer/src" not in dockerfile

    # The Report Writer's own extras have to be requested, or its imports fail
    # at runtime rather than at build time.
    assert "multi-source-report-generator-agentic" in requirements
    assert "multi-source-report-generator-docx" in requirements

    # pypandoc shells out to the pandoc binary for DOCX export.
    assert "pandoc" in dockerfile


def test_api_image_preinstalls_cpu_torch_before_gaik():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")

    assert "https://download.pytorch.org/whl/cpu" in dockerfile

    torch_install = dockerfile.index("download.pytorch.org/whl/cpu")
    gaik_install = dockerfile.index("-r requirements.txt")
    assert torch_install < gaik_install, (
        "torch CPU must be installed before gaik, otherwise gaik[all-cpu] "
        "resolves torch itself and pulls the ~2GB CUDA build"
    )


def test_api_image_copies_report_writer_v2_examples_at_repo_paths():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    copies = " ".join(dockerfile.replace("\\", " ").split())
    examples = "implementation_layer/examples/software_modules"
    house = f"{examples}/report_writer/house_condition_assessment"
    legacy = f"{examples}/multi_source_report_generator"

    # routers/report_writer_v2.py walks up from /app/routers to /app/<examples>.
    for line in (
        f"COPY {examples}/report_writer/project_meeting/report_spec.json "
        f"./{examples}/report_writer/project_meeting/",
        f"COPY {house}/report_spec.json {house}/sample_report.docx ./{house}/",
        f"COPY {house}/inputs ./{house}/inputs",
        f"COPY {legacy}/sample_inputs ./{legacy}/sample_inputs",
        # The legacy router now finds this folder first, so it needs its config too.
        f"COPY {legacy}/sample_report.md {legacy}/report_config.json ./{legacy}/",
    ):
        assert line in copies, line
    assert "generate_dataset.py" not in dockerfile
    assert "recording_scripts" not in dockerfile


def test_api_deploy_uses_repo_root_build_context():
    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "docker buildx build" in deploy_script
    assert "--output type=registry,oci-mediatypes=false" in deploy_script
    assert '-f "$DEMO_DIR/api/Dockerfile"' in deploy_script
    assert '"$REPO_ROOT"' in deploy_script


if __name__ == "__main__":
    test_api_image_installs_published_gaik_with_report_writer_extras()
    test_api_image_preinstalls_cpu_torch_before_gaik()
    test_api_image_copies_report_writer_v2_examples_at_repo_paths()
    test_api_deploy_uses_repo_root_build_context()
    print("Report Writer image build regression tests passed.")
