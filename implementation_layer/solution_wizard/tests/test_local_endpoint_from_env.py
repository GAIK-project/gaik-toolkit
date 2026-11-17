"""A local-only blueprint can name its self-hosted endpoint as env:...BASE_URL.

Wizard v2's scaffold guard refuses a literal http address in a blueprint, so a
blueprint that allows no external model API names its self-hosted model server as
``env:LOCAL_LLM_BASE_URL``. The validator accepts that reference; the generated PoC
resolves it at run time and refuses the stage unless the resolved host is local.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc
from solution_wizard.validator import validate

EXAMPLES = Path(__file__).parent.parent / "examples"
TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"
FROM_ENV = {"provider": "openai_compatible", "base_url": "env:LOCAL_LLM_BASE_URL", "model": "m"}


def _local_only(models: dict) -> Blueprint:
    blueprint = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    blueprint.models = models
    blueprint.governance.data_handling.external_model_api_allowed = False
    return blueprint


def _rule13(blueprint: Blueprint) -> list[str]:
    return [issue.message for issue in validate(blueprint).errors if issue.rule == 13]


def test_a_self_hosted_endpoint_named_from_the_environment_is_accepted(tmp_path):
    blueprint = _local_only(dict(FROM_ENV))

    assert _rule13(blueprint) == []
    scaffold_poc(blueprint, tmp_path)
    config = yaml.safe_load((tmp_path / "poc" / "config.yaml").read_text(encoding="utf-8"))
    assert config["stages"]["extraction"]["base_url"] == "env:LOCAL_LLM_BASE_URL"


def test_a_cloud_provider_is_still_refused_whatever_its_base_url():
    assert _rule13(_local_only({**FROM_ENV, "provider": "openai"}))


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        ("http://localhost:8000/v1", True),
        ("https://api.openai.com/v1", False),
        (None, False),
    ],
)
def test_the_poc_checks_the_resolved_address_before_the_stage_runs(
    tmp_path, monkeypatch, address, allowed
):
    pytest.importorskip("gaik.software_components.llm")
    copy = tmp_path / "provider_config.py"
    copy.write_text(
        (TEMPLATES / "_common" / "provider_config.py.tmpl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("provider_config_env", copy)
    provider_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provider_config)
    if address is None:
        monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", address)
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    config = {
        "governance": {"external_model_api_allowed": False, "local_processing_required": False},
        "stages": {"extraction": dict(FROM_ENV)},
    }

    if allowed:
        assert provider_config.get_stage_config(config, "extraction")["base_url"] == address
    else:
        with pytest.raises(ValueError, match="allows no external model API"):
            provider_config.get_stage_config(config, "extraction")
