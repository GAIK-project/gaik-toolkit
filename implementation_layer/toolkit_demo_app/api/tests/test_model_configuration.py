"""Regression tests for the demo website's shared OpenAI model settings."""

import ast
from pathlib import Path
from unittest.mock import patch

from api.utils.config import MODEL, MODEL_OPTIONS, get_api_config

ROUTERS_DIR = Path(__file__).parents[1] / "routers"
TARGETS = {"SchemaGenerator", "DataExtractor", "VisionParser"}


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def test_shared_model_profile() -> None:
    assert MODEL == "gpt-5.4"
    assert MODEL_OPTIONS == {
        "temperature": None,
        "reasoning_effort": "medium",
    }


def test_get_api_config_pins_the_website_model(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch(
        "gaik.software_components.config.get_openai_config",
        return_value={"api_key": "test-key", "model": "provider-default"},
    ) as get_openai_config:
        config = get_api_config()

    assert config["model"] == MODEL
    get_openai_config.assert_called_once_with(use_azure=False)


def test_all_target_router_constructors_use_the_shared_profile() -> None:
    missing_options: list[str] = []
    missing_model: list[str] = []

    for path in ROUTERS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node)
            if call_name not in TARGETS:
                continue

            has_shared_options = any(
                keyword.arg is None
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "MODEL_OPTIONS"
                for keyword in node.keywords
            )
            location = f"{path.name}:{node.lineno} ({call_name})"
            if not has_shared_options:
                missing_options.append(location)

            if call_name in {"SchemaGenerator", "DataExtractor"}:
                has_shared_model = any(
                    keyword.arg == "model"
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id == "MODEL"
                    for keyword in node.keywords
                )
                if not has_shared_model:
                    missing_model.append(location)

    assert not missing_options, f"Missing **MODEL_OPTIONS: {missing_options}"
    assert not missing_model, f"Missing model=MODEL: {missing_model}"
