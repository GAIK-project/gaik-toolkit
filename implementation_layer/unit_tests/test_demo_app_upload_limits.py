"""The demo app's audio upload limit must be the same number in every layer.

An upload passes through four independent limits: the upload widget, the Next
proxy, the OpenShift route and finally the API. When they disagree, the widget
accepts a file, the bytes travel the whole way, and only the API rejects them —
which is what happened when the UI advertised 50MB and the API enforced 20MB.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

DEMO_APP = Path(__file__).parents[1] / "toolkit_demo_app"
API_CONFIG = DEMO_APP / "api" / "utils" / "config.py"
NEXT_CONFIG = DEMO_APP / "next.config.ts"
ROUTE_YAML = DEMO_APP / "openshift" / "route.yaml"

# Demo pages that upload audio or video.
AUDIO_PAGES = [
    DEMO_APP / "app" / "(demos)" / "transcriber" / "page.tsx",
    DEMO_APP / "app" / "(demos)" / "dental-transcription" / "page.tsx",
    DEMO_APP / "app" / "(demos)" / "audio-structured" / "page.tsx",
    DEMO_APP / "app" / "(demos)" / "incident-report" / "page.tsx",
    DEMO_APP / "app" / "(demos)" / "diary" / "page.tsx",
]


def _api_limit_mb() -> int:
    """Read MAX_AUDIO_FILE_SIZE_MB without importing the demo API package."""
    tree = ast.parse(API_CONFIG.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MAX_AUDIO_FILE_SIZE_MB"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("MAX_AUDIO_FILE_SIZE_MB not found in api/utils/config.py")


def test_next_proxy_allows_the_api_audio_limit() -> None:
    limit = _api_limit_mb()
    match = re.search(
        r"proxyClientMaxBodySize:\s*\"(\d+)mb\"", NEXT_CONFIG.read_text(encoding="utf-8")
    )
    assert match, "proxyClientMaxBodySize not found in next.config.ts"
    assert int(match.group(1)) >= limit


def test_openshift_route_allows_the_api_audio_limit() -> None:
    limit = _api_limit_mb()
    match = re.search(r"proxy-body-size:\s*(\d+)m", ROUTE_YAML.read_text(encoding="utf-8"))
    assert match, "proxy-body-size annotation not found in openshift/route.yaml"
    assert int(match.group(1)) >= limit


@pytest.mark.parametrize("page", AUDIO_PAGES, ids=lambda p: p.parent.name)
def test_audio_upload_widgets_match_the_api_limit(page: Path) -> None:
    """A widget advertising more than the API accepts is a guaranteed 413."""
    sizes = {
        int(value) for value in re.findall(r"maxSize=\{(\d+)\}", page.read_text(encoding="utf-8"))
    }
    assert sizes, f"no FileUpload maxSize found in {page.name}"
    assert sizes == {_api_limit_mb()}
