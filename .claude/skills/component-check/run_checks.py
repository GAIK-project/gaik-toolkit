"""Run gaik's schema generator, extractor and vision extractor on synthetic cases, per provider.

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
COMPONENTS = ("schema_generator", "extractor", "vision_extractor")
STATUSES = ("pass", "fail", "error", "skip")

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
    # A parent record with a nested list of items.
    if not records:
        return ["no record returned"]
    record = records[0]
    if len(records) > 1 and all(not isinstance(v, list) for v in record.values()):
        # Rows came back flat, one per line item.
        items, key = records, "(flat rows)"
    else:
        problems += compare_record(expect.get("parent", {}), record, "parent")
        items, key = find_items(record, expect.get("items_key", ""))
        if items is None:
            return problems + [f"no list of items under {expect.get('items_key')!r}"]
    if key not in (expect.get("items_key"), "(flat rows)"):
        problems.append(f"items came under {key!r}, not {expect.get('items_key')!r}")
    wanted = expect.get("items", [])
    if len(items) != len(wanted):
        problems.append(f"expected {len(wanted)} item(s), got {len(items)}")
    for index, (want, got) in enumerate(zip(wanted, items)):
        problems += compare_record(want, got, f"item[{index}]")
    return problems


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def describe_requirements(requirements: Any, structure_type: str) -> dict:
    """Field names, types and enums of generated requirements, flat or nested."""

    def fields_of(spec) -> dict:
        return {
            f.field_name: {
                "type": f.field_type,
                "enum": f.enum,
                "format": f.format,
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
    return {"structure_type": structure_type, "fields": fields_of(requirements), "children": {}}


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
    if "child_container" in expect:
        container = expect["child_container"]
        children = observed["children"]
        if container not in children:
            problems.append(f"no child list {container!r} (got {', '.join(children) or 'none'})")
        else:
            problems += _check_fields(
                expect.get("child_fields", {}), children[container], container, False
            )
    return problems


# ---------------------------------------------------------------------------
# Running one provider
# ---------------------------------------------------------------------------


def _usage(usage: Any) -> dict | None:
    if usage is None:
        return None
    names = ("input_tokens", "output_tokens", "thinking_tokens", "total_tokens", "cost_usd")
    return {n: getattr(usage, n) for n in names if getattr(usage, n, None) is not None}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", "utf-8")


def _error(exc: BaseException, secrets: list[str]) -> dict:
    message = redact(str(exc), secrets)
    return {
        "error_type": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "message": message[:600],
    }


def run_provider(
    provider: str, cases: list[dict], args, secrets: list[str], progress: dict | None = None
) -> dict:
    """Run every case for one provider; return its results keyed by case id.

    ``progress`` gets the provider's results as they come, so a run that stops
    waiting for a slow provider still reports the cases it finished.
    """
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

    info = {
        "provider": provider,
        "model": config.get("model"),
        "vision_model": vision_config.get("model"),
    }
    results: dict[str, dict] = {}
    if progress is not None:
        progress[provider] = {**info, "cases": results}
    schemas: dict[str, dict] = {}
    reuse = args.reuse_schemas / provider if args.reuse_schemas else None

    for case in cases:
        case_dir = out_dir / case["id"]
        started = time.monotonic()
        entry: dict[str, Any] = {"component": case["component"], "title": case.get("title", "")}
        try:
            if case["component"] == "schema_generator":
                output = _run_schema(case, config, reuse)
                schemas[case["id"]] = output
                entry["observed"] = output["observed"]
                entry["problems"] = check_schema(case.get("expect", {}), output["observed"])
                _write_json(case_dir / "requirements.json", output["requirements_json"])
                _write_json(case_dir / "json_schema.json", output["json_schema"])
                entry["usage"] = output.get("usage")
            else:
                parent = schemas.get(case.get("schema_from", ""))
                if parent is None:
                    entry.update(status="skip", reason=f"no schema from {case.get('schema_from')}")
                    results[case["id"]] = entry
                    say(f"[{provider}] {case['id']}: skip ({entry['reason']})")
                    continue
                if parent.get("failed") and not args.keep_going:
                    entry.update(status="skip", reason=f"{case['schema_from']} failed its checks")
                    results[case["id"]] = entry
                    say(f"[{provider}] {case['id']}: skip ({entry['reason']})")
                    continue
                if case["component"] == "extractor":
                    data, usage = _run_extractor(case, config, parent)
                else:
                    data, usage = _run_vision(case, vision_config, parent)
                _write_json(case_dir / "result.json", data)
                entry["output"] = data
                entry["usage"] = usage
                entry["problems"] = check_extraction(case.get("expect", {}), data)
            entry["status"] = "fail" if entry["problems"] else "pass"
            if case["component"] == "schema_generator" and entry["problems"]:
                schemas[case["id"]]["failed"] = True
        except Exception as exc:
            entry.update(status="error", **_error(exc, secrets))
        entry["elapsed_s"] = round(time.monotonic() - started, 2)

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
        structure = raw.get("structure_type", "flat")
        usage = None
    else:
        generator = SchemaGenerator(config)
        result = generator.generate_schema_with_usage(case["requirements"])
        schema, requirements = result.schema, result.requirements
        structure = result.structure_analysis.structure_type
        usage = _usage(result.usage)
    return {
        "schema": schema,
        "requirements": requirements,
        "user_requirements": case["requirements"],
        "requirements_json": requirements.model_dump(mode="json"),
        "json_schema": schema.model_json_schema(),
        "observed": describe_requirements(requirements, structure),
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


def judge_prompt(case: dict, entry: dict) -> str:
    if case["component"] == "schema_generator":
        given = f"Task given to the schema generator:\n{case['requirements']}"
        output = entry.get("observed")
    else:
        paths = case.get("documents") or [case.get("source_text")]
        texts = "\n\n".join(f"--- {p} ---\n{_read(p)}" for p in paths if p)
        label = "Documents" if case.get("documents") else "Text the page image was rendered from"
        given = f"{label}:\n{texts}"
        output = entry.get("output")
    return (
        "You check one output of a document-extraction component against its input. "
        "All data here is synthetic. Do not use tools; answer only with JSON matching the "
        "schema: verdict pass or fail, problems as a list of concrete defects (wrong or "
        "invented value, missing or extra field, wrong type or order), notes as one sentence. "
        "Write in English.\n\n"
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
            cmd, stdin = judge_command(
                args.judge, args.judge_model, work, judge_prompt(case, entry)
            )
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
    return notes


def render_summary(summary: dict) -> str:
    providers = list(summary["providers"])
    lines = [
        f"# Component check {summary['started']}",
        "",
        f"gaik {summary['gaik_version']} from `{summary['gaik_from']}`, commit "
        f"{summary['git_commit']}{' (uncommitted changes)' if summary['git_dirty'] else ''}.",
        f"Judge: {summary['judge'] or 'none'}.",
        "",
        "| Provider | Model | Vision model | Note |",
        "| --- | --- | --- | --- |",
    ]
    for name, result in summary["providers"].items():
        note = ""
        if result.get("skipped"):
            note = "not configured: " + result["skipped"]["message"][:120]
        elif result.get("timed_out"):
            note = "stopped waiting (--provider-timeout); unfinished cases are errors"
        model, vision = result.get("model") or "-", result.get("vision_model") or "-"
        lines.append(f"| {name} | {model} | {vision} | {note} |")
    lines += ["", "| Case | " + " | ".join(providers) + " |", "| --- |" + " --- |" * len(providers)]
    for case_id in summary["case_ids"]:
        cells = []
        for provider in providers:
            entry = summary["providers"][provider]["cases"].get(case_id, {})
            cell = entry.get("status", "-")
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
    parser.add_argument("--judge-model", help="Model for the judge CLI (its default otherwise)")
    parser.add_argument("--judge-timeout", type=float, default=300)
    parser.add_argument("--baseline", type=Path, help="An earlier run folder to compare with")
    parser.add_argument(
        "--reuse-schemas",
        type=Path,
        help="Use the schemas an earlier run folder generated, per provider",
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


def select_cases(args) -> list[dict]:
    cases = json.loads(args.cases.read_text("utf-8"))["cases"]
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
    rounds = -(-len(providers) // workers)
    done, stuck = concurrent.futures.wait(futures, timeout=args.provider_timeout * rounds)
    for future in done:
        results[futures[future]] = future.result()
    for future in stuck:
        provider = futures[future]
        partial = progress.get(provider, {"provider": provider})
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
