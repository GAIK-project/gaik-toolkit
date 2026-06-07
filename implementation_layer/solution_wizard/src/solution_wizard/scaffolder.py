"""Scaffolder -- deterministic PoC generation from a validated blueprint.

Entry point: scaffold_poc(blueprint, output_dir, synthetic=False)

Generates the complete poc/ folder described in spec §16 into
<output_dir>/poc/.  Deterministic: no API calls, no LLM involvement.

The two-layer split (spec §3.6):
  Scaffolder (this module) handles: folder tree, requirements.txt,
  .env.example, config.yaml, schema files, eval script, and run_poc.py for
  module-based common patterns (audio_to_structured, document_to_structured, rag).

  The agent (SKILL.md) handles: README prose, extraction_requirements.md
  content, and run_poc.py wiring for custom/composed pipelines.
"""

from __future__ import annotations

import ast
import json
import string
from pathlib import Path
from typing import Any, Dict, Optional

from .blueprint import Blueprint
from .registry import get_registry
from .schema_designer import write_extraction_requirements, write_schema_files
from .selector import module_for_pattern

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "poc"

# ---------------------------------------------------------------------------
# Eval framework bodies injected into run_basic_eval.py
# ---------------------------------------------------------------------------

_EVAL_BODIES: Dict[str, str] = {
    "extraction_eval": '''\
    total_exact = total_semantic = total_present = 0
    n = 0
    for out_file in output_files:
        gt_file = ground_truth_dir / out_file.name
        if not gt_file.exists():
            continue
        prediction = json.loads(out_file.read_text())
        ground_truth = json.loads(gt_file.read_text())
        for key, expected in ground_truth.items():
            predicted = prediction.get(key, "")
            exact = str(predicted).strip().lower() == str(expected).strip().lower()
            present = bool(str(predicted).strip())
            total_exact += int(exact)
            total_present += int(present)
            n += 1
        total_semantic += total_exact  # placeholder; use extraction_eval for full metrics
    if n:
        print(f"\\nField exact-match rate: {total_exact}/{n} ({100*total_exact/n:.1f}%)")
        print(f"Field completeness:     {total_present}/{n} ({100*total_present/n:.1f}%)")
    else:
        print("No matched output/ground-truth pairs found.")
    print("\\nFor full metrics (precision/recall/F1/semantic) run:")
    print("  implementation_layer/eval_methods/extraction_eval/evaluate.py")''',

    "RAG_eval": '''\
    print("For full RAG retrieval metrics (token recall, MRR, rank-weighted coverage) run:")
    print("  implementation_layer/eval_methods/RAG_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")''',

    "transcription_eval": '''\
    print("For full transcription metrics (WER/CER) run:")
    print("  implementation_layer/eval_methods/transcription_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")''',

    "report_writing_eval": '''\
    print("For full report quality scoring (LLM-as-judge) run:")
    print("  implementation_layer/eval_methods/report_writing_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")''',

    "translation_eval": '''\
    print("For full translation metrics (BLEU/chrF/TER) run:")
    print("  implementation_layer/eval_methods/translation_eval/")
    for out_file in output_files:
        print(f"  Output: {out_file.name}")''',
}

_DEFAULT_EVAL_BODY = '''\
    print("No specific evaluation framework configured.")
    print("Output files:")
    for f in output_files:
        print(f"  {f}")'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fill(template_text: str, variables: Dict[str, Any]) -> str:
    """Fill a template using string.Template safe_substitute."""
    return string.Template(template_text).safe_substitute(variables)


def _read_template(subdir: str, filename: str) -> Optional[str]:
    path = TEMPLATES_DIR / subdir / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _topo_order(steps: List) -> List:
    """Return steps sorted in topological order from the depends_on graph.

    Two blueprints with the same dependency graph but different step-list
    ordering will produce the same topological sequence, making the pattern
    key stable regardless of authoring order.
    """
    from collections import deque

    step_by_id = {s.id: s for s in steps}
    dependents: Dict[str, List[str]] = {s.id: [] for s in steps}
    in_degree: Dict[str, int] = {s.id: 0 for s in steps}

    for s in steps:
        for dep in (s.depends_on or []):
            if dep in dependents:
                dependents[dep].append(s.id)
                in_degree[s.id] = in_degree.get(s.id, 0) + 1

    # Kahn's algorithm: start from nodes with no dependencies
    queue: deque = deque(s.id for s in steps if not (s.depends_on or []))
    ordered: List = []
    while queue:
        nid = queue.popleft()
        if nid in step_by_id:
            ordered.append(step_by_id[nid])
        for child in dependents.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Append any remaining (cycles / disconnected nodes) in original list order
    seen = {s.id for s in ordered}
    ordered += [s for s in steps if s.id not in seen]
    return ordered


def _derive_pattern_key(blueprint: Blueprint) -> str:
    """Derive a stable, topology-aware key for a blueprint's pipeline shape.

    The key is computed from a **canonically sorted** set of edge descriptors
    (component + inputs + outputs + dependencies), not from traversal order.
    This means two blueprints with the same dependency graph but different
    step-list orderings produce the same key.
    LLMJudge and human_review are excluded (LLMJudge is injected separately).

    Returns a directory-safe key like 'hybrid_transcriber_multimodalparser_extractor_1a2b3c4d'.
    """
    import hashlib

    edge_parts = []
    name_parts = []
    for step in blueprint.workflow.steps:
        comp = step.component or ""
        if comp in ("LLMJudge", "custom", "human_review", ""):
            continue
        if step.type == "human_review":
            continue
        # Canonical edge: component + sorted inputs + sorted outputs + sorted deps
        edge_parts.append(
            f"{comp}(in={sorted(step.inputs)},out={sorted(step.outputs)},deps={sorted(step.depends_on or [])})"
        )
        name_parts.append(comp.lower())

    if not edge_parts:
        return "_generic"

    # Sort edges canonically so list order does not affect the key
    signature = "|".join(sorted(edge_parts))
    short_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:8]
    # Human-readable prefix from sorted component names (up to 4)
    prefix = "_".join(sorted(set(name_parts))[:4])
    prefix = "".join(c if c.isalnum() or c == "_" else "_" for c in prefix)
    return f"hybrid_{prefix}_{short_hash}"


def _module_covers_all_blocks(module_id: str, building_blocks: set) -> bool:
    """Return True if all selected building blocks are covered by the given module.

    LLMJudge is excluded — it is injected separately via ${llm_judge_section}.

    A building block is "covered" if:
      (a) it appears directly in the module's uses_components, OR
      (b) it is itself a compound component whose sub-components (uses_components)
          are all within the module's uses_components — e.g. "Extractor" wraps
          [SchemaGenerator, DataExtractor], both of which are inside
          AudioToStructuredData.uses_components, so Extractor is covered.

    If any extra block is genuinely new (e.g. DocumentClassifier), fall through
    to dynamic/generic so those extra steps are not silently dropped.
    """
    registry = get_registry()
    extra_blocks = building_blocks - {"LLMJudge"}
    if not extra_blocks:
        return True

    entry = registry.lookup_by_id(module_id)
    if not entry:
        return False
    module_components = set(entry.get("uses_components", []))

    for block in extra_blocks:
        if block in module_components:
            continue  # directly covered
        # Transitive: if the block is a compound, check if its sub-components are covered
        block_entry = registry.lookup_by_name(block) or registry.lookup_by_id(block)
        if block_entry:
            sub = set(block_entry.get("uses_components", []))
            if sub and sub.issubset(module_components):
                continue  # transitively covered
        return False  # genuinely extra

    return True


def _determine_pattern(blueprint: Blueprint) -> str:
    """Return the PoC pattern name (= template subdir) to use.

    Discovery order:
      1. Fixed module patterns (audio/document/rag) -- only when exactly one
         module is selected AND its building blocks are all covered. If multiple
         modules are selected the fixed template for the first match would
         silently drop all other modules' logic, so we fall through instead.
      2. Dynamic template lookup -- if a promoted template exists for this
         blueprint's pipeline shape, reuse it deterministically.
      3. _generic fallback -- agent authors the wiring.
    """
    modules = [m.id if hasattr(m, "id") else m.get("id", "") for m in blueprint.components.selected_modules]
    building_blocks = set(blueprint.components.selected_building_blocks)

    # Only use a fixed module template when exactly one module is selected.
    # Multiple selected modules mean a genuine hybrid -- no single fixed template
    # covers the full pipeline, so fall through to dynamic/generic.
    if len(modules) == 1:
        if "audio_to_structured_data" in modules and _module_covers_all_blocks("audio_to_structured_data", building_blocks):
            return "audio_to_structured"
        if "documents_to_structured_data" in modules and _module_covers_all_blocks("documents_to_structured_data", building_blocks):
            return "document_to_structured"
        if "rag_workflow" in modules and _module_covers_all_blocks("rag_workflow", building_blocks):
            return "rag"

    # Dynamic library lookup by topology-aware key
    pattern_key = _derive_pattern_key(blueprint)
    if pattern_key != "_generic":
        candidate = TEMPLATES_DIR / pattern_key / "run_poc.py.tmpl"
        if candidate.exists():
            return pattern_key

    return "_generic"


def _build_generic_pipeline_skeleton(blueprint: Blueprint) -> str:
    """Build a per-step wiring skeleton for the _generic template.

    Each automated_task step becomes a labelled block carrying the component's
    verified call pattern (from the reference cards) and the blueprint-derived
    artifact variable names -- which already chain correctly. The agent fills
    one call per block rather than inventing the whole structure.
    """
    from .registry import get_reference_cards
    cards = get_reference_cards()
    lines: List[str] = []

    for step in blueprint.workflow.steps:
        comp = step.component or ""
        inputs = ", ".join(step.inputs) if step.inputs else "(none)"
        outputs = ", ".join(step.outputs) if step.outputs else "(none)"

        if step.type == "user_task":
            lines.append(f"    # ----- Step: {step.id}  (user input) -----")
            lines.append(f"    # produces: {outputs}  (loaded from sample_input/, see loaders above)")
            lines.append("")
            continue

        if step.type == "human_review" or comp == "human_review":
            lines.append(f"    # ----- Step: {step.id}  (human review -- NOT executed in PoC) -----")
            lines.append(f"    # In production a reviewer approves: {outputs}")
            lines.append("")
            continue

        if comp == "LLMJudge":
            # Handled by the dedicated validation block below; skip here.
            continue

        lines.append(f"    # ----- Step: {step.id}  ({comp}) -----")
        lines.append(f"    # inputs: {inputs}  ->  outputs: {outputs}")
        card = cards.get(comp)
        if card:
            lines.append("    # Reference call pattern:")
            for snippet_key in ("import", "construct", "call"):
                for snip_line in card[snippet_key].split("\n"):
                    lines.append(f"    #   {snip_line}")
            lines.append(f"    #   returns: {card['returns']}")
        else:
            lines.append(f"    # (no reference card for {comp} -- read its README/example_script_path)")
        # Pre-declare each output variable so later steps reference real names
        for out in step.outputs:
            lines.append(f"    {out} = None  # TODO: wire {comp}; assign its result to '{out}'")
        lines.append("")

    return "\n".join(lines)


def _build_input_loaders(blueprint: Blueprint) -> str:
    """Build input-loading code for each user_upload artifact, by type."""
    from .blueprint import ArtifactSource

    audio_exts = '(".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4")'
    doc_exts = '(".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".txt", ".md")'

    lines: List[str] = []
    for art_id, art in blueprint.artifacts.items():
        if art.source != ArtifactSource.USER_UPLOAD:
            continue
        atype = art.type.lower()
        if atype in ("audio", "video"):
            exts = audio_exts
        elif atype in ("pdf", "docx", "document", "image", "text"):
            exts = doc_exts
        else:
            exts = doc_exts
        lines.append(f"    # Load user-upload artifact: {art_id} (type={art.type})")
        lines.append(f"    {art_id}_path = _find_input(sample_dir, {exts})")
        lines.append(f"    print(f'{art_id}: {{{art_id}_path}}')")
        lines.append("")
    if not lines:
        lines.append("    # (no user-upload inputs declared)")
    return "\n".join(lines)


def _build_generic_judge_section(has_llm_judge: bool) -> str:
    """LLMJudge block for the _generic template.

    Unlike the module templates (which read result.transcription / result.parsed_documents),
    the generic block uses the CONTRACT variables the agent must assign:
      - extracted_fields : dict | list[dict]  (the structured output)
      - source_text      : str                (grounding text for hallucination check)
    """
    if not has_llm_judge:
        return "    # LLMJudge is not in this blueprint's pipeline."

    return '''\
    # -- LLMJudge hallucination detection (from blueprint) --
    # Contract: by this point your wiring MUST have assigned:
    #   extracted_fields  (dict or list[dict])  -- the structured output
    #   source_text       (str)                 -- the grounding text to validate against
    if extracted_fields is None or not source_text:
        print("LLMJudge skipped: pipeline not fully wired "
              "(need both 'extracted_fields' and 'source_text').")
    else:
        print("\\nRunning LLMJudge hallucination detection...")
        try:
            from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
            judge = _LLMJudge(model_provider="openai", use_azure=use_azure)
            extracted_for_judge = extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(source_text=source_text, extracted=extracted_for_judge)
            if report.flags:
                print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
                for flag in report.flags:
                    print(f"  field={flag.field}  value={flag.value}  reason={flag.reason}")
            else:
                print("Hallucination check passed -- all fields are grounded in the source.")
            validation_result = {
                "hallucination_flags": [
                    {"field": f.field, "value": f.value, "severity": str(f.severity), "reason": f.reason}
                    for f in report.flags
                ],
                "passed": len(report.flags) == 0,
            }
            (output_dir / "validation.json").write_text(
                json.dumps(validation_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except ImportError:
            print("LLMJudge skipped: gaik[llm-judge] not installed.")
        except Exception as _judge_exc:
            print(f"LLMJudge warning: {_judge_exc}")'''


def _wants_pdf(blueprint: Blueprint) -> bool:
    """True when the blueprint requests a PDF report of the PoC output.

    Triggered by 'pdf' (or 'report') appearing in technical_spec.output_types.
    """
    tspec = blueprint.technical_spec if isinstance(blueprint.technical_spec, dict) else {}
    out = tspec.get("output_types") or []
    if isinstance(out, str):
        out = [out]
    return any(str(o).lower() in ("pdf", "report") for o in out)


def _build_pdf_report_section(blueprint: Blueprint, schema_name: str) -> str:
    """Code injected after the JSON output write -- renders a formatted PDF.

    Empty string when PDF output is not requested. The block reads the
    template-set `_pdf_source` variable (each run_poc.py template assigns it from
    its own result variable just before this block) and writes `result_report.pdf`
    next to the JSON output."""
    if not _wants_pdf(blueprint):
        return ""
    title = blueprint.use_case.name.replace('"', "'")
    return (
        "    # ----- PDF report (technical_spec.output_types includes 'pdf') -----\n"
        "    if _pdf_source is not None:\n"
        "        try:\n"
        "            from pdf_report import write_pdf_report\n"
        "            _pdf_path = output_dir / \"result_report.pdf\"\n"
        f"            write_pdf_report(_pdf_source, _pdf_path, title=\"{title}\", subtitle=\"{schema_name}\",\n"
        f"                             metadata={{\"Schema\": \"{schema_name}\"}})\n"
        "            print(f\"PDF report written to: {_pdf_path}\")\n"
        "        except Exception as _pdf_exc:  # noqa: BLE001\n"
        "            print(f\"WARNING: PDF report generation failed: {_pdf_exc}\")\n"
    )


def _build_variables(blueprint: Blueprint, pattern: str) -> Dict[str, Any]:
    """Build the substitution variables dict from the blueprint."""
    bc = blueprint
    models = bc.models or {}
    provider = models.get("provider", "azure_openai")
    use_azure = str(provider in ("azure_openai",)).lower()  # python bool as string


    # Determine model names
    transcription_model = models.get("transcription_model", "gpt-4o-transcribe")
    extraction_model = models.get("extraction_model", "gpt-5.4")
    temperature = models.get("temperature", 0.0)

    schema_name = (
        bc.target_output_spec.get("schema_name")
        or bc.use_case.id.replace("_", " ").title().replace(" ", "")
        or "OutputSchema"
    )
    fields = bc.target_output_spec.get("fields", [])
    sample_field_lines = "\n".join(f"  - {f}" for f in fields[:5]) if fields else "  (no fields defined)"

    # Workflow steps summary for _generic template
    steps_summary = "\n".join(
        f"#   {i+1}. {s.id} ({s.type}): {s.component or 'user_task'} "
        f"{s.inputs} -> {s.outputs}"
        for i, s in enumerate(bc.workflow.steps)
    )

    # Component imports placeholder for _generic
    registry = get_registry()
    import_lines = []
    for step in bc.workflow.steps:
        if step.component and step.component not in ("custom", "human_review"):
            entry = registry.lookup_by_name(step.component) or registry.lookup_by_id(step.component)
            if entry and entry.get("import_path"):
                class_name = entry["name"]
                import_path = entry["import_path"]
                import_lines.append(f"from {import_path} import {class_name}")

    language = bc.technical_spec.get("language", "en") if isinstance(bc.technical_spec, dict) else getattr(bc.technical_spec, "language", "en")

    # LLMJudge section: inject real code if judge is in the selected pipeline,
    # otherwise inject a skip comment so run_poc.py stays syntactically valid.
    all_components = (
        [m.name if hasattr(m, "name") else m.get("name", "") for m in bc.components.selected_modules]
        + bc.components.selected_building_blocks
    )
    has_llm_judge = "LLMJudge" in all_components

    if has_llm_judge:
        llm_judge_section = '''\
    # -- LLMJudge hallucination detection (from blueprint) --
    # detect_hallucinations() checks each extracted field against the grounding
    # source text and flags any value not supported by it.
    # Uses OpenAI provider; use_azure is read from config (True for Azure OpenAI).
    print("\\nRunning LLMJudge hallucination detection...")
    try:
        from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge as _LLMJudge
        judge = _LLMJudge(model_provider="openai", use_azure=use_azure)

        # Resolve source text: transcript for audio pipelines, parsed document for document pipelines
        source_text = ""
        if hasattr(result, "transcription") and result.transcription:
            source_text = (
                getattr(result.transcription, "enhanced_transcript", None)
                or getattr(result.transcription, "raw_transcript", None)
                or ""
            )
        elif hasattr(result, "parsed_documents") and result.parsed_documents:
            source_text = "\\n\\n".join(result.parsed_documents)

        if source_text and result.extracted_fields:
            # The Extractor returns a list (multi-document pipeline).
            # detect_hallucinations() expects a plain dict, so unwrap
            # the first element for single-document PoC runs.
            extracted_for_judge = result.extracted_fields
            if isinstance(extracted_for_judge, list) and len(extracted_for_judge) == 1:
                extracted_for_judge = extracted_for_judge[0]
            report = judge.detect_hallucinations(
                source_text=source_text,
                extracted=extracted_for_judge,
            )
            if report.flags:
                print(f"WARNING: {len(report.flags)} hallucination flag(s) detected:")
                for flag in report.flags:
                    print(f"  field={flag.field}  value={flag.value}  reason={flag.reason}")
            else:
                print("Hallucination check passed -- all fields are grounded in the source.")
            validation_result = {
                "hallucination_flags": [
                    {"field": f.field, "value": f.value, "severity": str(f.severity), "reason": f.reason}
                    for f in report.flags
                ],
                "passed": len(report.flags) == 0,
            }
            val_path = output_dir / f"{input_file.stem}_validation.json"
            val_path.write_text(
                json.dumps(validation_result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"Validation report: {val_path}")
        else:
            print("LLMJudge skipped: no source text available for grounding.")
    except ImportError:
        print("LLMJudge skipped: gaik[llm-judge] not installed.")
    except Exception as _judge_exc:
        print(f"LLMJudge warning: {_judge_exc}")

    # -- Human review (blueprint step: supervisor_review) --
    print("\\nNOTE: Human review (supervisor approval) is not executed in the PoC.")
    print("      Gate 3 in the wizard conversation is the equivalent review step.")
    print("      In production, the approved_ticket artifact is produced here.")'''
    else:
        llm_judge_section = (
            "    # LLMJudge and human_review are not in this blueprint's pipeline."
        )

    return {
        "use_case_name": bc.use_case.name,
        "use_case_id": bc.use_case.id,
        "use_case_description": bc.use_case.description,
        "schema_name": schema_name,
        "provider": provider,
        "use_azure": use_azure,
        "transcription_model": transcription_model,
        "extraction_model": extraction_model,
        "temperature": temperature,
        "language": language,
        "llm_judge_section": llm_judge_section,
        "eval_framework": bc.evaluation.get("eval_framework", "extraction_eval") if isinstance(bc.evaluation, dict) else "extraction_eval",
        "eval_framework_body": _EVAL_BODIES.get(
            bc.evaluation.get("eval_framework", "") if isinstance(bc.evaluation, dict) else "",
            _DEFAULT_EVAL_BODY,
        ),
        "sample_field_lines": sample_field_lines,
        "workflow_steps_summary": steps_summary,
        "component_imports_placeholder": "\n".join(import_lines),
        "input_instructions": _input_instructions(bc),
        "output_instructions": _output_instructions(bc),
        # _generic template extras
        "generic_pipeline_skeleton": _build_generic_pipeline_skeleton(bc),
        "generic_input_loaders": _build_input_loaders(bc),
        "llm_judge_section_generic": _build_generic_judge_section(has_llm_judge),
        # optional PDF report (empty unless output_types includes 'pdf')
        "pdf_report_section": _build_pdf_report_section(bc, schema_name),
    }


def _input_instructions(bp: Blueprint) -> str:
    input_types = (
        bp.technical_spec.get("input_types", [])
        if isinstance(bp.technical_spec, dict)
        else getattr(bp.technical_spec, "input_types", [])
    )
    if "audio" in input_types or "video" in input_types:
        lang = (
            bp.technical_spec.get("language", "")
            if isinstance(bp.technical_spec, dict)
            else getattr(bp.technical_spec, "language", "")
        )
        lang_note = f" in {lang.upper()}" if lang else ""
        return (
            f"Place an audio recording{lang_note} (.wav or .mp3) in `sample_input/`.\n"
            "The pipeline will transcribe and enhance it before extraction."
        )
    if any(t in input_types for t in ("pdf", "docx", "document", "image")):
        return "Place a document (.pdf or .docx) in `sample_input/`."
    if "document_collection" in input_types:
        return "Place one or more documents (.pdf or .txt) in `sample_input/`. They will be indexed before you can query them."
    return f"Place your input file in `sample_input/`. Expected types: {input_types}."


def _output_instructions(bp: Blueprint) -> str:
    fields = bp.target_output_spec.get("fields", []) if isinstance(bp.target_output_spec, dict) else []
    input_types = (
        bp.technical_spec.get("input_types", [])
        if isinstance(bp.technical_spec, dict)
        else getattr(bp.technical_spec, "input_types", [])
    )
    # Match the actual filenames the templates write:
    # audio template writes _ticket.json; document template writes _result.json
    suffix = "_ticket.json" if "audio" in input_types or "video" in input_types else "_result.json"
    if fields:
        return (
            f"A JSON file with the following fields: {', '.join(fields[:6])}"
            + (" (and more)" if len(fields) > 6 else "")
            + f".\nWritten to `output/<input_stem>{suffix}`."
        )
    return f"Results written to `output/<input_stem>{suffix}`."


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------

def _write_requirements_txt(blueprint: Blueprint, poc_dir: Path) -> None:
    registry = get_registry()
    all_components = (
        [m.name if hasattr(m, "name") else m.get("name", "") for m in blueprint.components.selected_modules]
        + blueprint.components.selected_building_blocks
    )
    lines = registry.pip_requirements(all_components)
    lines.append("pyyaml")
    if _wants_pdf(blueprint):
        lines.append("reportlab>=4.0")
    (poc_dir / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pdf_report_helper(blueprint: Blueprint, poc_dir: Path) -> Path | None:
    """Copy the PDF report renderer into the PoC when PDF output is requested."""
    if not _wants_pdf(blueprint):
        return None
    tmpl = _read_template("_common", "pdf_report.py.tmpl") or ""
    path = poc_dir / "pdf_report.py"
    path.write_text(tmpl, encoding="utf-8")  # no template variables to fill
    return path


def _write_env_example(variables: Dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "env.example.tmpl") or ""
    (poc_dir / ".env.example").write_text(_fill(tmpl, variables), encoding="utf-8")


def _write_config_yaml(variables: Dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "config.yaml.tmpl") or ""
    (poc_dir / "config.yaml").write_text(_fill(tmpl, variables), encoding="utf-8")


def _write_run_poc(variables: Dict[str, Any], pattern: str, poc_dir: Path) -> bool:
    """Write run_poc.py from pattern template. Returns True if a fully-wired template was used."""
    tmpl = _read_template(pattern, "run_poc.py.tmpl")
    if not tmpl:
        tmpl = _read_template("_generic", "run_poc.py.tmpl") or ""
    (poc_dir / "run_poc.py").write_text(_fill(tmpl, variables), encoding="utf-8")
    return pattern != "_generic"


def _write_eval_script(variables: Dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "run_basic_eval.py.tmpl") or ""
    evals_dir = poc_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    (evals_dir / "run_basic_eval.py").write_text(_fill(tmpl, variables), encoding="utf-8")
    (evals_dir / "ground_truth" / ".gitkeep").parent.mkdir(parents=True, exist_ok=True)
    (evals_dir / "ground_truth" / ".gitkeep").touch()


def _write_readme(variables: Dict[str, Any], poc_dir: Path) -> None:
    tmpl = _read_template("_common", "README.md.tmpl") or ""
    (poc_dir / "README.md").write_text(_fill(tmpl, variables), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def scaffold_poc(
    blueprint: Blueprint,
    output_dir: Path,
    synthetic: bool = False,
) -> Dict[str, Any]:
    """Scaffold the complete poc/ folder for a validated blueprint.

    Args:
        blueprint: a V1-validated Blueprint object
        output_dir: root output dir (e.g. ~/projects/my-use-case/)
        synthetic: if True, generate synthetic input data where possible

    Returns:
        dict with 'poc_dir', 'pattern', 'template_wired' (bool),
        'files' (list of created paths).
    """
    poc_dir = output_dir / "poc"
    poc_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("sample_input", "output", "schemas", "prompts", "evals", "evals/ground_truth"):
        (poc_dir / sub).mkdir(parents=True, exist_ok=True)

    pattern = _determine_pattern(blueprint)
    variables = _build_variables(blueprint, pattern)

    files_created = []

    # Core boilerplate
    _write_requirements_txt(blueprint, poc_dir)
    files_created.append(poc_dir / "requirements.txt")

    _write_env_example(variables, poc_dir)
    files_created.append(poc_dir / ".env.example")

    _write_config_yaml(variables, poc_dir)
    files_created.append(poc_dir / "config.yaml")

    # Schema files
    # Primary path: if generate_schema.py was already run during Phase 5 of the
    # wizard conversation, the user-reviewed and approved files are already in
    # poc/schemas/. In that case, do NOT overwrite them with the deterministic
    # fallback -- the SchemaGenerator output takes precedence.
    _approved_schema = poc_dir / "schemas" / "output_schema.py"
    _approved_req = poc_dir / "schemas" / "output_schema_requirements.json"
    _schema_already_approved = _approved_schema.exists() and _approved_req.exists()

    has_fields = bool(
        blueprint.target_output_spec.get("fields") if isinstance(blueprint.target_output_spec, dict) else False
    )
    if pattern != "rag" and _schema_already_approved:
        # SchemaGenerator output exists and was approved -- use as-is
        files_created.append(_approved_schema)
        files_created.append(_approved_req)
    elif has_fields and pattern != "rag":
        # Fallback: no approved schema yet, generate deterministically from
        # target_output_spec.  The wizard should have called generate_schema.py
        # first, but this keeps scaffolding self-contained when run standalone.
        schema_results = write_schema_files(
            blueprint.target_output_spec
            if isinstance(blueprint.target_output_spec, dict)
            else blueprint.target_output_spec.model_dump(),
            variables["schema_name"],
            poc_dir,
            use_case_name=blueprint.use_case.id,
        )
        files_created.extend(schema_results.values())

    # extraction_requirements.md -- always write from target_output_spec if absent
    _req_prompt = poc_dir / "prompts" / "extraction_requirements.md"
    if has_fields and pattern != "rag" and not _req_prompt.exists():
        req_path = write_extraction_requirements(
            blueprint.target_output_spec
            if isinstance(blueprint.target_output_spec, dict)
            else blueprint.target_output_spec.model_dump(),
            poc_dir,
        )
        files_created.append(req_path)

    # run_poc.py
    template_wired = _write_run_poc(variables, pattern, poc_dir)
    files_created.append(poc_dir / "run_poc.py")

    # PDF report helper (only when technical_spec.output_types includes 'pdf')
    pdf_helper = _write_pdf_report_helper(blueprint, poc_dir)
    if pdf_helper is not None:
        files_created.append(pdf_helper)

    # Eval script
    _write_eval_script(variables, poc_dir)
    files_created.append(poc_dir / "evals" / "run_basic_eval.py")

    # README
    _write_readme(variables, poc_dir)
    files_created.append(poc_dir / "README.md")

    # Synthetic data for document/RAG patterns.
    # Both DocumentsToStructuredData (vision_parser) and RAGWorkflow (VisionRagParser)
    # require PDF files.  We attempt to generate a minimal PDF via reportlab;
    # if unavailable, we write a .txt placeholder and warn -- the run_poc.py templates
    # will handle this gracefully with a clear error at runtime.
    if synthetic and pattern in ("document_to_structured", "rag"):
        sample_dir = poc_dir / "sample_input"
        sample_dir.mkdir(parents=True, exist_ok=True)
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as rl_canvas
            pdf_path = sample_dir / "synthetic_sample.pdf"
            c = rl_canvas.Canvas(str(pdf_path), pagesize=A4)
            c.drawString(50, 750, f"SYNTHETIC SAMPLE - {blueprint.use_case.name}")
            c.drawString(50, 730, "Generated by GAIK Solution Configuration Wizard V2.")
            c.drawString(50, 710, "Replace with a real document for meaningful results.")
            c.save()
            files_created.append(pdf_path)
        except ImportError:
            txt_path = sample_dir / "synthetic_sample.txt"
            txt_path.write_text(
                f"SYNTHETIC SAMPLE\nGenerated for {blueprint.use_case.name}.\n"
                "NOTE: Replace with a real PDF document.\n"
                "The vision parser requires PDF; this .txt file will cause a runtime error.",
                encoding="utf-8",
            )
            files_created.append(txt_path)

    # The topology-aware key under which this pipeline's template would be saved
    # if the user later promotes it to the library (Part 2).
    pattern_key = _derive_pattern_key(blueprint)
    template_save_path = TEMPLATES_DIR / pattern_key / "run_poc.py.tmpl"

    return {
        "poc_dir": poc_dir,
        "pattern": pattern,
        "template_wired": template_wired,
        "pattern_key": pattern_key,
        "template_save_path": template_save_path,
        "files": files_created,
    }


def validate_generated_python(poc_dir: Path) -> Optional[str]:
    """Try to parse run_poc.py -- returns error string or None if valid."""
    run_poc = poc_dir / "run_poc.py"
    if not run_poc.exists():
        return "run_poc.py not found"
    try:
        ast.parse(run_poc.read_text(encoding="utf-8"))
        return None
    except SyntaxError as exc:
        return str(exc)
