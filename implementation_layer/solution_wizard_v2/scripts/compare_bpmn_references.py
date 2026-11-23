#!/usr/bin/env python3
"""S2-12 (#50): structural comparison of V2-generated BPMN vs customer references.

Writes a markdown gap report. Not a pixel-perfect equality check — documents
lanes/tasks/data/events for PO review.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve()
# repo: .../solution_wizard_v2/scripts/...
SW_V2 = ROOT.parents[1]
REPO_IMPL = SW_V2.parent
SW_SRC = REPO_IMPL / "solution_wizard" / "src"
sys.path.insert(0, str(SW_SRC))
sys.path.insert(0, str(REPO_IMPL / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.bpmn_generator import generate_bpmn  # noqa: E402
from solution_wizard.v2_adapter import v2_to_v1_dict  # noqa: E402

REF_DIR = SW_V2 / "docs" / "6.7_demo" / "extracted"
OUT = SW_V2 / "docs" / "spike" / "bpmn-reference-comparison-2026-07-27.md"

# Approximate V2 reconstructions of customer use cases (SME path, not 1:1 clones).
CASES = [
    {
        "id": "audio_to_structured",
        "ref": "Use_Case_Audio-to-Structured.bpmn",
        "v2": {
            "name": "Incident reporting",
            "description": "Voice notes to structured incident report",
            "goal": "Incident report submitted",
            "steps": [
                {"id": "record", "name": "Record Voice Description", "type": "io"},
                {
                    "id": "transcribe",
                    "name": "Transcribe Audio",
                    "type": "ai",
                    "component": "WhisperTranscriber",
                },
                {
                    "id": "extract",
                    "name": "Extract Structured Data",
                    "type": "ai",
                    "component": "DataExtractor",
                },
                {"id": "review", "name": "Review Report", "type": "human_review"},
            ],
        },
    },
    {
        "id": "transcription_subtitling",
        "ref": "Use_Case_Transcription-Subtitling.bpmn",
        "v2": {
            "name": "Transcription and subtitling",
            "description": "Media to transcript and captions",
            "goal": "Transcript and subtitle files generated",
            "steps": [
                {"id": "upload", "name": "Upload Media File", "type": "io"},
                {
                    "id": "transcribe",
                    "name": "Transcribe Audio",
                    "type": "ai",
                    "component": "WhisperTranscriber",
                },
                {
                    "id": "enhance",
                    "name": "Enhance Transcript",
                    "type": "ai",
                    "component": "EnhanceTranscript",
                },
                {
                    "id": "subs",
                    "name": "Generate Subtitle Files",
                    "type": "ai",
                    "component": "Transcriber",
                },
            ],
        },
    },
]


def _attrs(xml: str, tag: str) -> list[str]:
    return re.findall(rf"<(?:bpmn:)?{tag}[^>]*name=\"([^\"]*)\"", xml)


def summarize(xml: str) -> dict:
    return {
        "lanes": _attrs(xml, "lane"),
        "tasks": _attrs(xml, "userTask") + _attrs(xml, "serviceTask") + _attrs(xml, "task"),
        "gateways": _attrs(xml, "exclusiveGateway") + _attrs(xml, "parallelGateway"),
        "starts": _attrs(xml, "startEvent"),
        "ends": _attrs(xml, "endEvent"),
        "data": _attrs(xml, "dataObjectReference"),
        "stores": _attrs(xml, "dataStoreReference"),
    }


def main() -> None:
    lines: list[str] = []
    lines.append("# BPMN reference comparison (#50) — 2026-07-27\n")
    lines.append(
        "Compares **V2 wizard generation** (adapter + `bpmn_generator`) against "
        "customer reference XML under `docs/6.7_demo/extracted/`.\n"
    )
    lines.append(
        "Scope: structural inventory (lanes, tasks, data, events). "
        "Not a claim of diagram identity — customer refs are multi-pool / "
        "domain-specific; the wizard emits a single-pool GenAI use-case diagram.\n"
    )

    for case in CASES:
        ref_path = REF_DIR / case["ref"]
        ref_xml = ref_path.read_text(encoding="utf-8", errors="replace")
        gen_xml = generate_bpmn(
            Blueprint.model_validate(v2_to_v1_dict(case["v2"], session_id="cmp"))
        )
        ref_s = summarize(ref_xml)
        gen_s = summarize(gen_xml)

        lines.append(f"## Case: `{case['id']}`\n")
        lines.append(f"- Reference: `{case['ref']}`")
        lines.append(f"- V2 use-case name: **{case['v2']['name']}**\n")
        lines.append("| Aspect | Customer reference | V2 generated |")
        lines.append("|--------|--------------------|--------------|")
        for key in ("lanes", "tasks", "gateways", "starts", "ends", "data", "stores"):
            lines.append(
                f"| {key} | {', '.join(ref_s[key][:8]) or '—'}"
                f"{'…' if len(ref_s[key]) > 8 else ''} | "
                f"{', '.join(gen_s[key][:8]) or '—'}"
                f"{'…' if len(gen_s[key]) > 8 else ''} |"
            )
        lines.append("")

    lines.append("## Known gaps (PO review)\n")
    lines.append(
        "1. **Role-specific lanes** (Observer, Safety Manager, ERP, …) vs wizard "
        "generic **Business User / GenAI / Reviewer** — by design for a configurable SME flow.\n"
        "2. **Multiple pools / collaboration** and **message flows** in references are not "
        "emitted from the V2 simplified blueprint.\n"
        "3. **Data stores / repositories** appear in references; V2 currently emphasizes "
        "in-process **data objects**.\n"
        "4. Customer diagrams include rich annotations and alternative paths; V2 generates "
        "the happy path + approval gateway from `human_review`.\n"
        "5. Exact task wording in references is domain-authored; V2 uses step names from "
        "the session blueprint (agent/UI).\n"
    )
    lines.append("## Conclusion\n")
    lines.append(
        "V2 generation is **directionally aligned** with GAIK modeling conventions "
        "(official shapes, GenAI lane, verb–object tasks, `[CODE]` prefixes, descriptive "
        "events, data objects). It is **not** a clone of the hand-built reference diagrams. "
        "Acceptable for Sprint 2 demo if PO agrees; deeper parity is Sprint 3+ (#48 topology, "
        "domain lane packs).\n"
    )

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
