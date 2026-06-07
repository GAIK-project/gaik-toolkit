#!/usr/bin/env python3
"""Scaffold a minimal runnable PoC from a validated blueprint.

Validates the blueprint first, then generates the poc/ folder in the
blueprint's output directory (or a directory you specify).

Usage:
    python scaffold_poc.py --blueprint ~/my-use-case/use_case.blueprint.json
    python scaffold_poc.py --blueprint ... --output-dir ~/my-use-case
    python scaffold_poc.py --blueprint ... --synthetic        # generate sample input
    python scaffold_poc.py --blueprint ... --skip-validation  # scaffold despite errors
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc, validate_generated_python
from solution_wizard.validator import validate

# The root of the GAIK repo -- outputs must never go inside here.
_WIZARD_ROOT = Path(__file__).parent.parent.resolve()
_REPO_ROOT = _WIZARD_ROOT.parent.parent.resolve()


def _check_output_dir(output_dir: Path) -> None:
    """Refuse to write inside the GAIK repo (implementation_layer/ or above)."""
    try:
        output_dir.resolve().relative_to(_REPO_ROOT)
        print(
            f"ERROR: output-dir '{output_dir}' is inside the GAIK repository "
            f"({_REPO_ROOT}).\n"
            "All wizard outputs must go outside the repo. "
            "Choose a directory under your home folder or project root.",
            file=sys.stderr,
        )
        sys.exit(1)
    except ValueError:
        pass  # Not inside repo -- OK


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a PoC from a GAIK blueprint.")
    parser.add_argument("--blueprint", required=True, help="Path to use_case.blueprint.json")
    parser.add_argument(
        "--output-dir",
        help="Root directory for PoC output (defaults to blueprint.package.output_dir)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate synthetic input data in sample_input/ where possible",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip blueprint validation (scaffold anyway)",
    )
    args = parser.parse_args()

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.exists():
        print(f"ERROR: Blueprint not found: {blueprint_path}", file=sys.stderr)
        return 1

    try:
        blueprint = Blueprint.from_file(blueprint_path)
    except Exception as exc:
        print(f"ERROR: Failed to load blueprint: {exc}", file=sys.stderr)
        return 1

    if not args.skip_validation:
        result = validate(blueprint)
        if not result.ok:
            print(result.summary(), file=sys.stderr)
            print(
                "\nBlueprint has validation errors. Fix them or use --skip-validation.",
                file=sys.stderr,
            )
            return 1
        for w in result.warnings:
            print(f"WARNING {w}")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    elif blueprint.package.output_dir:
        output_dir = Path(blueprint.package.output_dir).expanduser().resolve()
    else:
        output_dir = blueprint_path.parent.resolve()

    _check_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scaffolding PoC into: {output_dir / 'poc'}")
    result_info = scaffold_poc(blueprint, output_dir, synthetic=args.synthetic)

    poc_dir = result_info["poc_dir"]
    pattern = result_info["pattern"]
    template_wired = result_info["template_wired"]
    pattern_key = result_info["pattern_key"]
    template_save_path = result_info["template_save_path"]

    print(f"\nPattern detected: {pattern}")
    print(f"Pipeline pattern key: {pattern_key}")
    print(f"Generated {len(result_info['files'])} file(s) in {poc_dir}")

    # Validate generated Python
    parse_err = validate_generated_python(poc_dir)
    if parse_err:
        print(f"WARNING: run_poc.py has a syntax issue: {parse_err}", file=sys.stderr)
    else:
        print("run_poc.py: syntax OK")

    if not template_wired:
        print(
            "\nNOTE: Custom/hybrid pipeline detected. run_poc.py is a per-step skeleton"
            "\nwith reference call patterns -- the wizard agent fills the wiring."
            f"\n\nIf this pipeline is validated and you choose to promote it to a reusable"
            f"\ntemplate, it would be saved to:\n  {template_save_path}"
        )

    # Print handoff message
    print(f"""
Your PoC has been generated at: {poc_dir}

To run it:
  1. Install dependencies:
         pip install -r {poc_dir / 'requirements.txt'}
  2. Set up your environment:
         cp {poc_dir / '.env.example'} {poc_dir / '.env'}
         -- then open .env and fill in your API key
  3. Add a sample input file:
         See {poc_dir / 'README.md'} for the expected input format
  4. Run the pipeline:
         python {poc_dir / 'run_poc.py'}
  5. Inspect the output:
         Check {poc_dir / 'output'} for the generated result

When you are ready, paste the output here or describe what you see.
The wizard will help you interpret the result and refine if needed (Gate 3).
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
