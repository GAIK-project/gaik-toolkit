#!/usr/bin/env python3
"""GAIK Solution Configuration Wizard -- CLI entry point.

In normal use the wizard runs conversationally inside Claude Code or
Claude Desktop (via SKILL.md). This script is the standalone CLI
equivalent: it validates a given blueprint and generates the Mermaid
diagram, placing outputs in the user-specified directory.

Usage:
    # Interactive: prompts for output directory
    python run_wizard.py

    # Non-interactive: validate + generate from an existing blueprint
    python run_wizard.py --blueprint path/to/blueprint.json --output-dir ~/my-use-case

    # Re-export JSON Schema from Pydantic models
    python run_wizard.py --export-schema
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import generate_bpmn
from solution_wizard.registry import get_registry
from solution_wizard.validator import validate
from solution_wizard.visualizer import write_mermaid

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _prompt_output_dir() -> Path:
    print("\nGAIK Solution Configuration Wizard -- V1")
    print("=" * 50)
    while True:
        raw = input(
            "\nWhere would you like to save the generated files?\n"
            "(Enter a folder path, e.g. ~/projects/my-use-case): "
        ).strip()
        if not raw:
            print("Output directory is required.")
            continue
        output_dir = Path(raw).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {output_dir}")
        return output_dir


def _validate_and_generate(blueprint_path: Path, output_dir: Path) -> int:
    try:
        blueprint = Blueprint.from_file(blueprint_path)
    except Exception as exc:
        print(f"ERROR: Failed to load blueprint: {exc}", file=sys.stderr)
        return 1

    result = validate(blueprint)
    print(result.summary())

    if not result.ok:
        print("\nBlueprint validation failed. Fix errors before generating outputs.")
        return 1

    # Generate both visual views. The BPMN is the visual blueprint, derived
    # from the JSON and linked by visualizations.bpmn_mapping (generate_bpmn
    # writes the map into the blueprint), so we render BEFORE saving the JSON
    # so the mapping is persisted alongside the blueprint.
    output_dir.mkdir(parents=True, exist_ok=True)
    mmd_path = output_dir / "workflow.mmd"
    write_mermaid(blueprint, output_dir)
    bpmn_path = output_dir / "workflow.bpmn"
    bpmn_path.write_text(generate_bpmn(blueprint), encoding="utf-8")

    # Save blueprint to output dir (now including visualizations.bpmn_mapping)
    out_blueprint = output_dir / "use_case.blueprint.json"
    blueprint.package.output_dir = str(output_dir)
    blueprint.to_file(out_blueprint)
    print(f"\nBlueprint saved to:  {out_blueprint}")
    print(f"Mermaid diagram:     {mmd_path}")
    print(f"BPMN diagram:        {bpmn_path}")

    print("\nNext steps:")
    print("  - Review the Mermaid diagram in workflow.mmd (quick flow view)")
    print("  - Open the BPMN visual blueprint workflow.bpmn in bpmn-js / Camunda / draw.io")
    print(f"  - Scaffold a runnable PoC: python scripts/scaffold_poc.py --blueprint {out_blueprint}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GAIK Solution Configuration Wizard CLI"
    )
    parser.add_argument(
        "--blueprint", help="Path to an existing use_case.blueprint.json to validate + render"
    )
    parser.add_argument(
        "--output-dir", help="Directory to save outputs (skips interactive prompt)"
    )
    parser.add_argument(
        "--export-schema",
        action="store_true",
        help="Re-export JSON Schema from Pydantic models to schemas/",
    )
    parser.add_argument(
        "--show-registry",
        action="store_true",
        help="Print a compact summary of all registry components (for component selection)",
    )
    args = parser.parse_args()

    if args.export_schema:
        schema_path = SCHEMAS_DIR / "use_case_blueprint.schema.json"
        Blueprint.export_json_schema(schema_path)
        print(f"JSON Schema exported to: {schema_path}")
        return 0

    if args.show_registry:
        print(get_registry().as_llm_context())
        return 0

    if args.blueprint:
        blueprint_path = Path(args.blueprint)
        if args.output_dir:
            output_dir = Path(args.output_dir).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = blueprint_path.parent
        return _validate_and_generate(blueprint_path, output_dir)

    # Interactive mode
    output_dir = _prompt_output_dir()
    print(
        "\nTo configure a use case, describe it to the wizard in Claude Code or "
        "Claude Desktop using the /solution-wizard skill.\n"
        "Then run this script to validate and generate outputs:\n\n"
        f"  python run_wizard.py --blueprint {output_dir}/use_case.blueprint.json "
        f"--output-dir {output_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
