"""Regression tests for the Report Writer API image build configuration.

The report writer imports ``gaik.software_modules.multi_source_report_generator``.
That module is present in this repository but absent from the current published
PyPI wheel, so the production API image must install gaik from the repository
source and must build with the repository root as Docker context.

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


def test_api_image_installs_local_gaik_package():
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    requirements = API_REQUIREMENTS.read_text(encoding="utf-8")

    assert "COPY pyproject.toml README.md LICENSE" in dockerfile
    assert "COPY implementation_layer/src ./implementation_layer/src" in dockerfile
    assert "multi-source-report-generator-agentic" in dockerfile
    assert "multi-source-report-generator-docx" in dockerfile
    assert "gaik[" not in requirements


def test_api_deploy_uses_repo_root_build_context():
    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "docker buildx build" in deploy_script
    assert "--output type=registry,oci-mediatypes=false" in deploy_script
    assert '-f "$DEMO_DIR/api/Dockerfile"' in deploy_script
    assert '"$REPO_ROOT"' in deploy_script


if __name__ == "__main__":
    test_api_image_installs_local_gaik_package()
    test_api_deploy_uses_repo_root_build_context()
    print("Report Writer image build regression tests passed.")
