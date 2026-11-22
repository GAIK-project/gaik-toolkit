"""Scaffolder -- deterministic PoC generation from a validated blueprint.

Entry point: scaffold_poc(blueprint, output_dir, synthetic=False)

Generates the complete poc/ folder described in spec §16 into
<output_dir>/poc/.  Deterministic: no API calls, no LLM involvement.

The two-layer split (spec §3.6):
  Scaffolder (this module) handles: folder tree, requirements.txt,
  .env.example, config.yaml, schema files, eval script, and run_poc.py for
  module-based common patterns (audio_to_structured, document_to_structured, rag).

  The agent (SKILL.md) handles: README prose, extraction_requirements.md
  content, and run_poc.py wiring for custom/composed pipelines.
"""

from __future__ import annotations

import ast
import hashlib
import json
import keyword
import re
import shutil
import string
from pathlib import Path
from typing import Any

from .blueprint import Blueprint, external_services
from .docs_generator import external_services_block, md_text
from .registry import get_registry
from .schema_designer import (
    NESTED_KEY,
    check_schema_names,
    nested_row_fields,
    write_extraction_requirements,
    write_schema_files,
)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "poc"

# A generated PoC installs the gaik release the wizard was validated against
# (gaik_validated_version.txt), or a later patch of it. A lower floor let pip keep
# an older gaik whose components the registry and cards no longer describe.
# provider_config.py and the stage-config constructor arguments need gaik 0.8.0,
# which stays the floor when the pin cannot be read.
_MIN_GAIK_VERSION = "0.8.0"
_VALIDATED_VERSION_FILE = Path(__file__).parent.parent.parent / "gaik_validated_version.txt"
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _gaik_version_spec() -> str:
    """Return the pip specifier for gaik, for example ``>=0.11.0,<0.12``.

    Without a readable ``X.Y.Z`` pin only the floor is set.
    """
    try:
        version = _VALIDATED_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        version = ""
    if not _VERSION_RE.match(version):
        return f">={_MIN_GAIK_VERSION}"
    major, minor = (int(part) for part in version.split(".")[:2])
    return f">={version},<{major}.{minor + 1}"


_PROVIDERS = {
    "azure",
    "openai",
    "google",
    "vertex",
    "anthropic",
    "anthropic_foundry",
    "aitta",
    "openai_compatible",
    "litellm",
}
_PROVIDER_EXTRAS = {
    "google": "llm-google",
    "vertex": "llm-google",
    "anthropic": "llm-anthropic",
    "anthropic_foundry": "llm-anthropic",
    "litellm": "llm-litellm",
}
_STAGES = ("transcription", "parser", "extraction", "embedding", "answer", "judge")
_CONFIG_OPTIONS = {
    "model",
    "embedding_model",
    "transcription_model",
    "base_url",
    "api_version",
    "timeout",
    "max_retries",
    "model_family",
    "reasoning_effort",
    "project_id",
    "location",
    "resource",
    "vertex_project",
    "vertex_location",
    "azure_endpoint",
    "azure_audio_endpoint",
}


# Blueprint values that are written into generated code as names, in comments or
# in string literals. An id is one token: letters, digits and _ . -, no spaces,
# quotes or line breaks, so it cannot end the comment or literal it is in.
# The patterns are used with fullmatch: with match, ``$`` also accepts a value
# that ends in a line break.
_ID_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]{0,99}")
# A language code (en, fi, sv-FI), or "auto": the Transcriber's own default,
# which lets the model detect the language.
_LANGUAGE_RE = re.compile(r"auto|[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*")
# The framework names the blueprint template lists include RAG_eval.
_EVAL_FRAMEWORK_RE = re.compile(r"[A-Za-z0-9_]{1,64}")
#: Free-text variables that templates put inside Python string literals and
#: comments, and into .env.example comments.
_CODE_TEXT_KEYS = ("use_case_name", "use_case_description")


def _code_values_problems(blueprint: Blueprint) -> list[str]:
    """Blueprint values the generated code would carry outside the id pattern."""
    problems: list[str] = []

    def check(value: Any, where: str) -> None:
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            problems.append(f"{where} {value!r} must be letters, digits, _ . or - (no spaces)")

    check(blueprint.use_case.id, "use_case.id")
    for step in blueprint.workflow.steps:
        check(step.id, "workflow step id")
        check(step.type, f"type of step {step.id!r}")
        for name in [*step.inputs, *step.outputs]:
            check(name, f"artifact of step {step.id!r}")
    spec = blueprint.target_output_spec or {}
    schema_name = spec.get("schema_name")
    if schema_name and not _is_python_name(schema_name):
        problems.append(f"target_output_spec.schema_name {schema_name!r} must be a Python name")
    for field in spec.get("fields", []):
        if isinstance(field, str) and not _is_python_name(field):
            problems.append(f"output field {field!r} must be a Python name")
    # The rows of a nested collection become a model of their own in the same file.
    for container, fields in nested_row_fields(spec).items():
        for field in fields:
            if not _is_python_name(field):
                problems.append(f"field {field!r} of the {container!r} rows must be a Python name")
        if nested_row_fields(spec[NESTED_KEY][container]):
            problems.append(
                f"the {container!r} rows have rows of their own; only one level of nested "
                "rows is supported"
            )
    if spec.get(NESTED_KEY) and not problems:
        # Anything else the rows' model would refuse, before a file is written.
        try:
            check_schema_names(spec, schema_name or "OutputSchema")
        except ValueError as exc:
            problems.append(f"target_output_spec.nested: {exc}")
    return problems


def _is_python_name(value: Any) -> bool:
    """An identifier that is not a keyword, so generated source can carry it as written."""
    return isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)


def _eval_framework(evaluation: Any) -> str:
    """The evaluation framework's name for the generated eval script; unknown shapes fall back."""
    if not isinstance(evaluation, dict):
        return "extraction_eval"
    name = evaluation.get("eval_framework", "extraction_eval")
    valid = isinstance(name, str) and _EVAL_FRAMEWORK_RE.fullmatch(name)
    return name if valid else "extraction_eval"


def _code_text(value: Any) -> str:
    """Free text made safe inside a Python string literal, a docstring or a comment.

    One line, with backslashes and quotes escaped. The templates put it in plain
    literals only, never in an f-string.
    """
    text = " ".join(str(value).split())
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _for_code(variables: dict[str, Any]) -> dict[str, Any]:
    """The variables as code templates take them: free text escaped, one line."""
    return {**variables, **{k: _code_text(variables[k]) for k in _CODE_TEXT_KEYS if k in variables}}


_ENDPOINT_KEYS = ("base_url", "azure_endpoint", "azure_audio_endpoint")
_ENV_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{0,99}")
#: An ``env:`` reference in a blueprint names a setting (a deployment, an
#: endpoint), never a credential: the PoC would read it and use it as a value.
_CREDENTIAL_NAME_RE = re.compile(
    r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|DATABASE|DSN|PRIVATE|CERT", re.IGNORECASE
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _setting_problems(
    settings: dict[str, Any], where: str, local_hosts: set[str] = _LOCAL_HOSTS
) -> list[str]:
    """Endpoints and ``env:`` references the generated configuration would follow.

    Plain http is accepted only for this machine and the hosts in models.local_endpoints.
    """
    from urllib.parse import urlsplit

    problems: list[str] = []
    for key, value in settings.items():
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text[:4].lower() == "env:":
            name = text[4:].strip()
            if not _ENV_NAME_RE.fullmatch(name):
                problems.append(f"{where}.{key} {value!r} (env: needs an UPPER_CASE name)")
            elif _CREDENTIAL_NAME_RE.search(name):
                problems.append(f"{where}.{key} {value!r} (env: names a setting, not a credential)")
            continue
        if key in _ENDPOINT_KEYS:
            try:
                url = urlsplit(text)
                host = (url.hostname or "").lower()
            except ValueError:
                problems.append(f"{where}.{key} {value!r} (not a URL)")
                continue
            local = url.scheme == "http" and host in local_hosts
            if not (url.scheme == "https" or local) or not host or url.username or url.password:
                problems.append(
                    f"{where}.{key} {value!r} (an https endpoint without credentials in it)"
                )
    return problems


def _provider_name(value: str) -> str:
    provider = str(value).strip().lower()
    provider = "azure" if provider == "azure_openai" else provider
    if provider not in _PROVIDERS:
        raise ValueError(f"Unsupported provider {value!r}; choose one of {sorted(_PROVIDERS)}")
    return provider


_MODEL_KEYS = ("model", "embedding_model", "transcription_model")


def _model_id(value, where: str):
    """Keep only the ID from a model field; older blueprints may append a note.

    e.g. "text-embedding-3-large (env-overridable via RAG_EMBEDDING_DEPLOYMENT)".
    """
    if not isinstance(value, str):
        return value
    model = re.sub(r"\s*\(.*\)\s*$", "", value).strip()
    if not model or re.search(r"\s", model):
        raise ValueError(
            f"{where} must be a model or deployment ID, got {value!r}. Put notes in "
            "assumptions, not in the model field."
        )
    return model


def _stage_settings(blueprint: Blueprint) -> dict[str, dict]:
    """Resolve nonsecret, deterministic settings without loading credentials."""
    models = blueprint.models or {}
    provider = _provider_name(models.get("provider", DEFAULT_PROVIDER))
    shared = {key: models[key] for key in _CONFIG_OPTIONS if models.get(key) is not None}
    if not shared.get("model") and (models.get("extraction_model") or models.get("answer_model")):
        shared["model"] = models.get("extraction_model") or models["answer_model"]
    stages = {}
    for stage in _STAGES:
        override = models.get(f"{stage}_config") or {}
        if not isinstance(override, dict):
            raise ValueError(f"models.{stage}_config must be a dictionary")
        unknown = set(override) - (_CONFIG_OPTIONS | {"provider"})
        if unknown:
            raise ValueError(
                f"Unsupported settings in models.{stage}_config: {sorted(unknown)}. "
                "Keep credentials in provider environment variables, not the blueprint."
            )
        selected = _provider_name(override.get("provider", provider))
        settings = dict(shared) if selected == provider else {}
        explicit = models.get(f"{stage}_model")
        model = explicit
        if stage in {"parser", "judge"} and model is None:
            model = models.get("extraction_model") or models.get("answer_model")
        if stage == "extraction" and model is None:
            model = models.get("answer_model")
        key = (
            "embedding_model"
            if stage == "embedding"
            else "transcription_model"
            if stage == "transcription"
            else "model"
        )
        if selected == provider and model:
            settings[key] = model
        elif explicit and key not in override:
            # Model IDs are provider-specific; never drop or move one silently.
            raise ValueError(
                f"models.{stage}_model belongs to models.provider {provider!r}, but "
                f"models.{stage}_config selects {selected!r}. Set {key!r} in "
                f"models.{stage}_config instead."
            )
        settings.update(override)
        settings["provider"] = selected
        for model_key in _MODEL_KEYS:
            if model_key in settings:
                settings[model_key] = _model_id(
                    settings[model_key], f"models ({stage}.{model_key})"
                )
        problems = _setting_problems(settings, f"models ({stage})", _local_hosts(blueprint))
        if problems:
            raise ValueError("Unsafe model settings: " + "; ".join(problems))
        stages[stage] = settings
    return stages


# The model stages each component calls. A component that calls a model is listed here,
# so a blueprint's governance flags are checked for every stage its PoC may use; a test
# keeps it in step with the registry's components that name supported providers.
_COMPONENT_STAGES: dict[str, set[str]] = {
    "AudioToStructuredData": {"transcription", "extraction"},
    "Transcriber": {"transcription"},
    "ParallelTranscriber": {"transcription"},
    "TextToSpeech": {"transcription"},
    "TranscriptEnhancer": {"transcription"},
    "DocumentsToStructuredData": {"parser", "extraction"},
    "VisionParser": {"parser"},
    "VisionPlusParser": {"parser"},
    "VisionRagParser": {"parser"},
    "MultimodalParser": {"parser"},
    "VisionExtractor": {"parser"},
    "FormUnderstander": {"parser"},
    "SourceNormalizer": {"parser", "transcription"},
    "Extractor": {"extraction"},
    "DataExtractor": {"extraction"},
    "SchemaGenerator": {"extraction"},
    "DocumentClassifier": {"extraction"},
    "RAGWorkflow": {"parser", "embedding", "answer"},
    "Embedder": {"embedding"},
    "Retriever": {"embedding"},
    "AnswerGenerator": {"answer"},
    "PostgresAgent": {"answer"},
    "TabularAgent": {"answer"},
    "MultiSourceReportGenerator": {"answer"},
    "ReportWriter": {"answer"},
    "KnowledgeCurator": {"answer"},
    "ReportSynthesizer": {"answer"},
    "DraftReviewer": {"answer"},
    "LLMJudge": {"judge"},
    "LLMJudgePanel": {"judge"},
    "ExtractionEvaluator": {"judge"},
    "RAGEvaluator": {"judge"},
}


def _needed_stages(blueprint: Blueprint, pattern: str) -> set[str]:
    stages = {
        "audio_to_structured": {"transcription", "extraction"},
        "document_to_structured": {"parser", "extraction"},
        "rag": {"parser", "embedding", "answer"},
    }.get(pattern, {"extraction"}).copy()
    names = set(blueprint.components.selected_building_blocks)
    names.update(module.name for module in blueprint.components.selected_modules)
    names.update(step.component for step in blueprint.workflow.steps)
    for name in names:
        stages |= _COMPONENT_STAGES.get(name, set())
    return stages


# The provider a blueprint gets when models.provider is not set. It is a cloud
# provider, so a blueprint that allows no external model API never gets it.
DEFAULT_PROVIDER = "azure"


# A models.local_endpoints entry: a bare host name, no scheme, port or path.
_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST_RE = re.compile(rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})*")
# A last label that is a number: the entry is an IPv4 address in some notation.
_NUMERIC_LABEL_RE = re.compile(r"\d+|0x[0-9a-f]*")

#: The hosts of the cloud model APIs gaik calls, as in gaik's endpoint allow-list
#: (gaik.software_components.endpoints.PROVIDER_HOSTS; a test keeps them in step).
#: ``*`` matches any host ending in the rest of the pattern.
CLOUD_MODEL_API_HOSTS = (
    "api.openai.com",
    "*.openai.azure.com",
    "*.cognitiveservices.azure.com",
    "*.services.ai.azure.com",
    "aitta-api.csc.fi",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "*-aiplatform.googleapis.com",
    "aiplatform.eu.rep.googleapis.com",
    "aiplatform.us.rep.googleapis.com",
    "api.typesafe.ai",
    "gaik-decide.2.rahtiapp.fi",
)


def _cloud_model_api_host(host: str) -> bool:
    for pattern in CLOUD_MODEL_API_HOSTS:
        if pattern.startswith("*"):
            if len(host) > len(pattern) - 1 and host.endswith(pattern[1:]):
                return True
        elif host == pattern:
            return True
    return False


def _local_endpoint_problem(entry: object) -> str | None:
    """Why a models.local_endpoints entry cannot count as local processing, if it cannot.

    The PoC sends the stage's key to a listed host, over plain http too, and treats
    a stage there as local. A public IP address or a cloud model API host is never a
    server of the user's own, and 0.0.0.0 is no server's address; a public domain
    name cannot be checked here, so a server of the user's own on a public IP
    address is listed by its DNS name.
    """
    import ipaddress

    text = str(entry).strip().lower()
    if not isinstance(entry, str) or not _HOST_RE.fullmatch(text):
        return (
            f"models.local_endpoints entry {entry!r} must be a host name such as "
            "'gpu.lan', without scheme, port or path"
        )
    if _NUMERIC_LABEL_RE.fullmatch(text.rsplit(".", 1)[-1]):
        try:
            address = ipaddress.IPv4Address(text)
        except ValueError:
            return (
                f"models.local_endpoints entry {entry!r} reads as an IP address; write it "
                "as four decimal numbers such as '192.168.1.20'"
            )
        if address.is_unspecified:
            return (
                f"models.local_endpoints entry {entry!r} is the address a server listens on, "
                "not one to connect to; list the server's own address or host name "
                "('localhost' for this machine needs no entry)"
            )
        if address.is_global:
            return (
                f"models.local_endpoints entry {entry!r} is a public IP address; list only "
                "servers on your own network. For a server of your own on a public IP "
                "address, list its DNS name instead"
            )
    if _cloud_model_api_host(text):
        return (
            f"models.local_endpoints entry {entry!r} is a cloud model API host, not a "
            "server of your own; it cannot count as local processing"
        )
    return None


def _declared_local_hosts(blueprint: Blueprint) -> tuple[set[str], list[str]]:
    """The hosts in models.local_endpoints, and why the others are refused.

    An entry must be a host name; a public IP address and the host of a cloud model
    API gaik calls are refused (see :func:`_local_endpoint_problem`).
    """
    declared = (blueprint.models or {}).get("local_endpoints") or []
    if not isinstance(declared, list):
        return set(), ["models.local_endpoints must be a list of host names"]
    hosts, problems = set(), []
    for entry in declared:
        problem = _local_endpoint_problem(entry)
        if problem:
            problems.append(problem)
        else:
            hosts.add(str(entry).strip().lower())
    return hosts, problems


def _local_hosts(blueprint: Blueprint) -> set[str]:
    """Hosts that count as local processing: this machine, plus models.local_endpoints."""
    return _LOCAL_HOSTS | _declared_local_hosts(blueprint)[0]


def _local_endpoints(blueprint: Blueprint) -> list[str]:
    """The hosts models.local_endpoints lists, which the PoC lets gaik send keys to.

    An entry that is not a host name is refused whatever the governance flags say.
    """
    hosts, problems = _declared_local_hosts(blueprint)
    if problems:
        raise ValueError("; ".join(problems))
    return sorted(hosts - _LOCAL_HOSTS)


def _is_local_stage(stage: str, settings: dict[str, Any], local_hosts: set[str]) -> bool:
    """Whether a stage's model runs on a host the blueprint counts as local.

    Self-hosted Whisper (``whisper_local``) for transcription, or an
    ``openai_compatible``/``litellm`` stage whose ``base_url`` names a local host. Every
    other provider is an external model API.
    """
    from urllib.parse import urlsplit

    if stage == "transcription" and settings.get("transcription_model") == "whisper_local":
        return True
    if settings.get("provider") not in {"openai_compatible", "litellm"}:
        return False
    base_url = settings.get("base_url")
    if isinstance(base_url, str) and base_url.strip()[:4].lower() == "env:":
        # Wizard v2 names a self-hosted endpoint as env:...BASE_URL (its scaffold guard
        # refuses a literal http address). The PoC resolves it at run time, and
        # provider_config.py refuses the stage unless the resolved host is local.
        return True
    try:
        host = (urlsplit(str(base_url or "")).hostname or "").lower()
    except ValueError:
        return False
    return bool(host) and host in local_hosts


def external_model_forbidden(blueprint: Blueprint) -> bool:
    """Whether governance.data_handling allows no external model API."""
    handling = blueprint.governance.data_handling
    return (not handling.external_model_api_allowed) or handling.local_processing_required


def _needed(blueprint: Blueprint) -> set[str]:
    return _needed_stages(blueprint, _determine_pattern(blueprint))


def defaulted_stages(blueprint: Blueprint) -> list[str]:
    """Stages the PoC uses that get the default provider: no models.provider, no own one."""
    models = blueprint.models or {}
    if models.get("provider"):
        return []

    def own_provider(stage: str) -> bool:
        override = models.get(f"{stage}_config")
        return isinstance(override, dict) and bool(override.get("provider"))

    return sorted(stage for stage in _needed(blueprint) if not own_provider(stage))


def governance_problems(blueprint: Blueprint) -> list[str]:
    """Stages whose provider the blueprint's governance flags do not allow.

    A blueprint with ``external_model_api_allowed: false`` or
    ``local_processing_required: true`` needs every stage the PoC uses on a local
    host, and never gets the default cloud provider.
    """
    if not external_model_forbidden(blueprint):
        return []
    entries = _declared_local_hosts(blueprint)[1]
    try:
        defaulted = defaulted_stages(blueprint)
        if defaulted:
            return entries + [
                "governance allows no external model API, but no provider is set for the "
                f"{', '.join(defaulted)} stage(s), so the PoC would use the default "
                f"{DEFAULT_PROVIDER!r}. Set models.provider or each stage's config to a "
                "local endpoint"
            ]
        stages = _stage_settings(blueprint)
        needed = _needed(blueprint)
    except ValueError as exc:
        return entries + [
            "governance allows no external model API, and the model settings cannot be "
            f"checked: {exc}"
        ]
    local_hosts = _local_hosts(blueprint)
    return entries + [
        f"governance allows no external model API, but the {stage} stage uses "
        f"{stages[stage]['provider']!r}"
        + (f" at {stages[stage]['base_url']!r}" if stages[stage].get("base_url") else "")
        + "; use a local endpoint (localhost, or a host listed in models.local_endpoints)"
        for stage in sorted(needed)
        if not _is_local_stage(stage, stages[stage], local_hosts)
    ]


def _validate_stage_settings(
    stages: dict[str, dict], needed: set[str], external_forbidden: bool = False
) -> None:
    """Refuse stage settings the generated PoC cannot run with.

    ``external_forbidden``: the blueprint allows no external model API, so a
    ``whisper_local`` transcription stage reads no OpenAI/Azure credentials.
    """
    if "transcription" in needed and stages["transcription"]["provider"] not in {"openai", "azure"}:
        raise ValueError(
            "Audio requires an OpenAI/Azure transcription_config. Set "
            "models.transcription_config explicitly when using another text provider."
        )
    if "transcription" in needed:
        audio = stages["transcription"]
        if (
            audio["provider"] == "azure"
            and audio.get("base_url")
            and not (audio.get("azure_audio_endpoint") or audio.get("azure_endpoint"))
        ):
            raise ValueError(
                "Azure transcription_config with base_url also needs an explicit "
                "azure_endpoint or azure_audio_endpoint resource URL for audio."
            )
    if "embedding" in needed:
        embedding = stages["embedding"]
        if embedding["provider"] in {"anthropic", "anthropic_foundry"}:
            raise ValueError("Native Anthropic has no embeddings; select models.embedding_config.")
        if embedding["provider"] in {"aitta", "openai_compatible", "litellm"} and not embedding.get(
            "embedding_model"
        ):
            raise ValueError(
                "Set an explicit models.embedding_config.embedding_model for this provider."
            )
    # A whisper_local stage with no external model API reads no OPENAI_API_KEY: its
    # transcript enhancement is off and its endpoint comes from LOCAL_TRANSCRIBER_API_*.
    keyed = {
        stage
        for stage in needed
        if not (
            external_forbidden
            and stage == "transcription"
            and stages[stage].get("transcription_model") == "whisper_local"
        )
    }
    if {"openai", "openai_compatible"} <= {stages[stage]["provider"] for stage in keyed}:
        raise ValueError(
            "An openai stage and an openai_compatible stage would both read OPENAI_API_KEY "
            "and OPENAI_BASE_URL, sending one key to both endpoints. Use one of them for "
            "every stage, or a separately keyed provider (e.g. litellm) for the other."
        )
    for stage in needed:
        settings = stages[stage]
        if settings["provider"] == "litellm" and (
            not settings.get("model") or "/" not in str(settings["model"])
        ):
            raise ValueError(f"models.{stage}_config needs a provider-prefixed LiteLLM model.")


# ---------------------------------------------------------------------------
# Eval framework bodies injected into run_basic_eval.py
# ---------------------------------------------------------------------------

_EVAL_BODIES: dict[str, str] = {
    "extraction_eval": """\
    total_exact = total_semantic = total_present = 0
    n = 0
    for out_file in output_files:
        gt_file = ground_truth_dir / out_file.name
        if not gt_file.exists():
            continue
        prediction = json.loads(out_file.read_text())
        ground_truth = json.loads(gt_file.read_text())
        for key, expected in ground_truth.items():
            predicted = prediction.get(key, "")
            exact = str(predicted).strip().lower() == str(expected).strip().lower()
            present = bool(str(predicted).strip())
            total_exact += int(exact)
            total_present += int(present)
            n += 1
        total_semantic += total_exact  # placeholder; use extraction_eval for full metrics
    if n:
        print(f"\\nField exact-match rate: {total_exact}/{n} ({100*total_exact/n:.1f}%)")
        print(f"Field completeness:     {total_present}/{n} ({100*total_present/n:.1f}%)")
    else:
        print("No matched output/ground-truth pairs found.")
    print("\\nFor full metrics (precision/recall/F1/semantic) run:")
    print("  evaluation_layer/eval_methods/extraction_eval/evaluate.py")""",
    "RAG_eval": """\
    print("For full RAG retrieval metrics (token recall, MRR, rank-weighted coverage) run:")
    print("  evaluation_layer/eval_methods/RAG_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")""",
    "transcription_eval": """\
    print("For full transcription metrics (WER/CER) run:")
    print("  evaluation_layer/eval_methods/transcription_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")""",
    "report_writing_eval": """\
    print("For full report quality scoring (LLM-as-judge) run:")
    print("  evaluation_layer/eval_methods/report_writing_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")""",
    "translation_eval": """\
    print("For full translation metrics (BLEU/chrF/TER) run:")
    print("  evaluation_layer/eval_methods/translation_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")""",
}

_DEFAULT_EVAL_BODY = """\
    print("No specific evaluation framework configured.")
    print("Output files:")
    for f in output_files:
        print(f"  {f}")"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill(template_text: str, variables: dict[str, Any]) -> str:
    """Fill a template using string.Template safe_substitute."""
    return string.Template(template_text).safe_substitute(variables)


def _read_template(subdir: str, filename: str) -> str | None:
    path = TEMPLATES_DIR / subdir / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _topo_order(steps: list) -> list:
    """Return steps sorted in topological order from the depends_on graph.

    Two blueprints with the same dependency graph but different step-list
    ordering will produce the same topological sequence, making the pattern
    key stable regardless of authoring order.
    """
    from collections import deque

    step_by_id = {s.id: s for s in steps}
    dependents: dict[str, list[str]] = {s.id: [] for s in steps}
    in_degree: dict[str, int] = {s.id: 0 for s in steps}

    for s in steps:
        for dep in s.depends_on or []:
            if dep in dependents:
                dependents[dep].append(s.id)
                in_degree[s.id] = in_degree.get(s.id, 0) + 1

    # Kahn's algorithm: start from nodes with no dependencies
    queue: deque = deque(s.id for s in steps if not (s.depends_on or []))
    ordered: list = []
    while queue:
        nid = queue.popleft()
        if nid in step_by_id:
            ordered.append(step_by_id[nid])
        for child in dependents.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Append any remaining (cycles / disconnected nodes) in original list order
    seen = {s.id for s in ordered}
    ordered += [s for s in steps if s.id not in seen]
    return ordered


def _derive_pattern_key(blueprint: Blueprint) -> str:
    """Derive a stable, topology-aware key for a blueprint's pipeline shape.

    The key is computed from a **canonically sorted** set of edge descriptors
    (component + inputs + outputs + dependencies), not from traversal order.
    This means two blueprints with the same dependency graph but different
    step-list orderings produce the same key.
    LLMJudge and human_review are excluded (LLMJudge is injected separately).

    Returns a directory-safe key like 'hybrid_transcriber_multimodalparser_extractor_1a2b3c4d'.
    """
    import hashlib

    edge_parts = []
    name_parts = []
    for step in blueprint.workflow.steps:
        comp = step.component or ""
        if comp in ("LLMJudge", "custom", "human_review", ""):
            continue
        if step.type == "human_review":
            continue
        # Canonical edge: component + sorted inputs + sorted outputs + sorted deps
        edge_parts.append(
            f"{comp}(in={sorted(step.inputs)},out={sorted(step.outputs)},"
            f"deps={sorted(step.depends_on or [])})"
        )
        name_parts.append(comp.lower())

    if not edge_parts:
        return "_generic"

    # Sort edges canonically so list order does not affect the key
    signature = "|".join(sorted(edge_parts))
    short_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:8]
    # Human-readable prefix from sorted component names (up to 4)
    prefix = "_".join(sorted(set(name_parts))[:4])
    prefix = "".join(c if c.isalnum() or c == "_" else "_" for c in prefix)
    return f"hybrid_{prefix}_{short_hash}"


# Blocks a fixed template injects itself, besides the module's own components: the judge
# (${llm_judge_section}) in all three, and source tracing (${source_tracing_setup} and
# ${source_tracing_section}) in the two extraction templates. RAG has no extraction step.
_INJECTED_BLOCKS = {
    "audio_to_structured_data": {"LLMJudge", "SourceTracing"},
    "documents_to_structured_data": {"LLMJudge", "SourceTracing"},
}


def _module_covers_all_blocks(module_id: str, building_blocks: set) -> bool:
    """Return True if all selected building blocks are covered by the given module.

    LLMJudge is excluded -- it is injected separately via ${llm_judge_section}. So is
    SourceTracing in the audio and document templates (see ``_INJECTED_BLOCKS``).

    A building block is "covered" if:
      (a) it appears directly in the module's uses_components, OR
      (b) it is itself a compound component whose sub-components (uses_components)
          are all within the module's uses_components — e.g. "Extractor" wraps
          [SchemaGenerator, DataExtractor], both of which are inside
          AudioToStructuredData.uses_components, so Extractor is covered.

    If any extra block is genuinely new (e.g. DocumentClassifier), fall through
    to dynamic/generic so those extra steps are not silently dropped.
    """
    registry = get_registry()
    extra_blocks = building_blocks - _INJECTED_BLOCKS.get(module_id, {"LLMJudge"})
    if not extra_blocks:
        return True

    entry = registry.lookup_by_id(module_id)
    if not entry:
        return False
    module_components = set(entry.get("uses_components", []))

    for block in extra_blocks:
        if block in module_components:
            continue  # directly covered
        # Transitive: if the block is a compound, check if its sub-components are covered
        block_entry = registry.lookup_by_name(block) or registry.lookup_by_id(block)
        if block_entry:
            sub = set(block_entry.get("uses_components", []))
            if sub and sub.issubset(module_components):
                continue  # transitively covered
        return False  # genuinely extra

    return True


def _determine_pattern(blueprint: Blueprint) -> str:
    """Return the PoC pattern name (= template subdir) to use.

    Discovery order:
      1. Fixed module patterns (audio/document/rag) -- only when exactly one
         module is selected AND its building blocks are all covered. If multiple
         modules are selected the fixed template for the first match would
         silently drop all other modules' logic, so we fall through instead.
      2. Dynamic template lookup -- if a promoted template exists for this
         blueprint's pipeline shape, reuse it deterministically.
      3. _generic fallback -- agent authors the wiring.
    """
    modules = [
        m.id if hasattr(m, "id") else m.get("id", "") for m in blueprint.components.selected_modules
    ]
    building_blocks = set(blueprint.components.selected_building_blocks)

    # Only use a fixed module template when exactly one module is selected.
    # Multiple selected modules mean a genuine hybrid -- no single fixed template
    # covers the full pipeline, so fall through to dynamic/generic.
    if len(modules) == 1:
        if "audio_to_structured_data" in modules and _module_covers_all_blocks(
            "audio_to_structured_data", building_blocks
        ):
            return "audio_to_structured"
        if "documents_to_structured_data" in modules and _module_covers_all_blocks(
            "documents_to_structured_data", building_blocks
        ):
            return "document_to_structured"
        if "rag_workflow" in modules and _module_covers_all_blocks("rag_workflow", building_blocks):
            return "rag"

    # Dynamic library lookup by topology-aware key
    pattern_key = _derive_pattern_key(blueprint)
    if pattern_key != "_generic":
        candidate = TEMPLATES_DIR / pattern_key / "run_poc.py.tmpl"
        if candidate.exists():
            if "get_stage_config(" not in candidate.read_text(encoding="utf-8"):
                raise ValueError(
                    f"Promoted template {pattern_key!r} needs a provider migration: "
                    "use provider_config.get_stage_config(config, stage) in each model stage. "
                    "Its existing pipeline has not been replaced."
                )
            return pattern_key

    return "_generic"


def _build_generic_pipeline_skeleton(blueprint: Blueprint) -> str:
    """Build a per-step wiring skeleton for the _generic template.

    Each automated_task step becomes a labelled block carrying the component's
    verified call pattern (from the reference cards) and the blueprint-derived
    artifact variable names -- which already chain correctly. The agent fills
    one call per block rather than inventing the whole structure.
    """
    from .registry import get_reference_cards

    cards = get_reference_cards()
    lines: list[str] = []

    for step in blueprint.workflow.steps:
        comp = step.component or ""
        inputs = ", ".join(step.inputs) if step.inputs else "(none)"
        outputs = ", ".join(step.outputs) if step.outputs else "(none)"

        if step.type == "user_task":
            lines.append(f"    # ----- Step: {step.id}  (user input) -----")
            lines.append(
                f"    # produces: {outputs}  (loaded from sample_input/, see loaders above)"
            )
            lines.append("")
            continue

        if step.type == "human_review" or comp == "human_review":
            lines.append(
                f"    # ----- Step: {step.id}  (human review -- NOT executed in PoC) -----"
            )
            lines.append(f"    # In production a reviewer approves: {outputs}")
            lines.append("")
            continue

        if comp == "LLMJudge":
            # Handled by the dedicated validation block below; skip here.
            continue

        lines.append(f"    # ----- Step: {step.id}  ({comp}) -----")
        lines.append(f"    # inputs: {inputs}  ->  outputs: {outputs}")
        card = cards.get(comp)
        if card:
            lines.append("    # Reference call pattern:")
            for snippet_key in ("import", "construct", "call"):
                for snip_line in card[snippet_key].split("\n"):
                    lines.append(f"    #   {snip_line}")
            lines.append(f"    #   returns: {card['returns']}")
        else:
            lines.append(
                f"    # (no reference card for {comp} -- read its README/example_script_path)"
            )
        # Pre-declare each output variable so later steps reference real names
        for out in step.outputs:
            lines.append(f"    {out} = None  # TODO: wire {comp}; assign its result to '{out}'")
        lines.append("")

    return "\n".join(lines)


def _build_input_loaders(blueprint: Blueprint) -> str:
    """Build input-loading code for each user_upload artifact, by type."""
    from .blueprint import ArtifactSource

    audio_exts = '(".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4")'
    doc_exts = '(".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".txt", ".md")'

    lines: list[str] = []
    for art_id, art in blueprint.artifacts.items():
        if art.source != ArtifactSource.USER_UPLOAD:
            continue
        atype = art.type.lower()
        if atype in ("audio", "video"):
            exts = audio_exts
        elif atype in ("pdf", "docx", "document", "image", "text"):
            exts = doc_exts
        else:
            exts = doc_exts
        lines.append(f"    # Load user-upload artifact: {art_id} (type={art.type})")
        # The id's words pick between several inputs. A file type ("pdf" in agenda_pdf)
        # is in every file name of that type, so it would pick none.
        hints = tuple(w for w in art_id.lower().split("_") if len(w) > 2 and f'".{w}"' not in exts)
        lines.append(f"    {art_id}_path = _find_input(sample_dir, {exts}, hints={hints!r})")
        lines.append(f"    print(f'{art_id}: {{{art_id}_path}}')")
        lines.append("")
    if not lines:
        lines.append("    # (no user-upload inputs declared)")
    return "\n".join(lines)


def _build_generic_judge_section(has_llm_judge: bool) -> str:
    """LLMJudge block for the _generic template.

    Unlike the module templates (which read result.transcription / result.parsed_documents),
    the generic block uses the CONTRACT variables the agent must assign:
      - extracted_fields : dict | list[dict]  (the structured output)
      - source_text      : str                (grounding text for hallucination check)
    """
    if not has_llm_judge:
        return "    # LLMJudge is not in this blueprint's pipeline."

    return """\
    # -- LLMJudge hallucination detection (from blueprint) --
    # Contract: by this point your wiring MUST have assigned:
    #   extracted_fields  (dict or list[dict])  -- the structured output
    #   source_text       (str)                 -- the grounding text to validate against
    if extracted_fields is None or not source_text:
        print("LLMJudge skipped: pipeline not fully wired "
              "(need both 'extracted_fields' and 'source_text').")
    else:
        print("\\nRunning LLMJudge hallucination detection...")
        try:
            from gaik.software_components.validators.llm_judge import LLMJudge as _LLMJudge
            judge = _LLMJudge(config=get_stage_config(config, "judge"))
            extracted_for_judge = extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(
                source_text=source_text, extracted=extracted_for_judge,
            )
            # judge_error: the judge's response could not be read, so an empty
            # flag list is no verdict. gaik 0.8.14 has neither judge_error nor
            # passed; there an empty flag list is the only signal.
            judge_error = getattr(report, "judge_error", None)
            if report.flags:
                print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
                for flag in report.flags:
                    # The value and the reason quote content: shown only with --verbose.
                    print(f"  field={flag.field}" + (f"  value={flag.value}  reason={flag.reason}"
                                                     if poc_output.VERBOSE else ""))
            if judge_error:
                print(f"WARNING: the judge's response could not be read ({judge_error}).")
            elif not report.flags:
                print("Hallucination check passed -- all fields are grounded in the source.")
            validation_result = {
                "hallucination_flags": [
                    {"field": f.field, "value": f.value,
                     "severity": str(f.severity), "reason": f.reason}
                    for f in report.flags
                ],
                "judge_error": judge_error,
                "passed": getattr(report, "passed", not report.flags),
            }
            (output_dir / "validation.json").write_text(
                json.dumps(validation_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except ImportError:
            print("LLMJudge skipped: gaik[llm-judge] not installed.")
        except Exception as _judge_exc:
            print(f"LLMJudge warning: {poc_output.short_error(_judge_exc)}")"""


def _build_source_tracing_setup(has_source_tracing: bool) -> str:
    """Code injected before ``pipeline.run`` in the audio and document templates.

    Asks the extractor for one quote per value by adding the evidence request to the schema
    and the task. It needs the schema before the run: on the first run the pipeline generates
    it, so tracing starts from the second run, once the schema file exists.
    Empty when SourceTracing is not in the blueprint, so other PoCs are unchanged.
    """
    if not has_source_tracing:
        return ""
    return """\
    # -- SourceTracing: ask the extractor for one verbatim quote per value (from blueprint) --
    # The evidence request is added to the schema and the task; the pipeline is unchanged.
    # It needs the schema before the run, so it starts once the schema file exists.
    tracing = None
    if schema is not None:
        from gaik.software_components.source_tracing import SourceTracing
        tracing = SourceTracing()
        _traced_task = tracing.augment(schema, user_requirements, source="text")
        schema, user_requirements = _traced_task.model, _traced_task.prompt
    else:
        print("SourceTracing: the schema is generated in this run, so values are not traced yet. "
              "Run the PoC again to trace them.")
"""


def _build_source_tracing_section(has_source_tracing: bool, pattern: str) -> str:
    """Code injected after the run and before the judge in the audio and document templates.

    Removes the evidence from the results, checks each value against its quote in the text the
    extractor read, writes the report, and prints the values a reviewer should look at.
    """
    if not has_source_tracing:
        return ""
    if pattern == "audio_to_structured":
        source = "transcript_used(result)"
        import_line = (
            "        from gaik.software_components.source_tracing import transcript_used\n"
        )
    else:
        source = "result.parsed_documents"
        import_line = ""
    return (
        "    # -- SourceTracing: check each value against its quote in the source (from blueprint) --\n"
        "    if tracing is not None:\n"
        + import_line
        + "        clean_fields, trace_report = tracing.check_text(\n"
        f"            result.extracted_fields, {source}\n"
        "        )\n"
        "        result.extracted_fields = clean_fields  # the evidence is not part of the output\n"
        '        trace_path = output_dir / f"{input_file.stem}_source_trace.json"\n'
        "        trace_path.write_text(\n"
        "            json.dumps(trace_report.to_dict(), indent=2, ensure_ascii=False, default=str),\n"
        '            encoding="utf-8",\n'
        "        )\n"
        "        summary = trace_report.summary()\n"
        '        coverage = summary["coverage"]\n'
        "        print(\n"
        "            f\"SourceTracing: {summary['verified']} verified, {summary['check']} to check, \"\n"
        "            f\"{summary['reworded']} reworded, {summary['unchecked']} unchecked\"\n"
        '            + (f"; evidence for {coverage:.0%} of the values" if coverage is not None else "")\n'
        "        )\n"
        "        for item in trace_report.items:\n"
        '            if item.verdict != "verified":\n'
        "                # The value and its quote are content: shown only with --verbose.\n"
        '                print(f"  {item.verdict:<9} {item.field}"\n'
        '                      + (f": {item.value!r}  quote: {item.quote!r}"\n'
        '                         if poc_output.VERBOSE else ""))\n'
        '        print(f"Source trace report: {trace_path}")\n'
    )


def _wants_pdf(blueprint: Blueprint) -> bool:
    """True when the blueprint requests a PDF report of the PoC output.

    Triggered by 'pdf' (or 'report') appearing in technical_spec.output_types.
    """
    tspec = blueprint.technical_spec if isinstance(blueprint.technical_spec, dict) else {}
    out = tspec.get("output_types") or []
    if isinstance(out, str):
        out = [out]
    return any(str(o).lower() in ("pdf", "report") for o in out)


def _build_pdf_report_section(blueprint: Blueprint, schema_name: str) -> str:
    """Code injected after the JSON output write -- renders a formatted PDF.

    Empty string when PDF output is not requested. The block reads the
    template-set `_pdf_source` variable (each run_poc.py template assigns it from
    its own result variable just before this block) and writes `result_report.pdf`
    next to the JSON output."""
    if not _wants_pdf(blueprint):
        return ""
    title = _code_text(blueprint.use_case.name)
    blueprint_sha256 = blueprint.fingerprint()["blueprint_sha256"]
    return (
        "    # ----- PDF report (technical_spec.output_types includes 'pdf') -----\n"
        "    if _pdf_source is not None:\n"
        "        try:\n"
        "            from pdf_report import write_pdf_report\n"
        '            _pdf_path = output_dir / "result_report.pdf"\n'
        f'            write_pdf_report(_pdf_source, _pdf_path, title="{title}",\n'
        f'                             subtitle="{schema_name}",\n'
        f'                             metadata={{"Schema": "{schema_name}",\n'
        f'                                       "Blueprint SHA-256": "{blueprint_sha256}"}})\n'
        '            print(f"PDF report written to: {_pdf_path}")\n'
        "        except Exception as _pdf_exc:  # noqa: BLE001\n"
        '            print(f"WARNING: PDF report generation failed: {_pdf_exc}")\n'
    )


#: A reference card's verified import line: ``from <module> import A, B``.
_CARD_IMPORT_RE = re.compile(r"from (?P<module>[A-Za-z_][\w.]*) import (?P<names>[\w ,]+)")


def _component_import_lines(entry: dict) -> list[str]:
    """The import lines for a registry entry's classes, one name per line.

    They come from the entry's reference card, whose import line the _generic
    skeleton also shows. Most entries are named after their class, but a family
    entry such as ``Extractor`` is not one: its card imports ``SchemaGenerator``
    and ``DataExtractor``, and importing the family name would stop the run at
    its first line. A class that uses another class of its module, such as
    ``LLMJudgePanel`` with ``LLMJudge``, keeps its own import, and the classes
    it lists in ``uses_components`` that the same module exports are imported
    beside it: the panel is built from ``LLMJudge`` instances. Without a card
    the entry's own name is imported, as before.
    """
    from .registry import get_reference_cards, get_registry

    card = get_reference_cards().get(entry["name"]) or {}
    match = _CARD_IMPORT_RE.fullmatch(str(card.get("import", "")).strip())
    names = [name.strip() for name in match["names"].split(",") if name.strip()] if match else []
    lines = [f"from {match['module']} import {name}" for name in names] or [
        f"from {entry['import_path']} import {entry['name']}"
    ]
    import_path = entry["import_path"]
    registry = get_registry()
    for member in entry.get("uses_components") or []:
        if member == entry["name"]:
            continue
        if (registry.lookup_by_name(member) or {}).get("import_path") != import_path:
            continue
        line = f"from {import_path} import {member}"
        if line not in lines:
            lines.append(line)
    return lines


def _build_variables(blueprint: Blueprint, pattern: str) -> dict[str, Any]:
    """Build the substitution variables dict from the blueprint."""
    bc = blueprint
    problems = _code_values_problems(bc)
    if problems:
        raise ValueError("blueprint values cannot go into the PoC code: " + "; ".join(problems))
    models = bc.models or {}
    provider = _provider_name(models.get("provider", DEFAULT_PROVIDER))
    stages = _stage_settings(blueprint)
    _validate_stage_settings(
        stages, _needed_stages(blueprint, pattern), external_model_forbidden(blueprint)
    )
    governance = governance_problems(blueprint)
    if governance:
        raise ValueError(
            "The blueprint's governance flags refuse this PoC: " + "; ".join(governance)
        )
    use_azure = str(provider == "azure")

    # Determine model names
    transcription_model = _model_id(
        models.get("transcription_model", "gpt-4o-transcribe"), "models.transcription_model"
    )
    extraction_model = stages["extraction"].get("model")
    temperature = models.get("temperature", 0.0)

    schema_name = (
        bc.target_output_spec.get("schema_name")
        or bc.use_case.id.replace("_", " ").title().replace(" ", "")
        or "OutputSchema"
    )
    fields = bc.target_output_spec.get("fields", [])
    sample_field_lines = (
        "\n".join(f"  - {f}" for f in fields[:5]) if fields else "  (no fields defined)"
    )

    # Workflow steps summary for _generic template
    steps_summary = "\n".join(
        f"#   {i + 1}. {s.id} ({s.type}): {s.component or 'user_task'} {s.inputs} -> {s.outputs}"
        for i, s in enumerate(bc.workflow.steps)
    )

    # Component imports placeholder for _generic
    registry = get_registry()
    import_lines = []
    for step in bc.workflow.steps:
        if step.component and step.component not in ("custom", "human_review"):
            entry = registry.lookup_by_name(step.component) or registry.lookup_by_id(step.component)
            if entry and entry.get("import_path"):
                for line in _component_import_lines(entry):
                    if line not in import_lines:
                        import_lines.append(line)

    language = (
        bc.technical_spec.get("language", "en")
        if isinstance(bc.technical_spec, dict)
        else getattr(bc.technical_spec, "language", "en")
    )
    if not isinstance(language, str) or not _LANGUAGE_RE.fullmatch(language):
        # The generated code takes the language as a code (en, fi, sv-FI) or
        # "auto"; anything else falls back rather than reaching a string literal.
        language = "en"

    # LLMJudge section: inject real code if judge is in the selected pipeline,
    # otherwise inject a skip comment so run_poc.py stays syntactically valid.
    all_components = [
        m.name if hasattr(m, "name") else m.get("name", "") for m in bc.components.selected_modules
    ] + bc.components.selected_building_blocks
    has_llm_judge = "LLMJudge" in all_components
    has_source_tracing = "SourceTracing" in all_components or any(
        s.component == "SourceTracing" for s in bc.workflow.steps
    )

    if has_llm_judge:
        llm_judge_section = """\
    # -- LLMJudge hallucination detection (from blueprint) --
    # detect_hallucinations() checks each extracted field against the grounding
    # source text and flags any value not supported by it.
    # Uses the explicitly configured judge provider.
    print("\\nRunning LLMJudge hallucination detection...")
    try:
        from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
        judge = _LLMJudge(config=get_stage_config(config, "judge"))

        # Ground against the transcript or parsed document text.
        source_text = ""
        if hasattr(result, "transcription") and result.transcription:
            source_text = (
                getattr(result.transcription, "enhanced_transcript", None)
                or getattr(result.transcription, "raw_transcript", None)
                or ""
            )
        elif hasattr(result, "parsed_documents") and result.parsed_documents:
            source_text = "\\n\\n".join(result.parsed_documents)

        if source_text and result.extracted_fields:
            # The Extractor returns a list (multi-document pipeline).
            # detect_hallucinations() expects a plain dict, so unwrap
            # the first element for single-document PoC runs.
            extracted_for_judge = result.extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(
                source_text=source_text,
                extracted=extracted_for_judge,
            )
            # judge_error: the judge's response could not be read, so an empty
            # flag list is no verdict. gaik 0.8.14 has neither judge_error nor
            # passed; there an empty flag list is the only signal.
            judge_error = getattr(report, "judge_error", None)
            if report.flags:
                print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
                for flag in report.flags:
                    # The value and the reason quote content: shown only with --verbose.
                    print(f"  field={flag.field}" + (f"  value={flag.value}  reason={flag.reason}"
                                                     if poc_output.VERBOSE else ""))
            if judge_error:
                print(f"WARNING: the judge's response could not be read ({judge_error}).")
            elif not report.flags:
                print("Hallucination check passed -- all fields are grounded in the source.")
            validation_result = {
                "hallucination_flags": [
                    {"field": f.field, "value": f.value,
                     "severity": str(f.severity), "reason": f.reason}
                    for f in report.flags
                ],
                "judge_error": judge_error,
                "passed": getattr(report, "passed", not report.flags),
            }
            val_path = output_dir / f"{input_file.stem}_validation.json"
            val_path.write_text(
                json.dumps(validation_result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Validation report: {val_path}")
        else:
            print("LLMJudge skipped: no source text available for grounding.")
    except ImportError:
        print("LLMJudge skipped: gaik[llm-judge] not installed.")
    except Exception as _judge_exc:
        print(f"LLMJudge warning: {poc_output.short_error(_judge_exc)}")

    # -- Human review (blueprint step: supervisor_review) --
    print("\\nNOTE: Human review (supervisor approval) is not executed in the PoC.")
    print("      Gate 3 in the wizard conversation is the equivalent review step.")
    print("      In production, the approved_ticket artifact is produced here.")"""
    else:
        llm_judge_section = "    # LLMJudge and human_review are not in this blueprint's pipeline."

    handling = bc.governance.data_handling
    return {
        # Which blueprint the PoC came from (config.yaml and README.md carry it).
        "blueprint": bc.fingerprint(),
        "governance": {
            "external_model_api_allowed": handling.external_model_api_allowed,
            "local_processing_required": handling.local_processing_required,
            "contains_personal_data": handling.contains_personal_data,
            "local_endpoints": _local_endpoints(bc),
        },
        "allow_provider_fallback": models.get("allow_provider_fallback") is True,
        "use_case_name": bc.use_case.name,
        "use_case_id": bc.use_case.id,
        "use_case_description": bc.use_case.description,
        "schema_name": schema_name,
        "provider": provider,
        "use_azure": use_azure,
        "transcription_model": transcription_model,
        "extraction_model": extraction_model,
        "temperature": temperature,
        "stage_settings": stages,
        "language": language,
        "llm_judge_section": llm_judge_section,
        "source_tracing_setup": _build_source_tracing_setup(has_source_tracing),
        "source_tracing_section": _build_source_tracing_section(has_source_tracing, pattern),
        "eval_framework": _eval_framework(bc.evaluation),
        "eval_framework_body": _EVAL_BODIES.get(
            bc.evaluation.get("eval_framework", "") if isinstance(bc.evaluation, dict) else "",
            _DEFAULT_EVAL_BODY,
        ),
        "sample_field_lines": sample_field_lines,
        "workflow_steps_summary": steps_summary,
        # Every line commented out: the agent uncomments each as it wires its step.
        "component_imports_placeholder": "\n".join(f"# {line}" for line in import_lines),
        "input_instructions": _input_instructions(bc),
        "output_instructions": _output_instructions(bc),
        # technical_spec.external_services: their keys in .env.example, and the README section
        "external_services_env": _external_services_env(bc),
        "external_services_readme": _external_services_readme(bc),
        # _generic template extras
        "generic_pipeline_skeleton": _build_generic_pipeline_skeleton(bc),
        "generic_input_loaders": _build_input_loaders(bc),
        "llm_judge_section_generic": _build_generic_judge_section(has_llm_judge),
        # optional PDF report (empty unless output_types includes 'pdf')
        "pdf_report_section": _build_pdf_report_section(bc, schema_name),
    }


def _input_instructions(bp: Blueprint) -> str:
    input_types = (
        bp.technical_spec.get("input_types", [])
        if isinstance(bp.technical_spec, dict)
        else getattr(bp.technical_spec, "input_types", [])
    )
    if "audio" in input_types or "video" in input_types:
        lang = (
            bp.technical_spec.get("language", "")
            if isinstance(bp.technical_spec, dict)
            else getattr(bp.technical_spec, "language", "")
        )
        # A language code names the language; "auto" leaves it to the model.
        known = isinstance(lang, str) and _LANGUAGE_RE.fullmatch(lang) and lang != "auto"
        lang_note = f" in {lang.upper()}" if known else ""
        return (
            f"Place an audio recording{lang_note} (.wav or .mp3) in `sample_input/`.\n"
            "The pipeline will transcribe and enhance it before extraction."
        )
    if any(t in input_types for t in ("pdf", "docx", "document", "image")):
        return "Place a document (.pdf or .docx) in `sample_input/`."
    if "document_collection" in input_types:
        return (
            "Place one or more PDF documents in `sample_input/`. "
            "They will be indexed before you can query them."
        )
    return f"Place your input file in `sample_input/`. Expected types: {input_types}."


def _output_instructions(bp: Blueprint) -> str:
    fields = (
        bp.target_output_spec.get("fields", []) if isinstance(bp.target_output_spec, dict) else []
    )
    input_types = (
        bp.technical_spec.get("input_types", [])
        if isinstance(bp.technical_spec, dict)
        else getattr(bp.technical_spec, "input_types", [])
    )
    # Match the actual filenames the templates write:
    # audio template writes _ticket.json; document template writes _result.json
    suffix = "_ticket.json" if "audio" in input_types or "video" in input_types else "_result.json"
    if fields:
        # fields may be strings (extraction) or dicts (multi_source_report sections)
        field_names = [
            f.get("title", f.get("id", str(f))) if isinstance(f, dict) else str(f)
            for f in fields[:6]
        ]
        return (
            f"A JSON file with the following fields: {', '.join(field_names)}"
            + (" (and more)" if len(fields) > 6 else "")
            + f".\nWritten to `output/<input_stem>{suffix}`."
        )
    return f"Results written to `output/<input_stem>{suffix}`."


def _comment_text(value: Any, limit: int = 200) -> str:
    """Text for one comment line of a generated file: no line break or control character."""
    text = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _external_services_env(blueprint: Blueprint) -> str:
    """The .env.example lines of the external services: each one's own variables,
    empty, under a comment naming the service and what it is for. A name two services
    share is written once."""
    written: set[str] = set()
    blocks: list[str] = []
    for service in external_services(blueprint):
        names = [name for name in service.env_vars if name not in written]
        if not names:
            continue
        written.update(names)
        comment = _comment_text(f"{service.name}: {service.purpose}")
        blocks.append(f"# {comment}\n" + "\n".join(f"{name}=" for name in names))
    if not blocks:
        return ""
    return (
        "\n# --- External services (outside GAIK) ---\n"
        "# Without its key the PoC skips the step, says so in its log, and runs the rest.\n"
        + "\n\n".join(blocks)
        + "\n"
    )


def _external_services_readme(blueprint: Blueprint) -> str:
    """The README section on the external services, or "" when the blueprint has none."""
    block = external_services_block(blueprint)
    if not block:
        return ""
    return (
        "## External services\n\n"
        "Some steps use a service outside GAIK, with its own account and key in `.env`. "
        "Without the key or the package, the PoC skips the step, says so in its log "
        "(`SKIPPED <service>: ...`), and runs the GAIK steps; a test run without them "
        "shows those lines.\n\n" + block + "\n\n---\n"
    )


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------


def _normalised(name: str) -> str:
    """A project or extra name as pip compares it (PEP 503, PEP 685)."""
    return re.sub(r"[-_.]+", "-", name).lower()


_REQUIREMENT_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?\s*(.*)")


def _requirement_parts(line: str) -> tuple[str, set[str], set[str]]:
    """A requirement line's project name, extras and version specifiers, normalised."""
    match = _REQUIREMENT_RE.fullmatch(line.strip())
    if not match:
        return line, set(), set()
    name, extras, specifiers = match.groups()
    return (
        _normalised(name),
        {_normalised(e) for e in (extras or "").split(",") if e.strip()},
        {s.replace(" ", "") for s in specifiers.split(",") if s.strip()},
    )


def _external_requirements(blueprint: Blueprint, lines: list[str]) -> list[str]:
    """The external services' packages, each as written, unless it adds nothing.

    The blueprint refuses a service package that names gaik or another project
    written above (``POC_OWN_PROJECTS``), so no line here pins one of them. pip
    combines every line of one project: ``requests[socks]>=2.31`` beside
    ``requests>=2`` adds an extra and a stricter version, so it is kept. A line is
    left out only when the lines already there ask for all its extras and
    specifiers, as an exact duplicate or a bare name does.
    """
    required: dict[str, tuple[set[str], set[str]]] = {}

    def note(line: str) -> bool:
        """Record ``line``; True when it asks for something not asked for yet."""
        name, extras, specifiers = _requirement_parts(line)
        if name not in required:
            required[name] = (extras, specifiers)
            return True
        have_extras, have_specifiers = required[name]
        adds = not (extras <= have_extras and specifiers <= have_specifiers)
        have_extras |= extras
        have_specifiers |= specifiers
        return adds

    for line in lines:
        note(line)
    added = [
        service.python_package
        for service in external_services(blueprint)
        if service.python_package and note(service.python_package)
    ]
    if not added:
        return []
    return ["# Packages of the external services (README, External services)", *added]


def _write_requirements_txt(blueprint: Blueprint, poc_dir: Path) -> None:
    registry = get_registry()
    all_components = [
        m.name if hasattr(m, "name") else m.get("name", "")
        for m in blueprint.components.selected_modules
    ] + blueprint.components.selected_building_blocks
    lines = registry.pip_requirements(all_components)
    stages = _stage_settings(blueprint)
    for stage in sorted(_needed_stages(blueprint, _determine_pattern(blueprint))):
        extra = _PROVIDER_EXTRAS.get(stages[stage]["provider"])
        requirement = f"gaik[{extra}]"
        if extra and requirement not in lines:
            lines.append(requirement)
    spec = _gaik_version_spec()
    lines = [f"{line}{spec}" if line.startswith("gaik[") else line for line in lines]
    if not any(line.startswith("gaik[") for line in lines):
        lines.append(f"gaik{spec}")
    lines.append("pyyaml")
    if _wants_pdf(blueprint):
        lines.append("reportlab>=4.0")
    # After the gaik lines: a third-party package never replaces a gaik requirement.
    lines.extend(_external_requirements(blueprint, lines))
    (poc_dir / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pdf_report_helper(blueprint: Blueprint, poc_dir: Path) -> Path | None:
    """Copy the PDF report renderer into the PoC when PDF output is requested."""
    if not _wants_pdf(blueprint):
        return None
    tmpl = _read_template("_common", "pdf_report.py.tmpl") or ""
    path = poc_dir / "pdf_report.py"
    path.write_text(tmpl, encoding="utf-8")  # no template variables to fill
    return path


def _write_env_example(variables: dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "env.example.tmpl") or ""
    (poc_dir / ".env.example").write_text(_fill(tmpl, _for_code(variables)), encoding="utf-8")


def _write_config_yaml(variables: dict[str, Any], poc_dir: Path) -> None:
    import yaml

    config = {
        # The blueprint this PoC was generated from; compare blueprint_sha256 with
        # the current blueprint's to see whether the PoC needs scaffolding again.
        "blueprint": variables["blueprint"],
        "provider": variables["provider"],
        "use_azure": variables["provider"] == "azure",
        "models": {
            "transcription": variables["transcription_model"],
            "extraction": variables["extraction_model"],
            "temperature": variables["temperature"],
        },
        "stages": variables["stage_settings"],
        "language": variables["language"],
        # The blueprint's governance flags; provider_config.py refuses an external model
        # API at run time when they allow none.
        "governance": variables["governance"],
        # A stage without a provider fails unless the blueprint asked for the default.
        "allow_provider_fallback": variables["allow_provider_fallback"],
        "paths": {
            "sample_input": "sample_input/",
            "output": "output/",
            "schemas": "schemas/",
            "prompts": "prompts/",
        },
    }
    (poc_dir / "config.yaml").write_text(
        _fill(
            _read_template("_common", "config.yaml.tmpl") or "${settings_yaml}",
            {"settings_yaml": yaml.safe_dump(config, sort_keys=False, allow_unicode=True)},
        ),
        encoding="utf-8",
    )


def _write_run_poc(variables: dict[str, Any], pattern: str, poc_dir: Path) -> bool:
    """Write run_poc.py from pattern template. Returns True if a fully-wired template was used."""
    tmpl = _read_template(pattern, "run_poc.py.tmpl")
    if not tmpl:
        tmpl = _read_template("_generic", "run_poc.py.tmpl") or ""
    (poc_dir / "run_poc.py").write_text(_fill(tmpl, _for_code(variables)), encoding="utf-8")
    return pattern != "_generic"


def _write_eval_script(variables: dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "run_basic_eval.py.tmpl") or ""
    evals_dir = poc_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    script = _fill(tmpl, _for_code(variables))
    (evals_dir / "run_basic_eval.py").write_text(script, encoding="utf-8")
    (evals_dir / "ground_truth" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (evals_dir / "ground_truth" / ".gitkeep").touch()


def _write_readme(variables: dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "README.md.tmpl") or ""
    # Markdown: the use case's own words are shown as text, not read as markup.
    shown = {**variables, **{k: md_text(variables[k]) for k in _CODE_TEXT_KEYS if k in variables}}
    shown.update({f"{k}_text": md_text(v) for k, v in variables["blueprint"].items()})
    (poc_dir / "README.md").write_text(_fill(tmpl, shown), encoding="utf-8")


# ---------------------------------------------------------------------------
# The package's test page (app.py, ui/)
# ---------------------------------------------------------------------------

#: The file endings each wired entrypoint looks for in sample_input/.
_DOCUMENT_SUFFIXES = [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tiff", ".tif"]
_AUDIO_SUFFIXES = [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4"]
#: technical_spec.input_types -> (input kind, file endings) for a pipeline the
#: agent wires itself. A type that is not listed takes any file.
_INPUT_KINDS = {
    "audio": ("audio", _AUDIO_SUFFIXES),
    "video": ("audio", _AUDIO_SUFFIXES),
    "pdf": ("document", _DOCUMENT_SUFFIXES),
    "docx": ("document", _DOCUMENT_SUFFIXES),
    "document": ("document", _DOCUMENT_SUFFIXES),
    "image": ("document", _DOCUMENT_SUFFIXES),
    "document_collection": ("document", [".pdf"]),
    "text": ("text", [".txt", ".md"]),
    "csv": ("table", [".csv", ".xlsx"]),
    "xlsx": ("table", [".csv", ".xlsx"]),
    "excel": ("table", [".csv", ".xlsx"]),
    "spreadsheet": ("table", [".csv", ".xlsx"]),
    "tabular": ("table", [".csv", ".xlsx"]),
    "json": ("data", [".json"]),
}
_INPUT_LABELS = {
    "en": {
        "audio": "A recording",
        "document": "A document",
        "documents": "The documents to search",
        "text": "A text file, or text typed below",
        "table": "A table file",
        "data": "A data file",
        "file": "The solution's input files",
    },
    "fi": {
        "audio": "Äänite",
        "document": "Asiakirja",
        "documents": "Asiakirjat, joista haetaan",
        "text": "Tekstitiedosto tai alle kirjoitettu teksti",
        "table": "Taulukkotiedosto",
        "data": "Datatiedosto",
        "file": "Ratkaisun syötetiedostot",
    },
}
_QUESTION_LABELS = {"en": "Your question", "fi": "Kysymyksesi"}
#: The test page's fixed files: their place in the package and their template under
#: TEMPLATES_DIR. They are the same in every package, so wizard_api's package check
#: (``poc_service.package_problems``) can tell a changed copy from the one written here.
TEST_PAGE_TEMPLATES = {
    "app.py": "_common/app.py.tmpl",
    "ui/index.html": "_common/ui/index.html",
}
#: The page's own files beside index.html, copied as they are: the Sora font
#: (SIL Open Font License 1.1, its text beside the files) and the GAIK mark.
_PAGE_ASSETS = (
    "fonts/sora-latin-wght-normal.woff2",
    "fonts/sora-latin-ext-wght-normal.woff2",
    "fonts/OFL.txt",
    "gaik.svg",
)


def _short(value: Any, limit: int) -> str:
    """Free text for the page's data file: one line, no control characters, cut to ``limit``."""
    text = " ".join(str(value if value is not None else "").split())
    return "".join(ch for ch in text if ch.isprintable())[:limit]


def _spec_list(spec: Any, key: str) -> list:
    value = spec.get(key, []) if isinstance(spec, dict) else getattr(spec, key, [])
    return value if isinstance(value, list) else []


def _page_inputs(blueprint: Blueprint, pattern: str, ui_language: str) -> list[dict[str, Any]]:
    """What the test page lets the user add, following what the entrypoint reads."""
    labels = _INPUT_LABELS[ui_language]

    def entry(kind: str, suffixes: list[str], multiple: bool, label: str | None = None) -> dict:
        return {
            "kind": kind,
            "label": labels[label or kind],
            "extensions": list(suffixes),
            "multiple": multiple,
        }

    if pattern == "audio_to_structured":
        return [entry("audio", _AUDIO_SUFFIXES, False)]
    if pattern == "document_to_structured":
        return [entry("document", _DOCUMENT_SUFFIXES, False)]
    if pattern == "rag":
        return [entry("document", [".pdf"], True, "documents")]
    found: dict[str, dict] = {}
    for input_type in _spec_list(blueprint.technical_spec, "input_types"):
        kind, suffixes = _INPUT_KINDS.get(str(input_type).lower(), ("file", []))
        if kind in found:
            merged = found[kind]["extensions"]
            merged.extend(s for s in suffixes if s not in merged)
        else:
            found[kind] = entry(kind, suffixes, True)
    return list(found.values()) or [entry("file", [], True)]


def _page_output_fields(spec: Any) -> list[dict[str, str]]:
    """The output fields as the page labels them: key, label, type and description."""
    if not isinstance(spec, dict):
        return []
    types = spec.get("field_types") if isinstance(spec.get("field_types"), dict) else {}
    descriptions = (
        spec.get("field_descriptions") if isinstance(spec.get("field_descriptions"), dict) else {}
    )
    fields: list[dict[str, str]] = []
    for field in spec.get("fields") or []:
        if isinstance(field, dict):
            # A report's sections: {"id": ..., "title": ..., "instructions": ...}.
            key = _short(field.get("id") or field.get("title") or "", 100)
            label = _short(field.get("title") or key.replace("_", " ").capitalize(), 200)
            field_type, description = "text", ""
        else:
            key = _short(field, 100)
            label = key.replace("_", " ").capitalize()
            field_type = _short(types.get(field, "string"), 40)
            description = _short(descriptions.get(field, ""), 500)
        if not key:
            continue
        item = {"key": key, "label": label, "type": field_type}
        if description:
            item["description"] = description
        fields.append(item)
    return fields


#: workflow step type -> what the page calls the step. An automated task is "ai"
#: when a gaik component does it and "auto" otherwise; anything else is a plain step.
_STEP_KINDS = {
    "user_task": "input",
    "human_review": "review",
    "decision": "decision",
}
_MAX_PAGE_STEPS = 30
_MAX_STEP_ARTIFACTS = 6


def _artifact_names(names: Any) -> list[str]:
    """Artifact ids as words ("purchase_order_json" -> "purchase order json")."""
    if not isinstance(names, list):
        return []
    shown = (_short(str(name).replace("_", " "), 80) for name in names[:_MAX_STEP_ARTIFACTS])
    return [name for name in shown if name]


def _page_steps(blueprint: Blueprint) -> list[dict[str, Any]]:
    """The workflow's steps in the order they run, for the page's "how it works" strip.

    Each step is its title, what kind of step it is, the gaik component that does
    it (where one does) and the artifacts it uses and gives. A blueprint without
    steps gives an empty list, and the page shows no strip.
    """
    steps: list[dict[str, Any]] = []
    for step in _topo_order(list(blueprint.workflow.steps))[:_MAX_PAGE_STEPS]:
        title = _short(step.name, 200) or _short(str(step.id).replace("_", " "), 200)
        if not title:
            continue
        component = _short(step.component, 100)
        if str(step.type) == "automated_task":
            kind = "ai" if component else "auto"
        else:
            kind = _STEP_KINDS.get(str(step.type), "step")
        item: dict[str, Any] = {"id": _short(step.id, 100), "title": title, "kind": kind}
        if component:
            item["component"] = component
        item["uses"] = _artifact_names(step.inputs)
        item["gives"] = _artifact_names(step.outputs)
        steps.append(item)
    return steps


def _solution_description(
    blueprint: Blueprint, variables: dict[str, Any], pattern: str
) -> dict[str, Any]:
    """The data the test page reads: what the solution is, takes in and gives out."""
    language = str(variables.get("language") or "en")
    ui_language = "fi" if language.lower().startswith("fi") else "en"
    # Only the RAG entrypoint reads a question from a text file beside the documents.
    # A pipeline the agent wires takes typed text where its input_types say text.
    asks_question = pattern == "rag"
    return {
        "id": blueprint.use_case.id,
        "name": _short(blueprint.use_case.name, 200),
        "purpose": _short(blueprint.use_case.description, 1000),
        "language": ui_language,
        "content_language": language,
        "pattern": pattern,
        "inputs": _page_inputs(blueprint, pattern, ui_language),
        "asks_question": asks_question,
        "question_label": _QUESTION_LABELS[ui_language] if asks_question else "",
        "output_fields": _page_output_fields(blueprint.target_output_spec),
        "steps": _page_steps(blueprint),
    }


def _json_for_page(data: Any) -> str:
    """JSON whose text cannot end a tag or a script wherever a page puts it.

    The page reads this file with fetch and shows its values as text. The angle
    brackets and the ampersand are written as escapes all the same, so the file
    stays data if a later front end inlines it.
    """
    text = json.dumps(data, indent=2, ensure_ascii=False)
    for char in ("<", ">", "&", chr(0x2028), chr(0x2029)):
        text = text.replace(char, f"\\u{ord(char):04x}")
    return text + "\n"


def _write_test_page(
    blueprint: Blueprint, variables: dict[str, Any], pattern: str, poc_dir: Path
) -> list[Path]:
    """Write the package's own test page: app.py and ui/ (the page, its assets, solution.json).

    The server and the page (:data:`TEST_PAGE_TEMPLATES`) and the page's assets
    (its font files with their licence, the GAIK mark) are the same files in every
    package; only ``ui/solution.json`` comes from the blueprint, and as data. No
    blueprint value is written into the code or the markup.
    """
    written = []
    for relative, template in TEST_PAGE_TEMPLATES.items():
        target = poc_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_read_template(*template.rsplit("/", 1)) or "", encoding="utf-8")
        written.append(target)
    data_path = poc_dir / "ui" / "solution.json"
    data_path.write_text(
        _json_for_page(_solution_description(blueprint, variables, pattern)), encoding="utf-8"
    )
    written.append(data_path)
    source_dir = TEMPLATES_DIR / "_common" / "ui"
    for relative in _PAGE_ASSETS:
        target = poc_dir / "ui" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_dir / relative, target)
        written.append(target)
    return written


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def scaffold_poc(
    blueprint: Blueprint,
    output_dir: Path,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Scaffold the complete poc/ folder for a validated blueprint.

    Args:
        blueprint: a V1-validated Blueprint object
        output_dir: root output dir (e.g. ~/projects/my-use-case/)
        synthetic: if True, generate synthetic input data where possible

    Returns:
        dict with 'poc_dir', 'pattern', 'template_wired' (bool),
        'files' (list of created paths).
    """
    poc_dir = output_dir / "poc"
    poc_dir.mkdir(parents=True, exist_ok=True)

    pattern = _determine_pattern(blueprint)
    variables = _build_variables(blueprint, pattern)

    _needs_schema_dir = pattern not in ("rag", "multi_source_report")
    _base_subdirs = ["sample_input", "output", "prompts", "evals", "evals/ground_truth"]
    if _needs_schema_dir:
        _base_subdirs.append("schemas")
    for sub in _base_subdirs:
        (poc_dir / sub).mkdir(parents=True, exist_ok=True)

    files_created = []

    # Core boilerplate
    _write_requirements_txt(blueprint, poc_dir)
    files_created.append(poc_dir / "requirements.txt")

    _write_env_example(variables, poc_dir)
    files_created.append(poc_dir / ".env.example")

    _write_config_yaml(variables, poc_dir)
    files_created.append(poc_dir / "config.yaml")

    provider_helper = poc_dir / "provider_config.py"
    provider_helper.write_text(
        _read_template("_common", "provider_config.py.tmpl") or "", encoding="utf-8"
    )
    files_created.append(provider_helper)

    # Every package gets it: the agent decides only later whether the package
    # gates documents with a manifest, and a hand-written lookup missed (#251).
    manifest_helper = poc_dir / "document_manifest.py"
    manifest_helper.write_text(
        _read_template("_common", "document_manifest.py.tmpl") or "", encoding="utf-8"
    )
    files_created.append(manifest_helper)

    # Same reason for the inputs: a hand-written finder read only the top level of
    # sample_input/ and missed the case's bundle layout (UC05, #255).
    bundle_helper = poc_dir / "input_bundle.py"
    bundle_helper.write_text(
        _read_template("_common", "input_bundle.py.tmpl") or "", encoding="utf-8"
    )
    files_created.append(bundle_helper)

    output_helper = poc_dir / "poc_output.py"
    output_helper.write_text(
        _read_template("_common", "poc_output.py.tmpl") or "", encoding="utf-8"
    )
    files_created.append(output_helper)

    # Schema files
    # Primary path: if generate_schema.py was already run during Phase 5 of the
    # wizard conversation, the user-reviewed and approved files are already in
    # poc/schemas/. In that case, do NOT overwrite them with the deterministic
    # fallback -- the SchemaGenerator output takes precedence.
    _approved_schema = poc_dir / "schemas" / "output_schema.py"
    _approved_req = poc_dir / "schemas" / "output_schema_requirements.json"
    _schema_already_approved = _approved_schema.exists() and _approved_req.exists()

    has_fields = bool(
        blueprint.target_output_spec.get("fields")
        if isinstance(blueprint.target_output_spec, dict)
        else False
    )
    if _needs_schema_dir and _schema_already_approved:
        # SchemaGenerator output exists and was approved -- use as-is
        files_created.append(_approved_schema)
        files_created.append(_approved_req)
        # Write the hash file so run_poc.py can detect prompt changes from the
        # very first run instead of always re-checking without a baseline.
        _req_prompt = poc_dir / "prompts" / "extraction_requirements.md"
        _hash_file = poc_dir / "schemas" / "output_schema.hash"
        if _req_prompt.exists() and not _hash_file.exists():
            _hash_file.write_text(hashlib.sha256(_req_prompt.read_bytes()).hexdigest())
            files_created.append(_hash_file)
    elif has_fields and _needs_schema_dir:
        # Fallback: no approved schema yet, generate deterministically from
        # target_output_spec.  The wizard should have called generate_schema.py
        # first, but this keeps scaffolding self-contained when run standalone.
        schema_results = write_schema_files(
            blueprint.target_output_spec
            if isinstance(blueprint.target_output_spec, dict)
            else blueprint.target_output_spec.model_dump(),
            variables["schema_name"],
            poc_dir,
            use_case_name=blueprint.use_case.id,
        )
        files_created.extend(schema_results.values())

    # extraction_requirements.md -- always write from target_output_spec if absent
    _req_prompt = poc_dir / "prompts" / "extraction_requirements.md"
    if has_fields and _needs_schema_dir and not _req_prompt.exists():
        req_path = write_extraction_requirements(
            blueprint.target_output_spec
            if isinstance(blueprint.target_output_spec, dict)
            else blueprint.target_output_spec.model_dump(),
            poc_dir,
        )
        files_created.append(req_path)

    # run_poc.py
    template_wired = _write_run_poc(variables, pattern, poc_dir)
    files_created.append(poc_dir / "run_poc.py")

    # PDF report helper (only when technical_spec.output_types includes 'pdf')
    pdf_helper = _write_pdf_report_helper(blueprint, poc_dir)
    if pdf_helper is not None:
        files_created.append(pdf_helper)

    # Eval script
    _write_eval_script(variables, poc_dir)
    files_created.append(poc_dir / "evals" / "run_basic_eval.py")

    # README
    _write_readme(variables, poc_dir)
    files_created.append(poc_dir / "README.md")

    # The test page: a fixed server and page, and the blueprint's facts as data.
    files_created.extend(_write_test_page(blueprint, variables, pattern, poc_dir))

    # Synthetic data for document/RAG patterns.
    # Both DocumentsToStructuredData (vision_parser) and RAGWorkflow (VisionRagParser)
    # require PDF files.  We attempt to generate a minimal PDF via reportlab;
    # if unavailable, we write a .txt placeholder and warn -- the run_poc.py templates
    # will handle this gracefully with a clear error at runtime.
    if synthetic and pattern in ("document_to_structured", "rag"):
        sample_dir = poc_dir / "sample_input"
        sample_dir.mkdir(parents=True, exist_ok=True)
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as rl_canvas

            pdf_path = sample_dir / "synthetic_sample.pdf"
            c = rl_canvas.Canvas(str(pdf_path), pagesize=A4)
            c.drawString(50, 750, f"SYNTHETIC SAMPLE - {blueprint.use_case.name}")
            c.drawString(50, 730, "Generated by GAIK Solution Configuration Wizard V2.")
            c.drawString(50, 710, "Replace with a real document for meaningful results.")
            c.save()
            files_created.append(pdf_path)
        except ImportError:
            txt_path = sample_dir / "synthetic_sample.txt"
            txt_path.write_text(
                f"SYNTHETIC SAMPLE\nGenerated for {blueprint.use_case.name}.\n"
                "NOTE: Replace with a real PDF document.\n"
                "The vision parser requires PDF; this .txt file will cause a runtime error.",
                encoding="utf-8",
            )
            files_created.append(txt_path)

    # The first test run of a RAG package has no terminal and nobody's question
    # yet: without one it has nothing to answer. The entrypoint reads the text
    # files beside the documents as questions, one per line. A file of that
    # name that is already there is kept: it may hold the user's own questions.
    if synthetic and pattern == "rag":
        questions_path = poc_dir / "sample_input" / "sample_questions.txt"
        if not questions_path.exists():
            questions_path.write_text("What is this document about?\n", encoding="utf-8")
            files_created.append(questions_path)

    # The topology-aware key under which this pipeline's template would be saved
    # if the user later promotes it to the library (Part 2).
    pattern_key = _derive_pattern_key(blueprint)
    template_save_path = TEMPLATES_DIR / pattern_key / "run_poc.py.tmpl"

    # A stage without its own provider gets the default; say so instead of choosing silently.
    defaulted = defaulted_stages(blueprint)
    notes = (
        [
            f"No provider is set for the {', '.join(defaulted)} stage(s); config.yaml uses "
            f"the default {DEFAULT_PROVIDER!r}. Set models.provider to choose another."
        ]
        if defaulted
        else []
    )
    return {
        "notes": notes,
        "poc_dir": poc_dir,
        "pattern": pattern,
        "template_wired": template_wired,
        "pattern_key": pattern_key,
        "template_save_path": template_save_path,
        "files": files_created,
    }


def validate_generated_python(poc_dir: Path) -> str | None:
    """Try to parse run_poc.py -- returns error string or None if valid."""
    run_poc = poc_dir / "run_poc.py"
    if not run_poc.exists():
        return "run_poc.py not found"
    try:
        ast.parse(run_poc.read_text(encoding="utf-8"))
        return None
    except SyntaxError as exc:
        return str(exc)
