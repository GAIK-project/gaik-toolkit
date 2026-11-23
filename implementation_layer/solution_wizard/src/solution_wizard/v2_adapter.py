"""Convert Solution Wizard V2 simplified blueprint JSON to V1 Blueprint dict."""

from __future__ import annotations

import re
from typing import Any


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "use_case"


def v2_step_type(step_type: str) -> str:
    return {
        "io": "user_task",
        "ai": "automated_task",
        "human_review": "human_review",
    }.get(step_type, "automated_task")


def _words(text: str) -> str:
    """Lower-cased words of a step name or component: camelCase and snake_case
    are split ("DataExtractor" -> "data extractor", "LLMJudge" -> "llm judge";
    a plural like "PDFs" stays whole), so a keyword can be matched at the start of
    a word instead of anywhere inside one."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]{2,})", " ", text)
    return re.sub(r"[_\-/]+", " ", text).lower()


def _mentions(blob: str, words: tuple[str, ...]) -> bool:
    """Whether any keyword starts a word in ``blob``.

    A plain substring test matched ``voice`` inside "in-voice", so a first step
    "Upload invoice PDFs" got an audio data object ("Voice Note Audio") in a BPMN
    for a PDF case; ``rag`` matched "storage", ``media`` matched "intermediate".
    Prefix matches stay ("transcrib" for transcribe/transcription).
    """
    return any(re.search(r"\b" + re.escape(w), blob) for w in words)


def _unique_art_id(base: str, used: set[str]) -> str:
    candidate = base or "artifact"
    if candidate not in used:
        used.add(candidate)
        return candidate
    n = 2
    while f"{candidate}_{n}" in used:
        n += 1
    out = f"{candidate}_{n}"
    used.add(out)
    return out


def _infer_artifact(
    step: dict[str, Any],
    *,
    is_first: bool,
    is_last: bool,
) -> tuple[str, str]:
    """Pick (artifact_id, artifact_type) for official BPMN data-object labels.

    GAIK modeling guide: data objects are *data* (Audio File, Transcript,
    Structured JSON), not copies of task names. Ids are chosen so
    ``bpmn_generator._data_object_label`` yields those human labels.
    """
    step_type = str(step.get("type") or "ai")
    blob = _words(f"{step.get('name') or ''} {step.get('component') or ''}")

    if step_type == "io" and is_first:
        if _mentions(blob, ("audio", "voice", "speech", "recording", "ään")):
            return "voice_note_audio", "audio"
        if _mentions(blob, ("pdf", "document", "docx", "file upload")):
            return "source_document", "pdf"
        if _mentions(blob, ("image", "photo", "kuva")):
            return "source_image", "image"
        if _mentions(blob, ("video", "media")):
            return "source_media", "video"
        return "user_input", "text"

    if _mentions(blob, ("transcrib", "whisper", "speech to text", "stt")):
        return "raw_transcript", "transcript"
    if _mentions(blob, ("enhance_transcript", "enhancetranscript", "enhance transcript")):
        return "enhanced_transcript", "transcript"
    if _mentions(blob, ("schema", "ssg")):
        return "extraction_schema", "schema"
    if _mentions(blob, ("extract", "structured", "field")):
        return "structured_json", "structured_json"
    if _mentions(blob, ("subtitle", "caption")):
        return "subtitle_file", "subtitle"
    if _mentions(blob, ("rag", "pgvector", "search", "index")):
        return "search_result", "structured_json"
    if _mentions(blob, ("validat", "judge", "qa")):
        return "validation_report", "validation_report"
    if step_type == "human_review":
        return (
            ("reviewed_output", "structured_json")
            if is_last
            else ("draft_report", "structured_json")
        )
    if is_last:
        return "final_output", "structured_json"
    if step_type == "ai":
        return "structured_json", "structured_json"
    return "intermediate_text", "text"


def _synthesize_artifacts_and_links(
    steps: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create V1 artifacts + wire step inputs/outputs so BPMN gets data objects.

    V2 blueprints only have ordered steps. We invent one outgoing artifact per
    step using official-style data names (Audio File, Transcript, …) so the
    generator can emit guide-compliant data objects and associations.
    """
    artifacts: dict[str, Any] = {}
    workflow_steps: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    prev_art: str | None = None
    prev_id: str | None = None

    for i, step in enumerate(steps):
        sid = str(step.get("id") or f"step_{i + 1}")
        step_type = str(step.get("type") or "ai")
        v1_type = v2_step_type(step_type)
        name = str(step.get("name") or sid)
        is_first = i == 0
        is_last = i == len(steps) - 1
        art_base, art_type = _infer_artifact(step, is_first=is_first, is_last=is_last)
        art_id = _unique_art_id(art_base, used_ids)

        if step_type == "io" and is_first:
            artifacts[art_id] = {
                "type": art_type,
                "source": "user_upload",
                "optional": False,
            }
        else:
            artifacts[art_id] = {
                "type": art_type,
                "source": "generated",
                "optional": False,
                "produced_by": sid,
                "final_output": bool(is_last),
            }

        ws: dict[str, Any] = {
            "id": sid,
            "name": name,
            "type": v1_type,
            "inputs": [prev_art] if prev_art else [],
            "outputs": [art_id],
            "depends_on": [prev_id] if prev_id else [],
            "parameters": {},
        }
        if step.get("component"):
            ws["component"] = step["component"]
        # V2 descriptions live on the V2 step; V1 WorkflowStep has no description field.
        if step.get("description"):
            ws["parameters"] = {**ws["parameters"], "description": step["description"]}
        workflow_steps.append(ws)
        prev_art = art_id
        prev_id = sid

    return artifacts, workflow_steps


def _normalize_integration_targets(v2: dict[str, Any]) -> list[str]:
    """V2 → V1 ``technical_spec.integration_targets`` (BPMN data stores + send tasks).

    Accepts ``integration_targets`` (preferred) or ``data_stores`` as a UI alias.
    Empty / missing → no stores (same as V1 ``[]``).
    """
    raw = v2.get("integration_targets")
    if raw is None:
        raw = v2.get("data_stores")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def v2_to_v1_dict(v2: dict[str, Any], *, session_id: str = "session") -> dict[str, Any]:
    """Build a minimal valid V1 blueprint dict from V2 UI blueprint content."""
    name = (v2.get("name") or "Session").strip() or "Session"
    slug = _slugify(name)
    steps = list(v2.get("steps") or [])
    has_human_review = any(s.get("type") == "human_review" for s in steps)
    integration_targets = _normalize_integration_targets(v2)

    artifacts, workflow_steps = _synthesize_artifacts_and_links(steps)

    building_blocks = sorted(
        {
            str(s["component"])
            for s in steps
            if s.get("component") and str(s.get("type") or "") == "ai"
        }
    )

    # Prefer role-like labels from step context when available.
    intended_users = ["Business User"]
    reviewers = ["Reviewer"] if has_human_review else []

    return {
        "blueprint_version": "1.0",
        "metadata": {
            "blueprint_id": f"{slug}_{session_id}",
            "status": "draft",
        },
        "use_case": {
            "id": slug,
            "name": name,
            "description": str(v2.get("description") or ""),
            "domain": "general",
            "knowledge_processes": ["knowledge_capture"],
        },
        "business_spec": {
            "intended_users": intended_users,
            "reviewers": reviewers,
        },
        "technical_spec": {
            "input_types": ["text"],
            "output_types": ["structured_json"],
            "language": "fi",
            "human_review_required": has_human_review,
            "integration_targets": integration_targets,
        },
        "target_output_spec": {
            "schema_name": "Output",
            "fields": ["result"],
            "required_fields": ["result"],
        },
        "components": {
            "selected_modules": [],
            "selected_building_blocks": building_blocks,
            "custom_components": [],
        },
        "artifacts": artifacts,
        "workflow": {"steps": workflow_steps},
        "business_process": {
            "participants": [
                {
                    "id": "business_user",
                    "name": "Business User",
                    "kind": "human_role",
                    "default_lane_for": ["user_task"],
                },
                *(
                    [
                        {
                            "id": "reviewer",
                            "name": "Reviewer",
                            "kind": "human_role",
                            "default_lane_for": ["human_review"],
                        }
                    ]
                    if has_human_review
                    else []
                ),
                {
                    "id": "genai",
                    "name": "GenAI",
                    "kind": "system",
                    "default_lane_for": [],
                },
            ],
        },
    }
