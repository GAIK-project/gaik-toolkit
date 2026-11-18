"""Run gaik's components on synthetic cases, per provider.

Covered: the schema generator, the extractor, the vision extractor, RAG (embedder, in-memory
vector store, retriever and answer generator), the tabular agent and the vision parser.
The components call each provider's API with the keys in the environment (or --env-file).
The optional judge (--judge claude|codex|agy) is a local CLI on its own subscription login:
every API key is removed from the judge's environment, so a judge call is never billed to
an API key. Outputs go to --out, which must be outside the repository.

    uv run python .claude/skills/component-check/run_checks.py --out ../component-check-runs/now
    uv run python .claude/skills/component-check/run_checks.py --providers azure,openai,google \
        --env-file .env --judge claude --baseline ../component-check-runs/before --out ...

See SKILL.md for reading the results.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
ROOT = SKILL_DIR.parents[2]
DEFAULT_CASES = SKILL_DIR / "cases.json"

PROVIDERS = ("azure", "openai", "google", "vertex", "aitta", "anthropic", "anthropic_foundry")
COMPONENTS = (
    "schema_generator",
    "extractor",
    "vision_extractor",
    "rag",
    "tabular_agent",
    "vision_parser",
)
# The components whose cases extract with the schema a schema_generator case made.
SCHEMA_CONSUMERS = ("extractor", "vision_extractor")
STATUSES = ("pass", "fail", "error", "skip")

# Providers whose API has no embeddings, so a RAG case cannot run on them.
NO_EMBEDDINGS = ("anthropic", "anthropic_foundry")

# Values whose names look like credentials are redacted from every error the run records.
SECRET_NAME = re.compile(r"(API_KEY|_TOKEN|TOKEN$|SECRET|PASSWORD|CREDENTIALS|SERVICE_ACCOUNT)")
SECRET_SHAPES = (
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
)

# A judge CLI uses its subscription login only while no API key or alternative endpoint
# is in its environment: Claude Code prefers ANTHROPIC_API_KEY, Codex OPENAI_API_KEY/
# CODEX_API_KEY, Antigravity GEMINI_API_KEY/GOOGLE_API_KEY.
JUDGE_DROP_EXACT = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "CODEX_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_PROJECT_ID",
}
JUDGE_DROP_PATTERN = re.compile(
    r"(API_KEY|API_TOKEN|_SECRET|SECRET_|PASSWORD|SERVICE_ACCOUNT|_ENDPOINT$|_BASE_URL$)"
)
# `claude setup-token` gives a subscription token, not an API key: keep it.
JUDGE_KEEP = {"CLAUDE_CODE_OAUTH_TOKEN"}

# The model a judge CLI gets when --judge-model is not given; None keeps the CLI's own default.
# GPT-6.2 Sol is the Codex model the maintainers chose for judging (2026-11).
DEFAULT_JUDGE_MODELS = {"codex": "gpt-6.2-sol"}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "problems": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["verdict", "problems", "notes"],
    "additionalProperties": False,
}

_print_lock = threading.Lock()


def say(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


# ---------------------------------------------------------------------------
# Environment, models and redaction
# ---------------------------------------------------------------------------


def load_env_files(paths: list[Path], override: bool) -> list[str]:
    """Load KEY=value files into os.environ; return the names set (never the values)."""
    from dotenv import dotenv_values

    loaded = []
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"--env-file {path} does not exist")
        for name, value in dotenv_values(path).items():
            if value is None:
                continue
            if override or not os.environ.get(name):
                os.environ[name] = value
                loaded.append(name)
    return loaded


def secret_values(environ: dict[str, str]) -> list[str]:
    values = {v for k, v in environ.items() if SECRET_NAME.search(k) and v and len(v) >= 8}
    return sorted(values, key=len, reverse=True)


def redact(text: str, secrets: list[str]) -> str:
    for value in secrets:
        text = text.replace(value, "***")
    for shape in SECRET_SHAPES:
        text = shape.sub("***", text)
    return text


def model_for(provider: str, overrides: dict[str, str], environ: dict[str, str]) -> str | None:
    """--model wins, then CHECK_<P>_MODEL, then RELEASE_<P>_MODEL; None lets gaik choose."""
    if provider in overrides:
        return overrides[provider]
    upper = provider.upper()
    for name in (f"CHECK_{upper}_MODEL", f"RELEASE_{upper}_MODEL"):
        if environ.get(name, "").strip():
            return environ[name].strip()
    return None


def vision_model_for(provider: str, model: str | None, environ: dict[str, str]) -> str | None:
    return environ.get(f"CHECK_{provider.upper()}_VISION_MODEL", "").strip() or model


def embedding_model_for(provider: str, environ: dict[str, str]) -> str | None:
    """CHECK_<P>_EMBEDDING_MODEL, then RELEASE_<P>_EMBEDDING_MODEL; None lets gaik choose."""
    upper = provider.upper()
    for name in (f"CHECK_{upper}_EMBEDDING_MODEL", f"RELEASE_{upper}_EMBEDDING_MODEL"):
        if environ.get(name, "").strip():
            return environ[name].strip()
    return None


def rag_skip_reason(provider: str, config: dict, embedding_model: str | None) -> str | None:
    """Why a RAG case cannot run on this provider, or None when it can."""
    if provider in NO_EMBEDDINGS:
        return f"{provider} has no embeddings API, so gaik's Embedder cannot run on it"
    if not (embedding_model or config.get("embedding_model")):
        return (
            f"gaik has no default embedding model for {provider}: "
            f"set CHECK_{provider.upper()}_EMBEDDING_MODEL"
        )
    return None


def parse_model_overrides(values: list[str]) -> dict[str, str]:
    overrides = {}
    for item in values:
        provider, sep, model = item.partition("=")
        if not sep or provider not in PROVIDERS or not model:
            raise SystemExit(f"--model takes provider=model with a provider in {PROVIDERS}")
        overrides[provider] = model
    return overrides


def provider_config(provider: str, model: str | None, timeout: float) -> dict:
    from gaik.software_components.llm import get_llm_config

    overrides: dict[str, Any] = {"timeout": timeout, "max_retries": 1}
    if model:
        overrides["model"] = model
    return get_llm_config(provider, **overrides)


# ---------------------------------------------------------------------------
# Comparing values
# ---------------------------------------------------------------------------

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "as_tuple"):  # Decimal
        return float(value)
    if not isinstance(value, str):
        return None
    text = re.sub(r"[^\d,.\-]", "", value.replace("−", "-"))
    if not text:
        return None
    if "," in text and "." in text:
        # The later separator is the decimal one: 1,250.00 or 1.234,50.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = f"{head.replace(',', '')}.{tail}" if len(tail) != 3 else text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def compare_value(expected: Any, actual: Any) -> tuple[bool, str]:
    """Whether an extracted value matches the expected one, and why not."""
    if expected is None:
        ok = actual in (None, "", [])
        return ok, "" if ok else f"expected None (empty), got {actual!r}"
    if isinstance(expected, bool):
        ok = actual is expected or _text(actual) in (
            {"true", "yes"} if expected else {"false", "no"}
        )
        return ok, "" if ok else f"expected {expected!r}, got {actual!r}"
    if isinstance(expected, (int, float)):
        number = _number(actual)
        ok = number is not None and abs(number - float(expected)) <= 0.005
        return ok, "" if ok else f"expected {expected!r}, got {actual!r}"
    if isinstance(expected, str) and _DATE.match(expected):
        if hasattr(actual, "isoformat"):
            actual_text = actual.isoformat()[:10]
        else:
            actual_text = str(actual or "").strip()[:10]
        ok = actual_text == expected
        return ok, "" if ok else f"expected {expected!r}, got {actual!r}"
    ok = _text(expected) == _text(actual)
    return ok, "" if ok else f"expected {expected!r}, got {actual!r}"


def compare_record(expected: dict, actual: Any, where: str) -> list[str]:
    if not isinstance(actual, dict):
        return [f"{where}: expected an object, got {type(actual).__name__}"]
    problems = []
    for name, value in expected.items():
        if name not in actual:
            problems.append(
                f"{where}.{name}: missing (keys: {', '.join(sorted(actual)) or 'none'})"
            )
            continue
        ok, detail = compare_value(value, actual[name])
        if not ok:
            problems.append(f"{where}.{name}: {detail}")
    return problems


def to_records(data: Any) -> list[dict]:
    """The records an extractor returned, whatever wrapper it used."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    if isinstance(data, list):
        return [d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in data]
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        scalars = [v for v in data.values() if not isinstance(v, (list, dict))]
        # A {"records": [...]} style wrapper around flat records.
        if len(data) == 1 and lists:
            return lists[0]
        if lists and not scalars and len(lists) == 1:
            return lists[0]
        return [data]
    return []


def find_items(record: dict, key: str) -> tuple[list | None, str]:
    if isinstance(record.get(key), list):
        return record[key], key
    lists = [
        (k, v) for k, v in record.items() if isinstance(v, list) and v and isinstance(v[0], dict)
    ]
    if len(lists) == 1:
        return lists[0][1], lists[0][0]
    return None, ""


def check_extraction(expect: dict, data: Any) -> list[str]:
    """Problems with an extractor's output against the case's expect block."""
    records = to_records(data)
    problems: list[str] = []
    if "records" in expect:
        wanted = expect["records"]
        if len(records) != len(wanted):
            problems.append(f"expected {len(wanted)} record(s), got {len(records)}")
        for index, (want, got) in enumerate(zip(wanted, records)):
            problems += compare_record(want, got, f"record[{index}]")
        return problems
    # One parent record with a nested list of items; flat rows are a failure.
    if len(records) != 1:
        return [f"expected 1 parent record, got {len(records)}"]
    record = records[0]
    problems += compare_record(expect.get("parent", {}), record, "parent")
    items, key = find_items(record, expect.get("items_key", ""))
    if items is None:
        return problems + [f"no list of items under {expect.get('items_key')!r}"]
    if key != expect.get("items_key"):
        problems.append(f"items came under {key!r}, not {expect.get('items_key')!r}")
    wanted = expect.get("items", [])
    if len(items) != len(wanted):
        problems.append(f"expected {len(wanted)} item(s), got {len(items)}")
    for index, (want, got) in enumerate(zip(wanted, items)):
        problems += compare_record(want, got, f"item[{index}]")
    return problems


# A number as a sentence writes it: 439.50, 439,50, 1,250.00 or 1 250,00. A comma or a
# point must be followed by a digit, so "2, 5 and 1" gives three numbers. Digits in a
# word or a code (INV-2026-0042, line_2) are not a number.
_NUMBER_TOKEN = re.compile(
    r"(?<![\w-])(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*)(?![\w-])"
)


def number_tokens(text: str) -> list[str]:
    """The numbers written in a text, as they are written."""
    return _NUMBER_TOKEN.findall(text or "")


# The typographic dashes (U+2010 to U+2015) and the minus sign (U+2212), read as a hyphen.
_DASHES = str.maketrans(dict.fromkeys([*range(0x2010, 0x2016), 0x2212], "-"))


def _plain_text(value: str) -> str:
    return _text(value).translate(_DASHES)


def check_contains(
    wanted: list, text: str, where: str, warnings: list[str] | None = None
) -> list[str]:
    """Each wanted string, or one of a list of alternatives, is in ``text``.

    Both sides are compared after normalising case and spaces, as compare_value does, and
    with a typographic dash read as a hyphen: a model writing markdown has set the hyphens
    of INV-2026-0042 as en dashes, every letter and digit right. A wrong or missing letter
    or digit still fails.
    """
    have = _plain_text(text or "")
    exact = _text(text or "")
    problems = []
    for item in wanted:
        options = [item] if isinstance(item, str) else list(item)
        if not any(_plain_text(option) in have for option in options):
            problems.append(f"{where} has no {' or '.join(repr(o) for o in options)}")
        elif warnings is not None and not any(_text(option) in exact for option in options):
            # Found only with the dashes folded: the value is not copied exactly.
            warnings.append(f"{where} writes {options[0]!r} with a typographic dash")
    return problems


# ---------------------------------------------------------------------------
# RAG, the tabular agent and the vision parser
# ---------------------------------------------------------------------------

_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_PAGE = re.compile(r"\bpage\b\s*:?\s*([0-9]+|unknown)", re.IGNORECASE)


def parse_citations(answer: str) -> list[dict]:
    """The citations in an answer, in the form gaik's AnswerGenerator asks for.

    That form is ``[document_name, page X]`` (also read: ``[Document: name, Page: X]``
    and several citations in one bracket separated by ``;``). A bracket without a page
    is not a citation in that form.
    """
    found = []
    for group in _BRACKET.findall(answer or ""):
        for part in group.split(";"):
            page = _PAGE.search(part)
            if not page:
                continue
            name = re.sub(r"^\s*document\s*:\s*", "", part.split(",")[0], flags=re.IGNORECASE)
            found.append(
                {
                    "text": part.strip(),
                    "document_name": name.strip().strip("'\"`*"),
                    "page": page.group(1).lower(),
                }
            )
    return found


def resolve_citations(citations: list[dict], retrieved: list[dict]) -> list[dict]:
    """Each citation with the source of the retrieved chunk it names (None if none).

    A citation names a chunk when its document name is the chunk's ``document_name``
    and its page is the chunk's page (a page of ``unknown`` matches any page).
    """
    resolved = []
    for citation in citations:
        source = None
        for chunk in retrieved:
            same_name = _text(citation["document_name"]) == _text(chunk.get("document_name", ""))
            page = citation["page"]
            if same_name and (page == "unknown" or page == str(chunk.get("page_number"))):
                source = chunk.get("source")
                break
        resolved.append({**citation, "source": source})
    return resolved


def check_rag(expect: dict, output: dict) -> list[str]:
    """Problems with a RAG answer: its content, the retrieval and its citations.

    The citations are read from the answer in gaik's citation form and resolved against
    the chunks the retriever returned (with their metadata), not matched as free text.
    """
    answer = output.get("answer") or ""
    problems = check_contains(expect.get("answer_contains", []), answer, "the answer")
    wanted = expect.get("cited_document")
    if not wanted:
        return problems
    retrieved = output.get("retrieved", [])
    if not any(chunk.get("source") == wanted for chunk in retrieved):
        got = [chunk.get("source") for chunk in retrieved]
        problems.append(f"the retriever did not return {wanted} (got {got})")
    citations = resolve_citations(parse_citations(answer), retrieved)
    if not citations:
        problems.append("the answer has no citation in the form [document_name, page X]")
    elif not any(c["source"] == wanted for c in citations):
        problems.append(
            f"no citation resolves to {wanted} (cited: {[c['text'] for c in citations]})"
        )
    unresolved = [c["text"] for c in citations if c["source"] is None]
    if unresolved:
        problems.append(f"citation(s) naming no retrieved chunk: {unresolved}")
    return problems


def check_tabular(expect: dict, output: dict) -> list[str]:
    """Problems with a tabular agent's answer: its query result and the number it states."""
    problems = []
    if not output.get("succeeded"):
        problems.append(
            f"the query failed after {output.get('attempts')} attempt(s): {output.get('error')}"
        )
    wanted = expect["number"]
    rows = output.get("rows") or []
    values = [value for row in rows for value in row.values()]
    if not any(compare_value(wanted, value)[0] for value in values):
        problems.append(f"the query result holds no {wanted!r} (rows: {rows[:5]})")
    answer = output.get("answer") or ""
    if not any(compare_value(wanted, token)[0] for token in number_tokens(answer)):
        problems.append(f"the answer states no {wanted!r}: {answer[:300]!r}")
    return problems


def check_markdown(expect: dict, output: dict, warnings: list[str] | None = None) -> list[str]:
    """Problems with a parser's markdown: the strings it must hold."""
    return check_contains(
        expect.get("contains", []), output.get("markdown") or "", "the markdown", warnings
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def describe_requirements(
    requirements: Any, structure_type: str, container: str | None = None
) -> dict:
    """Field names, types, enums, formats and defaults of generated requirements.

    ``container`` is the name of the list a ``nested_list`` schema puts its records in
    (gaik's ``StructureAnalysis.parent_container_name``); the requirements of such a
    schema are the fields of one record.
    """

    def fields_of(spec) -> dict:
        return {
            f.field_name: {
                "type": f.field_type,
                "enum": f.enum,
                "format": f.format,
                "default": f.default,
                "has_explicit_default": f.has_explicit_default,
                "nullable": f.nullable,
                "description": f.description,
            }
            for f in spec.fields
        }

    if hasattr(requirements, "parent_requirements"):
        return {
            "structure_type": structure_type,
            "fields": fields_of(requirements.parent_requirements),
            "children": {
                child.container_name: fields_of(child.requirements)
                for child in requirements.children
            },
        }
    observed = {"structure_type": structure_type, "fields": fields_of(requirements), "children": {}}
    if structure_type == "nested_list":
        observed["container"] = container
    return observed


def expected_children(expect: dict) -> dict[str, dict]:
    """The child lists a schema case expects: ``children``, or one ``child_container``."""
    if "children" in expect:
        return expect["children"]
    if "child_container" in expect:
        return {expect["child_container"]: expect.get("child_fields", {})}
    return {}


def _check_fields(wanted: dict, observed: dict, where: str, exact: bool) -> list[str]:
    problems = []
    for name, types in wanted.items():
        if name not in observed:
            problems.append(f"{where}: no field {name!r} (got {', '.join(observed) or 'none'})")
        elif observed[name]["type"] not in types:
            problems.append(f"{where}.{name}: type {observed[name]['type']!r}, expected {types}")
    if exact:
        extra = sorted(set(observed) - set(wanted))
        if extra:
            problems.append(f"{where}: unexpected field(s) {extra}")
    return problems


def check_schema(expect: dict, observed: dict) -> list[str]:
    problems = []
    if expect.get("structure_type") and observed["structure_type"] != expect["structure_type"]:
        problems.append(
            f"structure {observed['structure_type']!r}, expected {expect['structure_type']!r}"
        )
    problems += _check_fields(
        expect.get("fields", {}), observed["fields"], "fields", expect.get("exact_fields", False)
    )
    for name, values in expect.get("enums", {}).items():
        got = (observed["fields"].get(name) or {}).get("enum") or []
        if sorted(v.upper() for v in got) != sorted(v.upper() for v in values):
            problems.append(f"fields.{name}: enum {got}, expected {values}")
    for name, wanted in expect.get("formats", {}).items():
        got = (observed["fields"].get(name) or {}).get("format")
        if got != wanted:
            problems.append(f"fields.{name}: format {got!r}, expected {wanted!r}")
    for name, wanted in expect.get("defaults", {}).items():
        spec = observed["fields"].get(name) or {}
        if not spec.get("has_explicit_default"):
            problems.append(f"fields.{name}: no explicit default, expected {wanted!r}")
        elif not compare_value(wanted, spec.get("default"))[0]:
            problems.append(f"fields.{name}: default {spec.get('default')!r}, expected {wanted!r}")
    if "container" in expect and observed.get("container") != expect["container"]:
        problems.append(
            f"records listed under {observed.get('container')!r}, not {expect['container']!r}"
        )
    children = observed["children"]
    # A case that lists its children with ``children`` gets them exactly when exact_fields.
    exact_children = "children" in expect and expect.get("exact_fields", False)
    for container, fields in expected_children(expect).items():
        if container not in children:
            problems.append(f"no child list {container!r} (got {', '.join(children) or 'none'})")
        else:
            problems += _check_fields(fields, children[container], container, exact_children)
    if exact_children:
        extra = sorted(set(children) - set(expect["children"]))
        if extra:
            problems.append(f"unexpected child list(s) {extra}")
    return problems


def _resolve(root: dict, node: dict) -> dict:
    """Follow a local ``$ref`` (and a single non-null ``anyOf`` branch) in a JSON schema."""
    for _ in range(10):
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            node = root.get("$defs", {}).get(name, {})
        elif "anyOf" in node:
            branches = [b for b in node["anyOf"] if b.get("type") != "null"]
            if len(branches) != 1:
                return node
            node = branches[0]
        else:
            return node
    return node


def _enum_values(root: dict, node: dict) -> list[str]:
    """Every enum value a property's schema allows, wherever it is nested."""
    found: list[str] = []
    stack = [node]
    while stack:
        item = stack.pop()
        if "$ref" in item:
            item = _resolve(root, item)
        found += [str(v) for v in item.get("enum", [])]
        if "const" in item:
            found.append(str(item["const"]))
        for key in ("anyOf", "oneOf", "allOf"):
            stack += item.get(key, [])
    return found


def _list_item_properties(root: dict, properties: dict, container: str) -> dict | None:
    """The properties of one item of the list ``container``, or None if it is no list."""
    node = _resolve(root, properties.get(container, {}))
    if node.get("type") != "array":
        return None
    return _resolve(root, node.get("items", {})).get("properties", {})


def check_model(expect: dict, json_schema: dict) -> list[str]:
    """Problems with the generated model itself: its field names, enums, defaults and lists.

    For a ``nested_list`` case (``container`` in expect) the fields are those of one item
    of that list, which is the model's only property.
    """
    problems = []
    properties = _resolve(json_schema, json_schema).get("properties", {})
    where = "model"
    if "container" in expect:
        container = expect["container"]
        item = _list_item_properties(json_schema, properties, container)
        if item is None:
            return [f"model: {container!r} is not a list (got {', '.join(properties)})"]
        properties, where = item, f"model.{container}"
    for name in expect.get("fields", {}):
        if name not in properties:
            problems.append(f"{where}: no property {name!r} (got {', '.join(properties)})")
    for name, values in expect.get("enums", {}).items():
        if name in properties:
            # gaik adds an empty value to an enum the model may leave unanswered.
            got = [v for v in _enum_values(json_schema, properties[name]) if v != ""]
            if sorted(v.upper() for v in got) != sorted(v.upper() for v in values):
                problems.append(f"{where}.{name}: allows {got}, expected {values}")
    for name, wanted in expect.get("defaults", {}).items():
        if name in properties:
            got = properties[name].get("default")
            if not compare_value(wanted, got)[0]:
                problems.append(f"{where}.{name}: default {got!r}, expected {wanted!r}")
    for container, fields in expected_children(expect).items():
        item = _list_item_properties(json_schema, properties, container)
        if item is None:
            problems.append(f"model: {container!r} is not a list")
            continue
        for name in fields:
            if name not in item:
                problems.append(f"model.{container}: no property {name!r}")
    return problems


# ---------------------------------------------------------------------------
# Running one provider
# ---------------------------------------------------------------------------


def _usage(usage: Any) -> dict | None:
    if usage is None:
        return None
    names = ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens", "cost_usd")
    return {n: getattr(usage, n) for n in names if getattr(usage, n, None) is not None}


_USAGE_NAMES = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens"}
_USAGE_KEPT = ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens")


def usage_counts(usage: Any) -> dict[str, int]:
    """Token counts, by the names ``_usage`` gives, from an OpenAI response's ``usage``
    or a gaik usage dict (``prompt_tokens``/``completion_tokens``)."""
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in usage.items():
        name = _USAGE_NAMES.get(key, key)
        if name in _USAGE_KEPT and isinstance(value, int) and not isinstance(value, bool):
            counts[name] = counts.get(name, 0) + value
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if isinstance(reasoning, int) and reasoning:
        counts["thinking_tokens"] = counts.get("thinking_tokens", 0) + reasoning
    return counts


class UsageTap:
    """The token counts of the calls a component makes through its own client.

    gaik's Embedder, AnswerGenerator and TabularAgent return no usage. A gaik
    ProviderClient counts its calls itself (``usage``); for a raw OpenAI or Azure client
    the tap wraps that one instance's chat, parse and embeddings calls and adds up each
    response's ``usage``. Nothing else is changed, and a client in another thread (another
    provider) is never touched.
    """

    _CALLS = (
        ("chat", "completions", "create"),
        ("chat", "completions", "parse"),
        ("beta", "chat", "completions", "parse"),
        ("embeddings", "create"),
    )

    def __init__(self) -> None:
        self._totals: dict[str, int] = {}
        self._counters: list[tuple[Any, dict]] = []
        self._lock = threading.Lock()

    def watch(self, client: Any) -> None:
        counter = getattr(client, "usage", None)
        if hasattr(counter, "snapshot"):
            self._counters.append((counter, counter.snapshot()))
            return
        for path in self._CALLS:
            owner = client
            try:
                for name in path[:-1]:
                    owner = getattr(owner, name)
                call = getattr(owner, path[-1])
            except AttributeError:
                continue
            setattr(owner, path[-1], self._counted(call))

    def _counted(self, call):
        def counted(*args, **kwargs):
            response = call(*args, **kwargs)
            self._add(usage_counts(getattr(response, "usage", None)))
            return response

        return counted

    def _add(self, counts: dict[str, int]) -> None:
        with self._lock:
            for name, value in counts.items():
                self._totals[name] = self._totals.get(name, 0) + value

    def result(self) -> dict | None:
        for counter, before in self._counters:
            after = counter.snapshot()
            self._add(usage_counts({k: v - before.get(k, 0) for k, v in after.items()}))
        self._counters = []
        with self._lock:
            return dict(self._totals) or None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", "utf-8")


def _error(exc: BaseException, secrets: list[str], *, public: bool = False) -> dict:
    """An exception as type, status and (unless ``public``) its redacted message.

    ``--public`` (the CI run) keeps no message: a provider's error text can hold request
    details that redaction does not catch, and CI publishes the run's summary.
    """
    error = {"error_type": type(exc).__name__, "status_code": getattr(exc, "status_code", None)}
    error["message"] = "" if public else redact(str(exc), secrets)[:600]
    return error


def run_provider(
    provider: str, cases: list[dict], args, secrets: list[str], progress: dict | None = None
) -> dict:
    """Run every case for one provider; return its results keyed by case id.

    ``progress`` gets the provider's results as they come, so a run that stops
    waiting for a slow provider still reports the cases it finished.
    """
    if progress is not None:
        progress[provider] = {"_started": time.monotonic()}
    out_dir = args.out / provider
    environ = dict(os.environ)
    model = model_for(provider, args.model_overrides, environ)
    try:
        config = provider_config(provider, model, args.timeout)
        vision_model = vision_model_for(provider, model, environ)
        vision_config = (
            provider_config(provider, vision_model, args.timeout)
            if vision_model != model
            else config
        )
    except Exception as exc:  # missing credentials or an unknown provider
        reason = _error(exc, secrets)
        say(f"[{provider}] skipped: {reason['message'][:200]}")
        return {
            "provider": provider,
            "model": model,
            "skipped": reason,
            "cases": {
                c["id"]: {"status": "skip", "reason": "provider not configured"} for c in cases
            },
        }

    embedding_model = embedding_model_for(provider, environ)
    info = {
        "provider": provider,
        "model": config.get("model"),
        "vision_model": vision_config.get("model"),
        "embedding_model": embedding_model or config.get("embedding_model") or None,
    }
    results: dict[str, dict] = {}
    if progress is not None:
        progress[provider].update(info, cases=results)
    schemas: dict[str, dict] = {}
    reuse = args.reuse_schemas / provider if args.reuse_schemas else None

    def attempt(case: dict, case_dir: Path) -> dict:
        """One run of a case: its entry, with status pass, fail, error or skip."""
        entry: dict[str, Any] = {"component": case["component"], "title": case.get("title", "")}
        try:
            if case["component"] == "schema_generator":
                output = _run_schema(case, config, reuse)
                schemas[case["id"]] = output
                entry["observed"] = output["observed"]
                expect = case.get("expect", {})
                entry["problems"] = check_schema(expect, output["observed"]) + check_model(
                    expect, output["json_schema"]
                )
                _write_json(case_dir / "requirements.json", output["requirements_json"])
                _write_json(case_dir / "json_schema.json", output["json_schema"])
                _write_json(case_dir / "structure.json", output["structure"])
                entry["usage"] = output.get("usage")
            elif case["component"] not in SCHEMA_CONSUMERS:
                if case["component"] == "rag":
                    reason = rag_skip_reason(provider, config, embedding_model)
                    if reason:
                        entry.update(status="skip", reason=reason)
                        return entry
                    data, usage = _run_rag(case, config, embedding_model)
                    entry["problems"] = check_rag(case.get("expect", {}), data)
                elif case["component"] == "tabular_agent":
                    data, usage = _run_tabular(case, config)
                    entry["problems"] = check_tabular(case.get("expect", {}), data)
                else:
                    data, usage = _run_vision_parser(case, vision_config)
                    warnings: list[str] = []
                    entry["problems"] = check_markdown(case.get("expect", {}), data, warnings)
                    if warnings:
                        entry["warnings"] = warnings
                _write_json(case_dir / "result.json", data)
                entry["output"] = data
                entry["usage"] = usage
            else:
                parent = schemas.get(case.get("schema_from", ""))
                if parent is None:
                    entry.update(status="skip", reason=f"no schema from {case.get('schema_from')}")
                    return entry
                if parent.get("failed") and not args.keep_going:
                    entry.update(status="skip", reason=f"{case['schema_from']} failed its checks")
                    return entry
                if case["component"] == "extractor":
                    data, usage = _run_extractor(case, config, parent)
                else:
                    data, usage = _run_vision(case, vision_config, parent)
                _write_json(case_dir / "result.json", data)
                entry["output"] = data
                entry["usage"] = usage
                entry["problems"] = check_extraction(case.get("expect", {}), data)
            entry["status"] = "fail" if entry["problems"] else "pass"
            if case["component"] == "schema_generator":
                schemas[case["id"]]["failed"] = bool(entry["problems"])
        except Exception as exc:
            entry.update(status="error", **_error(exc, secrets, public=args.public))
        return entry

    for case in cases:
        case_dir = out_dir / case["id"]
        started = time.monotonic()
        earlier: list[dict] = []
        tries = max(1, args.attempts)
        for number in range(1, tries + 1):
            entry = attempt(case, case_dir)
            if entry["status"] not in ("fail", "error") or number == tries:
                break
            # Kept in the report, so a case that needed another attempt stays visible.
            earlier.append(
                {k: entry[k] for k in ("status", "problems", "error_type", "message") if k in entry}
            )
            say(f"[{provider}] {case['id']}: {entry['status']} on attempt {number}, trying again")
        if earlier:
            entry["attempts"] = len(earlier) + 1
            entry["earlier_attempts"] = earlier
        entry["elapsed_s"] = round(time.monotonic() - started, 2)
        if entry["status"] == "skip":
            _write_json(case_dir / "checks.json", entry)
            results[case["id"]] = entry
            say(f"[{provider}] {case['id']}: skip ({entry['reason']})")
            continue

        if args.judge and entry["status"] in ("pass", "fail"):
            entry["judge"] = judge_case(case, entry, args)

        _write_json(case_dir / "checks.json", {k: v for k, v in entry.items() if k != "output"})
        results[case["id"]] = entry
        verdict = f", judge {entry['judge'].get('verdict')}" if entry.get("judge") else ""
        say(f"[{provider}] {case['id']}: {entry['status']} ({entry['elapsed_s']} s{verdict})")

    return {**info, "cases": results}


def _run_schema(case: dict, config: dict, reuse: Path | None) -> dict:
    from gaik.software_components.extractor import SchemaGenerator
    from gaik.software_components.extractor.schema import (
        CompositeExtractionRequirements,
        ExtractionRequirements,
        _create_parent_with_nested_list_model,
        create_extraction_model,
    )

    if reuse is not None:
        saved = reuse / case["id"] / "requirements.json"
        if not saved.is_file():
            raise FileNotFoundError(f"--reuse-schemas has no {saved}")
        raw = json.loads(saved.read_text("utf-8"))
        structure_file = saved.parent / "structure.json"
        saved_structure = (
            json.loads(structure_file.read_text("utf-8")) if structure_file.is_file() else {}
        )
        if saved_structure.get("structure_type") == "nested_list":
            # The saved requirements are the item fields only; the list around them comes
            # from the structure analysis, which this runner does not rebuild.
            raise ValueError(
                f"--reuse-schemas cannot rebuild the nested_list schema of {case['id']}; "
                "run that case without it"
            )
        if raw.get("structure_type") == "parent_with_nested_list":
            requirements = CompositeExtractionRequirements.model_validate(raw)
            # The builder generate_schema itself uses for a nested schema.
            schema = _create_parent_with_nested_list_model(
                parent_requirements=requirements.parent_requirements,
                children=requirements.children,
            )
        else:
            requirements = ExtractionRequirements.model_validate(raw)
            schema = create_extraction_model(requirements)
        structure = raw.get("structure_type") or saved_structure.get("structure_type", "flat")
        container = None
        usage = None
    else:
        generator = SchemaGenerator(config)
        result = generator.generate_schema_with_usage(case["requirements"])
        schema, requirements = result.schema, result.requirements
        structure = result.structure_analysis.structure_type
        # A nested_list schema is one list of records; this is the list's field name.
        container = (
            result.structure_analysis.parent_container_name if structure == "nested_list" else None
        )
        usage = _usage(result.usage)
    saved = {"structure_type": structure}
    if container is not None:
        saved["parent_container_name"] = container
    return {
        "schema": schema,
        "requirements": requirements,
        "user_requirements": case["requirements"],
        "requirements_json": requirements.model_dump(mode="json"),
        "json_schema": schema.model_json_schema(),
        "observed": describe_requirements(requirements, structure, container),
        "structure": saved,
        "usage": usage,
    }


def _read(path: str) -> str:
    return (SKILL_DIR / path).read_text(encoding="utf-8")


def _run_extractor(case: dict, config: dict, parent: dict) -> tuple[Any, dict | None]:
    from gaik.software_components.extractor import DataExtractor

    result = DataExtractor(config).extract_with_usage(
        extraction_model=parent["schema"],
        requirements=parent["requirements"],
        user_requirements=parent["user_requirements"],
        documents=[_read(p) for p in case["documents"]],
    )
    return result.data, _usage(result.usage)


def _run_vision(case: dict, config: dict, parent: dict) -> tuple[Any, dict | None]:
    from gaik.software_components.vision_extractor import VisionExtractor

    result = VisionExtractor(api_config=config).extract(
        file_paths=[SKILL_DIR / p for p in case["files"]],
        user_requirements=parent["user_requirements"],
        extraction_model=parent["schema"],
        requirements=parent["requirements"],
    )
    return result.data, _usage(result.usage)


def _run_rag(case: dict, config: dict, embedding_model: str | None) -> tuple[dict, dict | None]:
    """Index the case's documents in memory and answer its question with citations.

    No parser: each document is one chunk (a fixture is one page), with the metadata
    gaik's answer generator builds its citations from.
    """
    from gaik.software_components.RAG.answer_generator import AnswerGenerator
    from gaik.software_components.RAG.embedder import Embedder
    from gaik.software_components.RAG.retriever import Retriever
    from gaik.software_components.RAG.vector_store import VectorStore
    from langchain_core.documents import Document

    chunks = [
        Document(
            page_content=_read(path),
            metadata={
                "document_name": Path(path).name,
                "page_number": 1,
                "chunk_id": 0,
                "source": path,
            },
        )
        for path in case["documents"]
    ]
    tap = UsageTap()
    embedder = Embedder(config, model=embedding_model)
    tap.watch(embedder.client)
    store = VectorStore()
    vectors, documents = embedder.embed(chunks)
    store.add(documents, vectors)
    retriever = Retriever(embedder=embedder, vector_store=store, top_k=case.get("top_k", 5))
    found = retriever.search(case["question"], include_scores=True)
    generator = AnswerGenerator(config=config, citations=True, stream=False)
    tap.watch(generator.client)
    answer = generator.generate(case["question"], found)
    retrieved = [
        {
            "document_name": doc.metadata.get("document_name"),
            "page_number": doc.metadata.get("page_number"),
            "source": doc.metadata.get("source"),
            "score": round(float(doc.metadata.get("relevance_score", 0.0)), 4),
        }
        for doc in found
    ]
    output = {
        "question": case["question"],
        "embedding_model": embedder.model,
        "answer": answer,
        "retrieved": retrieved,
        "citations": resolve_citations(parse_citations(answer), retrieved),
    }
    return output, tap.result()


def _run_tabular(case: dict, config: dict) -> tuple[dict, dict | None]:
    from gaik.software_components.tabular_agent import TabularAgent

    tap = UsageTap()
    with TabularAgent([SKILL_DIR / p for p in case["files"]], config=config) as agent:
        # The agent builds its client on first use; this is the one its calls go through.
        tap.watch(agent._get_llm_client())
        result = agent.ask(case["question"])
        tables = agent.table_names
    query = result.query_result
    output = {
        "question": case["question"],
        "tables": tables,
        "answer": result.answer,
        "sql": query.sql,
        "rows": query.rows,
        "succeeded": query.succeeded,
        "attempts": query.attempts,
        "error": query.error,
    }
    return output, tap.result()


def _run_vision_parser(case: dict, config: dict) -> tuple[dict, dict | None]:
    from gaik.software_components.parsers.vision import VisionParser

    parser = VisionParser(config)
    pages: list[str] = []
    for path in case["files"]:
        pages += parser.convert_pdf(str(SKILL_DIR / path))
    output = {"pages": len(pages), "markdown": "\n\n".join(pages)}
    return output, usage_counts(parser.usage.snapshot()) or None


# ---------------------------------------------------------------------------
# Judge on a subscription CLI
# ---------------------------------------------------------------------------


def judge_env(environ: dict[str, str]) -> dict[str, str]:
    """The environment for a judge CLI: no API key, so it runs on its own login."""
    return {
        name: value
        for name, value in environ.items()
        if name in JUDGE_KEEP
        or (name not in JUDGE_DROP_EXACT and not JUDGE_DROP_PATTERN.search(name))
    }


def login_problem(kind: str, status_output: str) -> str | None:
    """Why a judge CLI's login is not a subscription login, or None when it is.

    ``status_output`` is what ``claude auth status`` or ``codex login status`` printed
    with the judge's environment. Antigravity has no status command; it signs in with
    Google only.
    """
    if kind == "claude":
        status = _parse_json(status_output) or {}
        if not status.get("loggedIn"):
            return "claude is not signed in (run claude, then /login)"
        if status.get("authMethod") != "claude.ai" or status.get("apiProvider") not in (
            None,
            "firstParty",
        ):
            method = status.get("authMethod")
            return f"claude signs in with {method!r}, not a Claude subscription"
        return None
    if kind == "codex":
        if "ChatGPT" not in status_output:
            return "codex is not signed in with ChatGPT (run codex login)"
        return None
    return None


def check_judge_login(kind: str) -> None:
    """Stop before any component call when the judge would not run on a subscription."""
    commands = {"claude": ["auth", "status"], "codex": ["login", "status"]}
    if kind not in commands:
        return
    exe = shutil.which(kind)
    try:
        done = subprocess.run(
            [exe, *commands[kind]],
            env=judge_env(dict(os.environ)),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=60,
        )
        output = (done.stdout or "") + (done.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"--judge {kind}: could not read its login ({type(exc).__name__})")
    problem = login_problem(kind, output)
    if problem:
        raise SystemExit(f"--judge {kind}: {problem}; no judge call would be a subscription call")


_EXTRACTION_DEFECTS = "wrong or invented value, missing or extra field, wrong type or order"

# Per component: what the judge is told it checks, and the defects to look for.
JUDGE_SUBJECTS = {
    "schema_generator": ("a document-extraction component", _EXTRACTION_DEFECTS),
    "extractor": ("a document-extraction component", _EXTRACTION_DEFECTS),
    "vision_extractor": ("a document-extraction component", _EXTRACTION_DEFECTS),
    "rag": (
        "a retrieval-augmented question-answering pipeline (embedder, vector store, "
        "retriever and answer generator)",
        "wrong or invented value, an answer the documents do not support, a citation to "
        "the wrong document or to none",
    ),
    "tabular_agent": (
        "a text-to-SQL agent that answers a question about a CSV file",
        "wrong number, SQL that does not answer the question, an answer the query rows "
        "do not support",
    ),
    "vision_parser": (
        "a parser that turns a PDF page image into markdown",
        "misread, missing or invented text, a lost or merged table row or column",
    ),
}


def _texts(paths: list[str]) -> str:
    return "\n\n".join(f"--- {p} ---\n{_read(p)}" for p in paths if p)


def judge_prompt(case: dict, entry: dict) -> str:
    component = case["component"]
    output = entry.get("output")
    if component == "schema_generator":
        given = f"Task given to the schema generator:\n{case['requirements']}"
        output = entry.get("observed")
    elif component == "rag":
        given = f"Documents indexed:\n{_texts(case['documents'])}\n\nQuestion: {case['question']}"
    elif component == "tabular_agent":
        given = f"Files loaded:\n{_texts(case['files'])}\n\nQuestion: {case['question']}"
    else:
        paths = case.get("documents") or [case.get("source_text")]
        label = "Documents" if case.get("documents") else "Text the page image was rendered from"
        given = f"{label}:\n{_texts(paths)}"
    subject, defects = JUDGE_SUBJECTS[component]
    return (
        f"You check one output of {subject} against its input. "
        "All data here is synthetic. Do not use tools; answer only with JSON matching the "
        f"schema: verdict pass or fail, problems as a list of concrete defects ({defects}), "
        "notes as one sentence. Write in English.\n\n"
        f"Case: {case.get('title', case['id'])}\n\n{given}\n\n"
        f"What a correct output does: {case.get('rubric', '')}\n\n"
        f"Component output:\n{json.dumps(output, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Problems the fixed checks already found (may be empty): "
        f"{json.dumps(entry.get('problems', []), ensure_ascii=False)}\n"
    )


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    for candidate in (text, *re.findall(r"\{.*\}", text, flags=re.S)):
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def judge_command(
    kind: str, model: str | None, work: Path, prompt: str
) -> tuple[list[str], str | None]:
    """The CLI call for a judge, and what goes to its stdin."""
    exe = shutil.which(kind)
    if exe is None:
        raise FileNotFoundError(f"{kind} is not on PATH")
    if kind == "claude":
        cmd = [
            exe,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(JUDGE_SCHEMA),
            "--tools",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        return cmd + (["--model", model] if model else []), prompt
    if kind == "codex":
        (work / "schema.json").write_text(json.dumps(JUDGE_SCHEMA), "utf-8")
        cmd = [
            exe,
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--output-schema",
            str(work / "schema.json"),
            "-o",
            str(work / "answer.txt"),
        ]
        return cmd + (["-m", model] if model else []) + ["-"], prompt
    if kind == "agy":
        cmd = [
            exe,
            "--mode",
            "plan",
            "--sandbox",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(JUDGE_SCHEMA),
        ]
        return cmd + (["--model", model] if model else []) + ["-p", prompt], None
    raise ValueError(f"unknown judge {kind!r}")


def judge_case(case: dict, entry: dict, args) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="component-judge-") as tmp:
        work = Path(tmp)
        try:
            model = args.judge_model or DEFAULT_JUDGE_MODELS.get(args.judge)
            cmd, stdin = judge_command(args.judge, model, work, judge_prompt(case, entry))
            done = subprocess.run(
                cmd,
                input=stdin,
                cwd=work,
                env=judge_env(dict(os.environ)),
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=args.judge_timeout,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return {"verdict": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        answer = None
        if args.judge == "codex" and (work / "answer.txt").is_file():
            answer = _parse_json((work / "answer.txt").read_text("utf-8"))
        else:
            # claude -p and agy -p both print one JSON object with a structured_output.
            outer = _parse_json(done.stdout) or {}
            answer = outer.get("structured_output") or _parse_json(
                str(outer.get("result") or outer.get("response") or "")
            )
            if outer.get("is_error") or outer.get("status") not in (None, "SUCCESS"):
                answer = None
    elapsed = round(time.monotonic() - started, 1)
    if done.returncode != 0 or not answer or answer.get("verdict") not in ("pass", "fail"):
        tail = (done.stderr or done.stdout or "").strip()[-300:]
        return {
            "verdict": "error",
            "returncode": done.returncode,
            "error": tail,
            "elapsed_s": elapsed,
        }
    return {**answer, "judge": args.judge, "elapsed_s": elapsed}


# ---------------------------------------------------------------------------
# Summary and baseline
# ---------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """A value as it reads back from summary.json (Decimal and date as text)."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def diff_baseline(current: dict, baseline: dict) -> list[str]:
    """Cases that passed in the baseline and do not now, and outputs that changed."""
    notes = []
    for provider, now in current["providers"].items():
        before = baseline.get("providers", {}).get(provider)
        if not before:
            continue
        for case_id, entry in now["cases"].items():
            old = before.get("cases", {}).get(case_id)
            if not old:
                continue
            if old["status"] == "pass" and entry["status"] != "pass":
                notes.append(f"{provider} / {case_id}: was pass, now {entry['status']}")
            if (
                "output" in old
                and "output" in entry
                and _plain(old["output"]) != _plain(entry["output"])
            ):
                notes.append(f"{provider} / {case_id}: output differs from the baseline")
            if (
                "observed" in old
                and "observed" in entry
                and _contract(old["observed"]) != _contract(entry["observed"])
            ):
                notes.append(f"{provider} / {case_id}: schema differs from the baseline")
    return notes


def _contract(observed: dict) -> Any:
    """A generated schema's names, types, enums, formats, defaults and structure.

    Descriptions are left out (their wording varies), and so is an unset value (None or
    False), so a run that records more about a field than an older one does not differ
    from it on that account.
    """

    def strip(fields: dict) -> dict:
        return {
            name: {
                k: v
                for k, v in spec.items()
                if k != "description" and v is not None and v is not False
            }
            for name, spec in fields.items()
        }

    return _plain(
        {
            "structure_type": observed.get("structure_type"),
            "container": observed.get("container"),
            "fields": strip(observed.get("fields", {})),
            "children": {k: strip(v) for k, v in observed.get("children", {}).items()},
        }
    )


def render_summary(summary: dict) -> str:
    providers = list(summary["providers"])
    lines = [
        f"# Component check {summary['started']}",
        "",
        f"gaik {summary['gaik_version']} from `{summary['gaik_from']}`, commit "
        f"{summary['git_commit']}{' (uncommitted changes)' if summary['git_dirty'] else ''}.",
        f"Judge: {summary['judge'] or 'none'}.",
        "",
        "| Provider | Model | Vision model | Embedding model | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, result in summary["providers"].items():
        note = ""
        if result.get("skipped"):
            note = "not configured: " + result["skipped"]["message"][:120]
        elif result.get("timed_out"):
            note = "stopped waiting (--provider-timeout); unfinished cases are errors"
        model, vision = result.get("model") or "-", result.get("vision_model") or "-"
        embedding = result.get("embedding_model") or "-"
        lines.append(f"| {name} | {model} | {vision} | {embedding} | {note} |")
    lines += ["", "| Case | " + " | ".join(providers) + " |", "| --- |" + " --- |" * len(providers)]
    for case_id in summary["case_ids"]:
        cells = []
        for provider in providers:
            entry = summary["providers"][provider]["cases"].get(case_id, {})
            cell = entry.get("status", "-")
            if entry.get("attempts"):
                cell += f" (attempt {entry['attempts']})"
            if entry.get("warnings"):
                cell += " (warning)"
            if entry.get("judge"):
                cell += f" / judge {entry['judge'].get('verdict')}"
            cells.append(cell)
        lines.append(f"| {case_id} | " + " | ".join(cells) + " |")
    details = []
    for provider in providers:
        for case_id, entry in summary["providers"][provider]["cases"].items():
            judge = entry.get("judge") or {}
            if entry["status"] in ("fail", "error") or judge.get("verdict") in ("fail", "error"):
                details += ["", f"### {provider} / {case_id}: {entry['status']}"]
                if entry["status"] == "error":
                    details.append(f"- {entry.get('error_type')}: {entry.get('message', '')[:300]}")
                details += [f"- {p}" for p in entry.get("problems", [])]
                if judge.get("verdict") == "fail":
                    details += [f"- judge: {p}" for p in judge.get("problems", [])]
                elif judge.get("verdict") == "error":
                    details.append(f"- judge error: {judge.get('error', '')[:300]}")
    if details:
        lines += ["", "## Failures"] + details
    retried = []
    for provider in providers:
        for case_id, entry in summary["providers"][provider]["cases"].items():
            for number, earlier in enumerate(entry.get("earlier_attempts", []), 1):
                reasons = earlier.get("problems") or [
                    f"{earlier.get('error_type')}: {earlier.get('message', '')[:200]}"
                ]
                retried.append(
                    f"- {provider} / {case_id}, attempt {number} {earlier['status']}: "
                    + "; ".join(reasons)[:400]
                )
    if retried:
        lines += ["", "## Needed another attempt", ""] + retried
    warned = [
        f"- {provider} / {case_id}: {warning}"
        for provider in providers
        for case_id, entry in summary["providers"][provider]["cases"].items()
        for warning in entry.get("warnings", [])
    ]
    if warned:
        lines += ["", "## Warnings", ""] + warned
    # The provider table already says which providers were not configured.
    skipped = [
        f"- {provider} / {case_id}: {entry.get('reason', '')}"
        for provider in providers
        for case_id, entry in summary["providers"][provider]["cases"].items()
        if entry["status"] == "skip" and entry.get("reason") != "provider not configured"
    ]
    if skipped:
        lines += ["", "## Skipped", ""] + skipped
    if summary.get("baseline_notes") is not None:
        lines += ["", f"## Against the baseline `{summary['baseline']}`", ""]
        lines += [f"- {n}" for n in summary["baseline_notes"]] or [
            "- no change in status or output"
        ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, text=True, capture_output=True
        ).stdout.strip()
    except OSError:
        return ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, help="Run folder, outside the repository")
    parser.add_argument(
        "--providers",
        default=os.getenv("CHECK_PROVIDERS", "azure"),
        help="Comma-separated: " + ", ".join(PROVIDERS),
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="PROVIDER=MODEL",
        help="Model or deployment for a provider (repeatable)",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        type=Path,
        default=[],
        help="KEY=value file to load first (repeatable); values are never printed",
    )
    parser.add_argument(
        "--env-override",
        action="store_true",
        help="Let --env-file values replace variables already set",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--only", default="", help="Comma-separated case ids")
    parser.add_argument("--component", default="", help="Comma-separated: " + ", ".join(COMPONENTS))
    parser.add_argument("--list", action="store_true", help="List the cases and exit")
    parser.add_argument(
        "--judge",
        choices=["claude", "codex", "agy"],
        help="Judge every output with this CLI on its subscription login",
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("CHECK_JUDGE_MODEL"),
        help="Model for the judge CLI (codex: gpt-6.2-sol; claude and agy: their own default)",
    )
    parser.add_argument("--judge-timeout", type=float, default=300)
    parser.add_argument("--baseline", type=Path, help="An earlier run folder to compare with")
    parser.add_argument(
        "--reuse-schemas",
        type=Path,
        help="Use the schemas an earlier run folder generated, per provider",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="Runs of a case that fails or errors, at most; the summary shows each extra one",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Keep no provider error text in the outputs (for a run whose results are published)",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Run extraction cases even when their schema case failed its checks",
    )
    parser.add_argument(
        "--require-all", action="store_true", help="Fail when a selected provider is not configured"
    )
    parser.add_argument("--parallel", type=int, default=4, help="Providers run at the same time")
    parser.add_argument("--timeout", type=float, default=180, help="Seconds per model request")
    parser.add_argument(
        "--provider-timeout",
        type=float,
        default=900,
        help="Seconds a provider may take for all its cases; the rest are then errors",
    )
    args = parser.parse_args(argv)
    args.model_overrides = parse_model_overrides(args.model)
    return args


def check_cases(cases: list[dict]) -> list[dict]:
    """The cases with schema cases first; stop on a duplicate id or a broken dependency."""
    by_id: dict[str, dict] = {}
    for case in cases:
        if case.get("component") not in COMPONENTS:
            raise SystemExit(f"case {case.get('id')!r}: component must be one of {COMPONENTS}")
        if case["id"] in by_id:
            raise SystemExit(f"case id {case['id']!r} appears twice")
        by_id[case["id"]] = case
    for case in cases:
        if case["component"] not in SCHEMA_CONSUMERS:
            continue
        parent = by_id.get(case.get("schema_from", ""))
        if parent is None or parent["component"] != "schema_generator":
            raise SystemExit(
                f"case {case['id']!r}: schema_from {case.get('schema_from')!r} "
                "is not a schema_generator case in this file"
            )
    schemas = [c for c in cases if c["component"] == "schema_generator"]
    return schemas + [c for c in cases if c["component"] != "schema_generator"]


def select_cases(args) -> list[dict]:
    cases = check_cases(json.loads(args.cases.read_text("utf-8"))["cases"])
    only = {c for c in args.only.split(",") if c}
    components = {c for c in args.component.split(",") if c}
    unknown = only - {c["id"] for c in cases}
    if unknown:
        raise SystemExit(f"Unknown case id(s): {sorted(unknown)}")
    chosen = [
        c
        for c in cases
        if (not only or c["id"] in only) and (not components or c["component"] in components)
    ]
    # A chosen extraction case brings the schema case it depends on.
    needed = {c.get("schema_from") for c in chosen if c.get("schema_from")}
    chosen_ids = {c["id"] for c in chosen}
    return [c for c in cases if c["id"] in chosen_ids or c["id"] in needed]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = select_cases(args)
    if args.list:
        for case in cases:
            print(f"{case['id']:<24} {case['component']:<17} {case.get('title', '')}")
        return 0
    if args.out is None:
        raise SystemExit("--out is required (a folder outside the repository)")
    args.out = args.out.resolve()
    if args.out == ROOT or ROOT in args.out.parents:
        raise SystemExit("--out must be outside the repository, so that no output is committed")
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in providers if p not in PROVIDERS]
    if unknown:
        raise SystemExit(f"Unknown provider(s) {unknown}; choose from {PROVIDERS}")
    if args.judge and shutil.which(args.judge) is None:
        raise SystemExit(f"--judge {args.judge}: the CLI is not on PATH")
    if args.judge:
        check_judge_login(args.judge)

    loaded = load_env_files(args.env_file, args.env_override)
    secrets = secret_values(dict(os.environ))
    import gaik

    args.out.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    say(f"gaik {getattr(gaik, '__version__', '?')} from {Path(gaik.__file__).parent}")
    if loaded:
        say(f"loaded {len(loaded)} variable(s) from --env-file")

    results: dict[str, dict] = {}
    progress: dict[str, dict] = {}
    workers = max(1, args.parallel)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(run_provider, p, cases, args, secrets, progress): p for p in providers}
    pending, stuck = set(futures), set()
    while pending:
        done, pending = concurrent.futures.wait(
            pending, timeout=5, return_when=concurrent.futures.FIRST_COMPLETED
        )
        for future in done:
            results[futures[future]] = future.result()
        now = time.monotonic()
        for future in list(pending):
            begun = progress.get(futures[future], {}).get("_started")
            overdue = begun is not None and now - begun > args.provider_timeout
            # A provider that never started: every worker is held by one that timed out.
            blocked = begun is None and len(stuck) >= workers
            if overdue or blocked:
                pending.discard(future)
                stuck.add(future)
    for future in stuck:
        provider = futures[future]
        partial = {
            k: v
            for k, v in progress.get(provider, {"provider": provider}).items()
            if not k.startswith("_")
        }
        finished = dict(partial.get("cases", {}))
        message = f"the provider did not finish within {args.provider_timeout:.0f} s"
        for case in cases:
            finished.setdefault(
                case["id"],
                {
                    "component": case["component"],
                    "status": "error",
                    "error_type": "Timeout",
                    "message": message,
                },
            )
        results[provider] = {**partial, "cases": finished, "timed_out": True}
        say(f"[{provider}] stopped waiting: {message}")
    pool.shutdown(wait=not stuck, cancel_futures=True)

    summary = {
        "started": started,
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "gaik_version": getattr(gaik, "__version__", "?"),
        "gaik_from": str(Path(gaik.__file__).parent),
        "python": sys.version.split()[0],
        "judge": args.judge,
        "cases_file": str(args.cases),
        "case_ids": [c["id"] for c in cases],
        "providers": {p: results[p] for p in providers},
    }
    if args.baseline:
        baseline = json.loads((args.baseline / "summary.json").read_text("utf-8"))
        summary["baseline"] = str(args.baseline)
        summary["baseline_notes"] = diff_baseline(summary, baseline)
    _write_json(args.out / "summary.json", summary)
    (args.out / "summary.md").write_text(render_summary(summary), encoding="utf-8")

    statuses = [e["status"] for r in results.values() for e in r["cases"].values()]
    judged = [
        e["judge"]["verdict"]
        for r in results.values()
        for e in r["cases"].values()
        if e.get("judge")
    ]
    failed = any(s in ("fail", "error") for s in statuses) or "fail" in judged
    missing = [p for p, r in results.items() if r.get("skipped")]
    counts = {s: statuses.count(s) for s in STATUSES if statuses.count(s)}
    say(f"done: {counts}; summary in {args.out / 'summary.md'}")
    if stuck:
        # A provider's request is still hanging in its thread; do not wait for it.
        sys.stdout.flush()
        os._exit(1)
    if missing and args.require_all:
        say(f"not configured: {missing}")
        return 1
    if not any(s in ("pass", "fail") for s in statuses):
        say("nothing ran: configure at least one provider")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
