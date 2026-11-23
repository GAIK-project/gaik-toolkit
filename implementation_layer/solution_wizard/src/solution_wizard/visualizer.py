"""Mermaid generator -- produces flowchart TD from a Blueprint.

Uses the GAIK palette (spec §15.1):
  inputs      #dbeafe  (blue)
  processing  #f5f3ff  (purple)
  intermediate/decision  #fefce8  (yellow)
  outputs     #dcfce7  (green)
"""

from __future__ import annotations

import hashlib
import re
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


_SAFE_ID = re.compile(r"[^A-Za-z0-9_]")
# Words Mermaid's flowchart grammar reads as keywords when used as a node id.
_RESERVED_IDS = {"end", "graph", "flowchart", "subgraph", "style", "classdef", "class", "click"}


def _node_id(step_id: str) -> str:
    """Convert a step id to a distinct Mermaid node id that cannot change the syntax.

    An id made only of ``[A-Za-z0-9_]`` that is not a Mermaid keyword is used as it
    is. Any other id has every other character replaced by ``_`` and a short hash
    of the original appended, so ``end``, ``step end`` and ``step_end`` stay three
    nodes instead of merging into one.
    """
    if step_id and not _SAFE_ID.search(step_id) and step_id.lower() not in _RESERVED_IDS:
        return step_id
    digest = hashlib.sha1(step_id.encode("utf-8")).hexdigest()[:6]
    return f"{_SAFE_ID.sub('_', step_id) or 'step'}_{digest}"


# Mermaid reads entity codes (#name;) inside quoted labels. "#" itself is left
# alone: it only starts an entity when the text already looks like one.
_LABEL_ESCAPES = {
    "&": "#amp;",
    '"': "#quot;",
    "<": "#lt;",
    ">": "#gt;",
    "[": "#lsqb;",
    "]": "#rsqb;",
    "`": "#96;",
}


def _node_label(label: str) -> str:
    """Escape a step name for safe use inside Mermaid node label quotes.

    A double quote would end the label, brackets interfere with node-shape
    syntax, ``<``/``>``/``&`` would reach a renderer that allows HTML labels as
    markup, and a backtick starts a Markdown string. Line breaks would end the
    node definition, so they become spaces.
    """
    label = " ".join(label.splitlines())
    return "".join(_LABEL_ESCAPES.get(ch, ch) for ch in label)


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
