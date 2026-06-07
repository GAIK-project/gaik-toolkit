"""Mermaid generator -- produces flowchart TD from a Blueprint.

Uses the GAIK palette (spec §15.1):
  inputs      #dbeafe  (blue)
  processing  #f5f3ff  (purple)
  intermediate/decision  #fefce8  (yellow)
  outputs     #dcfce7  (green)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .blueprint import Blueprint


# GAIK palette
COLOUR = {
    "user_task": "#dbeafe",  # blue  -- user provides input
    "automated_task": "#f5f3ff",  # purple -- GAIK component processes
    "human_review": "#fefce8",  # yellow -- human-in-the-loop
    "decision": "#fefce8",  # yellow -- gateway
    "output": "#dcfce7",  # green  -- final output
}


def _node_id(step_id: str) -> str:
    """Convert step id to a safe Mermaid node id."""
    return step_id.replace("-", "_").replace(" ", "_")


def _node_label(label: str) -> str:
    """Escape a step name for safe use inside Mermaid node label quotes.

    Mermaid uses HTML entity syntax inside quoted labels. The characters most
    likely to break a diagram are double-quote (terminates the label string)
    and brackets (interfere with node-shape syntax).
    """
    return label.replace('"', "#quot;").replace("[", "#lsqb;").replace("]", "#rsqb;")


def generate_mermaid(blueprint: Blueprint) -> str:
    steps = blueprint.workflow.steps
    if not steps:
        return "flowchart TD\n    empty[No workflow steps defined]"

    final_artifact_ids = {art_id for art_id, art in blueprint.artifacts.items() if art.final_output}

    lines: List[str] = ["flowchart TD"]
    style_lines: List[str] = []

    for step in steps:
        nid = _node_id(step.id)
        label = _node_label(step.name)

        if step.type == "decision":
            node_def = f'    {nid}{{"{label}"}}'
        else:
            node_def = f'    {nid}["{label}"]'

        lines.append(node_def)

        # Colour
        colour = COLOUR.get(step.type, COLOUR["automated_task"])
        # If this step produces a final output, colour it green
        if any(out in final_artifact_ids for out in step.outputs):
            colour = COLOUR["output"]
        style_lines.append(f"    style {nid} fill:{colour}")

    # Edges from depends_on
    for step in steps:
        nid = _node_id(step.id)
        for dep in step.depends_on:
            dep_nid = _node_id(dep)
            lines.append(f"    {dep_nid} --> {nid}")

    # If no depends_on edges, fall back to sequential order
    has_edges = any(s.depends_on for s in steps)
    if not has_edges and len(steps) > 1:
        for i in range(len(steps) - 1):
            a = _node_id(steps[i].id)
            b = _node_id(steps[i + 1].id)
            lines.append(f"    {a} --> {b}")

    lines.append("")
    lines.extend(style_lines)

    return "\n".join(lines)


def write_mermaid(blueprint: Blueprint, output_dir: str | Path) -> Path:
    """Generate Mermaid and write workflow.mmd to output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mmd_path = output_dir / "workflow.mmd"
    mmd_content = generate_mermaid(blueprint)
    mmd_path.write_text(mmd_content, encoding="utf-8")
    return mmd_path
