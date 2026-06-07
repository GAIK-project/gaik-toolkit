#!/usr/bin/env python3
"""Promote a validated, agent-generalised PoC into the reusable template library.

"Save" is a generalize-then-save operation, NEVER a copy:
  1. The agent rewrites the validated poc/run_poc.py into a TEMPLATE -- every
     use-case-specific literal replaced with the matching ${variable}.
  2. This script VALIDATES that candidate template and, only if all checks pass,
     saves it to templates/poc/<pattern_key>/run_poc.py.tmpl plus a manifest.

Promotion checks (all must pass):
  - genericity: no blueprint-specific token leaks into the template body outside ${...}
  - fills cleanly: safe_substitute leaves no unfilled ${...} for this blueprint
  - parses: the filled template is valid Python (ast.parse)
  - imports resolve: every `from gaik...import` matches a registry import_path
  - no duplicate: the pattern_key directory does not already exist

Usage:
    python scripts/promote_template.py \
        --blueprint ~/my-use-case/use_case.blueprint.json \
        --candidate ~/my-use-case/poc/run_poc.py.tmpl \
        [--status provisional|confirmed] [--force]

The --candidate file is the agent-generalised template (with ${variables}),
NOT the concrete run_poc.py.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.registry import get_registry
from solution_wizard.scaffolder import _build_variables, _derive_pattern_key, _determine_pattern

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "poc"


def _blueprint_specific_tokens(blueprint: Blueprint) -> list:
    """Tokens that must NOT appear literally in a generic template body."""
    tokens = set()
    tokens.add(blueprint.use_case.id)
    tos = blueprint.target_output_spec if isinstance(blueprint.target_output_spec, dict) else {}
    if tos.get("schema_name"):
        tokens.add(tos["schema_name"])
    for f in tos.get("fields", []):
        if len(f) >= 4:  # skip ultra-short field names that cause false positives
            tokens.add(f)
    # Concrete model names from the blueprint
    models = blueprint.models or {}
    for key in ("transcription_model", "extraction_model"):
        v = models.get(key)
        if v:
            tokens.add(v)
    # Language code -- a hardcoded "fi" would break any non-Finnish use case
    lang = (
        blueprint.technical_spec.get("language", "")
        if isinstance(blueprint.technical_spec, dict)
        else getattr(blueprint.technical_spec, "language", "")
    )
    if lang and len(lang) >= 2:
        tokens.add(lang)
    return [t for t in tokens if t]


def _strip_placeholders(text: str) -> str:
    """Remove ${...} placeholders so the genericity scan only sees the literal body."""
    return re.sub(r"\$\{[^}]*\}", "", text)


def _check_genericity(candidate: str, blueprint: Blueprint) -> list:
    body = _strip_placeholders(candidate)
    leaked = []
    for tok in _blueprint_specific_tokens(blueprint):
        if re.search(r"\b" + re.escape(tok) + r"\b", body):
            leaked.append(tok)
    return leaked


def _check_fills_cleanly(candidate: str, variables: dict) -> list:
    filled = string.Template(candidate).safe_substitute(variables)
    return re.findall(r"\$\{[^}]*\}", filled)


def _check_parses(candidate: str, variables: dict) -> str | None:
    filled = string.Template(candidate).safe_substitute(variables)
    try:
        ast.parse(filled)
        return None
    except SyntaxError as exc:
        return str(exc)


def _check_imports(candidate: str) -> list:
    """Return gaik imports that do not resolve to an installed module."""
    unresolved = []
    for m in re.finditer(r"from\s+(gaik[\w\.]*)\s+import", candidate):
        modpath = m.group(1)
        try:
            if importlib.util.find_spec(modpath) is None:
                unresolved.append(modpath)
        except (ImportError, ModuleNotFoundError, ValueError):
            unresolved.append(modpath)
    return unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a PoC to the template library.")
    parser.add_argument("--blueprint", required=True, help="Path to the validated blueprint")
    parser.add_argument("--candidate", required=True, help="Path to the agent-generalised template (.tmpl with ${vars})")
    parser.add_argument("--status", default="provisional", choices=["provisional", "confirmed"])
    parser.add_argument("--force", action="store_true", help="Overwrite an existing template (skip duplicate check)")
    parser.add_argument("--skip-import-check", action="store_true",
                        help="Skip gaik import resolution check (use when gaik extras are not installed)")
    args = parser.parse_args()

    bp_path = Path(args.blueprint)
    cand_path = Path(args.candidate)
    for p, label in [(bp_path, "blueprint"), (cand_path, "candidate template")]:
        if not p.exists():
            print(f"ERROR: {label} not found: {p}", file=sys.stderr)
            return 1

    blueprint = Blueprint.from_file(bp_path)
    candidate = cand_path.read_text(encoding="utf-8")
    variables = _build_variables(blueprint, _determine_pattern(blueprint))

    pattern_key = _derive_pattern_key(blueprint)
    if pattern_key == "_generic":
        print("ERROR: cannot derive a stable pattern key (no automated steps).", file=sys.stderr)
        return 1

    print(f"Pattern key: {pattern_key}")
    failures = []

    # 1. Duplicate check
    target_dir = TEMPLATES_DIR / pattern_key
    if target_dir.exists() and not args.force:
        print(f"ERROR: template already exists for this pipeline shape: {target_dir}")
        print("This pipeline is already in the library (it would have been matched as a fixed pattern).")
        return 1

    # 2. Genericity scan
    leaked = _check_genericity(candidate, blueprint)
    if leaked:
        failures.append(
            f"genericity: use-case-specific tokens leaked into the template body "
            f"(must be ${{variables}}): {leaked}"
        )

    # 3. Fills cleanly
    unfilled = _check_fills_cleanly(candidate, variables)
    if unfilled:
        failures.append(f"fills_cleanly: unfilled placeholders for this blueprint: {sorted(set(unfilled))}")

    # 4. Parses
    parse_err = _check_parses(candidate, variables)
    if parse_err:
        failures.append(f"parses: filled template is not valid Python: {parse_err}")

    # 5. Imports resolve (optional -- needs gaik installed)
    if not args.skip_import_check:
        unresolved = _check_imports(candidate)
        if unresolved:
            failures.append(f"imports: unresolved gaik imports: {unresolved}")

    if failures:
        print("\nPROMOTION REJECTED:")
        for f in failures:
            print(f"  - {f}")
        print("\nFix the candidate template (or keep this PoC as a one-off) and retry.")
        return 1

    # All checks passed -- save template + manifest
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "run_poc.py.tmpl").write_text(candidate, encoding="utf-8")

    components = [
        s.component for s in blueprint.workflow.steps
        if s.component and s.component not in ("LLMJudge", "custom", "human_review")
    ]
    manifest = {
        "pattern_key": pattern_key,
        "components": components,
        "topology_signature": [
            f"{s.component}({sorted(s.inputs)}->{sorted(s.outputs)})"
            for s in blueprint.workflow.steps
            if s.component and s.component not in ("LLMJudge", "custom", "human_review")
        ],
        "variables_used": sorted(set(re.findall(r"\$\{(\w+)\}", candidate))),
        "validated_by": [blueprint.use_case.id],
        "status": args.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (target_dir / "template.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nPROMOTED. Template saved to: {target_dir / 'run_poc.py.tmpl'}")
    print(f"Manifest: {target_dir / 'template.json'}  (status={args.status})")
    print("Next time a blueprint with this pipeline shape is scaffolded, this template is reused automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
