"""Prepares the blueprint the V1 scaffolder turns into a PoC package.

The scaffolder writes blueprint values into Python source: field and step ids
become identifiers, descriptions and names go between double quotes, and the
schema module it writes is loaded in this process to export JSON Schema. The
values come from the agent's draft or a blueprint PATCH, and nothing upstream
limits their characters, so they are made safe to place in source first.

Two rules, applied to the copy handed to the scaffolder:

* names that become identifiers must be identifiers; anything else is refused,
  because renaming one would break every reference to it;
* every other string loses the characters that can end a literal or a line
  (``"`` becomes ``”``, ``\\`` becomes ``/``, control characters become spaces).
  These are descriptions and labels, so the wording survives;
* a value the scaffolder writes into source as text (a field description, a
  section's instructions, the language) must be a string. The scaffolder turns
  anything else into text with ``str()``, and the quotes ``repr`` puts around a
  list item or a dict key are not the neutralised ones.

The model settings are checked too: the generated PoC sends the provider's API
key to the endpoint ``models`` names and resolves ``env:NAME`` values from its
environment. Written-out endpoints must be a known provider's; any other
endpoint comes from the environment (``env:...ENDPOINT``), and ``env:`` refers
only to settings, not to credentials.
"""

from __future__ import annotations

import copy
import keyword
import re
from typing import Any
from urllib.parse import urlsplit

# The eval framework name lands inside a generated f-string, so it stays a plain name.
_PLAIN_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_USE_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

_ENDPOINT_KEYS = ("base_url", "azure_endpoint", "azure_audio_endpoint")
#: Hosts a blueprint may write out as an endpoint: the providers' own APIs.
_PROVIDER_HOSTS = (
    ".openai.azure.com",
    ".services.ai.azure.com",
    ".cognitiveservices.azure.com",
    "api.openai.com",
    "api.anthropic.com",
    "aitta-api.csc.fi",
    "generativelanguage.googleapis.com",
)
_ENDPOINT_ENV = re.compile(r"^[A-Z][A-Z0-9_]*(ENDPOINT|BASE_URL|API_BASE)$")
_CREDENTIAL_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|DATABASE|DSN|PRIVATE|CERT", re.I)
#: Settings that become part of a provider's host name (Azure resource, Vertex
#: region) or its URL path (Vertex project): one DNS label each.
_HOST_PART_KEYS = ("resource", "location", "vertex_location", "project_id", "vertex_project")
_HOST_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")


class UnsafeBlueprintError(ValueError):
    """The blueprint has a name the scaffolder would paste into code as-is."""


def _is_identifier(value: Any) -> bool:
    return isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _field_names(fields: Any) -> list[Any]:
    """Field names whether ``fields`` is flat or a list of report sections, once each."""
    names: list[Any] = []
    for f in _list(fields):
        name = f.get("id") or f.get("title", "") if isinstance(f, dict) else f
        if name not in names:
            names.append(name)
    return names


def _not_text(value: Any) -> bool:
    """Set, but not a string: the scaffolder would write its ``str()`` into source."""
    return value not in (None, "") and not isinstance(value, str)


def _spec_problems(spec: Any, where: str) -> list[str]:
    if not isinstance(spec, dict):
        return []
    problems: list[str] = []
    name = spec.get("schema_name")
    if name not in (None, "") and not _is_identifier(name):
        problems.append(f"{where}.schema_name {name!r}")
    # Only ``fields`` become class attributes; the per-field maps are looked up
    # by those names, so a key that matches no field never reaches the source.
    for field in _field_names(spec.get("fields")):
        if not _is_identifier(field):
            problems.append(f"{where} field {field!r}")
    # A report section's instructions become its field description.
    for section in _list(spec.get("fields")):
        if isinstance(section, dict):
            for key in ("title", "instructions"):
                if _not_text(section.get(key)):
                    problems.append(f"{where} section {section.get('id')!r} {key} (must be text)")
    descriptions = spec.get("field_descriptions")
    if descriptions not in (None, {}) and not isinstance(descriptions, dict):
        problems.append(f"{where}.field_descriptions (must be a mapping of field to text)")
    for field, desc in _dict(descriptions).items():
        if _not_text(desc):
            problems.append(f"{where}.field_descriptions {field!r} (must be text)")
    nested = spec.get("nested")
    if isinstance(nested, dict):
        for container, child in nested.items():
            if not _is_identifier(container):
                problems.append(f"{where}.nested {container!r}")
            problems += _spec_problems(child, f"{where}.nested.{container}")
    return problems


def _env_name(value: Any) -> str | None:
    if isinstance(value, str) and value.strip()[:4].lower() == "env:":
        return value.strip()[4:].strip()
    return None


def endpoint_ok(value: str) -> bool:
    """A known provider's own https endpoint, or an ``env:...ENDPOINT`` reference."""
    name = _env_name(value)
    if name is not None:
        return bool(_ENDPOINT_ENV.match(name))
    try:
        url = urlsplit(value.strip())
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    return (
        url.scheme == "https"
        and not url.username
        and any(
            host == h.lstrip(".") or (h.startswith(".") and host.endswith(h))
            for h in _PROVIDER_HOSTS
        )
    )


def _model_problems(models: Any) -> list[str]:
    """Endpoints and ``env:`` references in ``models`` and each ``<stage>_config``."""
    if not isinstance(models, dict):
        return []
    found: list[str] = []
    blocks = [("models", models)] + [
        (f"models.{key}", value)
        for key, value in models.items()
        if key.endswith("_config") and isinstance(value, dict)
    ]
    for where, block in blocks:
        for key, value in block.items():
            if not isinstance(value, str) or not value.strip():
                continue
            name = _env_name(value)
            if key in _ENDPOINT_KEYS:
                if not endpoint_ok(value):
                    found.append(f"{where}.{key} {value!r} (not a known provider endpoint)")
            elif key in _HOST_PART_KEYS and name is None and not _HOST_PART.match(value):
                found.append(f"{where}.{key} {value!r}")
            elif name is not None and _CREDENTIAL_NAME.search(name):
                found.append(f"{where}.{key} {value!r} (env: refers to settings, not credentials)")
    return found


#: Components whose stage sends audio to a transcription model.
TRANSCRIBING_COMPONENTS = frozenset({"Transcriber", "ParallelTranscriber", "AudioToStructuredData"})
_TRANSCRIBING_MODULES = frozenset({"audio_to_structured_data", "AudioToStructuredData"})
#: Where the scaffolder finds a chat model, which every stage inherits unless
#: the stage names its own.
_CHAT_MODEL_KEYS = ("model", "extraction_model", "answer_model")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def transcribes_audio(v1: dict[str, Any]) -> bool:
    """Whether the blueprint's pipeline has a transcription stage."""
    components = _dict(v1.get("components"))
    for module in _list(components.get("selected_modules")):
        ids = (module.get("id"), module.get("name")) if isinstance(module, dict) else (module,)
        if any(i in _TRANSCRIBING_MODULES for i in ids if isinstance(i, str)):
            return True
    names = [b for b in _list(components.get("selected_building_blocks")) if isinstance(b, str)]
    names += [
        step.get("component")
        for step in _list(_dict(v1.get("workflow")).get("steps"))
        if isinstance(step, dict) and isinstance(step.get("component"), str)
    ]
    return any(name in TRANSCRIBING_COMPONENTS for name in names)


def transcription_model_problems(v1: dict[str, Any]) -> list[str]:
    """A transcription stage that would get the chat model.

    The scaffolder gives every stage the blueprint's chat model unless the stage
    names its own. For transcription that sends audio to a chat model, which the
    provider refuses at the first run. A blueprint without any model settings
    keeps the scaffolder's own transcription default and is not affected.
    Which model is named is not checked, only that one is.
    """
    if not transcribes_audio(v1):
        return []
    models = _dict(v1.get("models"))
    config = _dict(models.get("transcription_config"))
    named = (
        models.get("transcription_model"),
        config.get("model"),
        config.get("transcription_model"),
    )
    if any(_text(value) for value in named):
        return []
    if not any(_text(models.get(key)) for key in _CHAT_MODEL_KEYS):
        return []
    return [
        "models.transcription_model is not set: the pipeline transcribes audio, and without "
        "it the transcription stage would use the chat model, which cannot transcribe. Set "
        "models.transcription_model (or models.transcription_config.model) to the audio "
        "transcription model or deployment"
    ]


def problems(v1: dict[str, Any]) -> list[str]:
    """What in the V1 blueprint would reach generated code unchecked or fail its first run."""
    found = transcription_model_problems(v1)
    found += _spec_problems(v1.get("target_output_spec"), "target_output_spec")

    language = _dict(v1.get("technical_spec")).get("language")
    if _not_text(language):
        found.append("technical_spec.language (must be text)")

    use_case_id = _dict(v1.get("use_case")).get("id")
    if isinstance(use_case_id, str) and not _USE_CASE_ID.match(use_case_id):
        found.append(f"use_case.id {use_case_id!r}")

    artifacts = v1.get("artifacts")
    for art in artifacts if isinstance(artifacts, dict | list) else []:
        if not _is_identifier(art):
            found.append(f"artifact {art!r}")
    for step in _list(_dict(v1.get("workflow")).get("steps")):
        if not isinstance(step, dict):
            continue
        if not _is_identifier(step.get("id")):
            found.append(f"step id {step.get('id')!r}")
        for key in ("inputs", "outputs"):
            for art in _list(step.get(key)):
                if not _is_identifier(art):
                    found.append(f"step {step.get('id')!r} {key[:-1]} {art!r}")

    evaluation = v1.get("evaluation")
    framework = evaluation.get("eval_framework") if isinstance(evaluation, dict) else None
    if framework not in (None, "") and not (
        isinstance(framework, str) and _PLAIN_NAME.match(framework)
    ):
        found.append(f"evaluation.eval_framework {framework!r}")
    return found + _model_problems(v1.get("models"))


def _neutralise(value: Any) -> Any:
    if isinstance(value, str):
        return _CONTROL.sub(" ", value).replace('"', "”").replace("\\", "/")
    if isinstance(value, dict):
        return {k: _neutralise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_neutralise(v) for v in value]
    return value


def safe_for_scaffolding(v1: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``v1`` the scaffolder can paste into code without it running.

    Raises ``UnsafeBlueprintError`` naming every identifier that is not one.
    Keys are left alone: the ones that reach code are checked above, and the
    rest are the blueprint's own structure.
    """
    found = problems(v1)
    if found:
        raise UnsafeBlueprintError(
            "fix these before a PoC can be generated (names must be plain identifiers; "
            "endpoints must be a provider's own or come from env:...ENDPOINT; an audio "
            "pipeline names its transcription model): " + "; ".join(found)
        )
    return _neutralise(copy.deepcopy(v1))
