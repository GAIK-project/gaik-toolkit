"""BlueprintValidator -- implements all V1 validation rules (spec §10.4).

Returns a ValidationResult with structured errors and warnings.
Errors block downstream phases; warnings are surfaced but do not block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .blueprint import ArtifactSource, AssumptionStatus, Blueprint
from .registry import Registry, get_registry


@dataclass
class Issue:
    rule: int
    message: str
    step_id: Optional[str] = None
    artifact_id: Optional[str] = None

    def __str__(self) -> str:
        loc = ""
        if self.step_id:
            loc = f" [step: {self.step_id}]"
        elif self.artifact_id:
            loc = f" [artifact: {self.artifact_id}]"
        return f"Rule {self.rule}{loc}: {self.message}"


@dataclass
class ValidationResult:
    ok: bool
    errors: List[Issue] = field(default_factory=list)
    warnings: List[Issue] = field(default_factory=list)

    def summary(self) -> str:
        lines = []
        if self.ok:
            lines.append("Validation PASSED")
        else:
            lines.append(f"Validation FAILED ({len(self.errors)} error(s))")
        for e in self.errors:
            lines.append(f"  ERROR   {e}")
        for w in self.warnings:
            lines.append(f"  WARNING {w}")
        return "\n".join(lines)


def validate(blueprint: Blueprint, registry: Optional[Registry] = None) -> ValidationResult:
    if registry is None:
        registry = get_registry()

    errors: List[Issue] = []
    warnings: List[Issue] = []

    steps = blueprint.workflow.steps
    artifacts = blueprint.artifacts
    step_ids = [s.id for s in steps]

    # ------------------------------------------------------------------
    # Rule 1: unique step IDs
    seen_ids: set = set()
    for step in steps:
        if step.id in seen_ids:
            errors.append(Issue(1, f"Duplicate step id '{step.id}'", step_id=step.id))
        seen_ids.add(step.id)

    # ------------------------------------------------------------------
    # Rule 2: step inputs/outputs reference declared artifacts
    for step in steps:
        for art_id in step.inputs:
            if art_id not in artifacts:
                errors.append(
                    Issue(2, f"Input '{art_id}' not declared in artifacts", step_id=step.id)
                )
        for art_id in step.outputs:
            if art_id not in artifacts:
                errors.append(
                    Issue(2, f"Output '{art_id}' not declared in artifacts", step_id=step.id)
                )

    # ------------------------------------------------------------------
    # Rule 3: components exist in registry, OR as a reference card (wireable in
    # custom/hybrid pipelines), OR are marked custom.
    # The reference cards are the superset of components that can be wired in a
    # _generic pipeline (every registry entry, plus building blocks that are
    # callable but not independently selectable), so a hybrid step naming a
    # card-only component is valid. Which components are card-only changes as
    # gaik-sync adds registry entries -- don't hard-code an example here.
    _card_names = set()
    try:
        from .registry import get_reference_cards

        _card_names = set(get_reference_cards().names())
    except Exception:
        pass
    for step in steps:
        if step.component and step.component not in ("custom", "human_review"):
            if not registry.exists(step.component) and step.component not in _card_names:
                errors.append(
                    Issue(
                        3,
                        f"Component '{step.component}' is not in the registry or reference cards",
                        step_id=step.id,
                    )
                )

    # ------------------------------------------------------------------
    # Rule 4: component artifact-type compatibility
    for step in steps:
        if not step.component or step.component in ("custom", "human_review"):
            continue
        entry = registry.lookup_by_id(step.component) or registry.lookup_by_name(step.component)
        if not entry:
            continue
        allowed_inputs = entry.get("input_artifact_types", [])
        allowed_outputs = entry.get("output_artifact_types", [])
        for art_id in step.inputs:
            art = artifacts.get(art_id)
            if art and allowed_inputs and art.type not in allowed_inputs:
                errors.append(
                    Issue(
                        4,
                        f"Component '{step.component}' does not accept artifact type '{art.type}' "
                        f"(allowed: {allowed_inputs})",
                        step_id=step.id,
                    )
                )
        for art_id in step.outputs:
            art = artifacts.get(art_id)
            if art and allowed_outputs and art.type not in allowed_outputs:
                errors.append(
                    Issue(
                        4,
                        f"Component '{step.component}' does not produce artifact type '{art.type}' "
                        f"(allowed: {allowed_outputs})",
                        step_id=step.id,
                    )
                )

    # ------------------------------------------------------------------
    # Rule 5: required parameters present
    for step in steps:
        if not step.component or step.component in ("custom", "human_review"):
            continue
        entry = registry.lookup_by_id(step.component) or registry.lookup_by_name(step.component)
        if not entry:
            continue
        for req_param in entry.get("required_parameters", []):
            if req_param not in step.parameters:
                errors.append(
                    Issue(
                        5,
                        f"Component '{step.component}' requires parameter '{req_param}' but it is missing",
                        step_id=step.id,
                    )
                )

    # ------------------------------------------------------------------
    # Rule 6: overwrites flagged
    produced_artifacts: dict = {}
    for step in steps:
        for art_id in step.outputs:
            if art_id in produced_artifacts:
                art = artifacts.get(art_id)
                if art and not art.overwrite:
                    errors.append(
                        Issue(
                            6,
                            f"Artifact '{art_id}' is produced by both step "
                            f"'{produced_artifacts[art_id]}' and step '{step.id}' "
                            f"but is not flagged overwrite=true",
                            artifact_id=art_id,
                        )
                    )
            produced_artifacts[art_id] = step.id

    # ------------------------------------------------------------------
    # Rule 7: generated artifacts have valid produced_by + consistency + no consume-before-produce
    step_outputs_map: dict = {s.id: set(s.outputs) for s in steps}

    for art_id, art in artifacts.items():
        if art.source == ArtifactSource.GENERATED:
            if art.produced_by and art.produced_by not in step_ids:
                errors.append(
                    Issue(
                        7,
                        f"Artifact '{art_id}' references produced_by='{art.produced_by}' "
                        f"which is not a valid step id",
                        artifact_id=art_id,
                    )
                )
            elif art.produced_by and art.produced_by in step_outputs_map:
                # Cross-check: the step named in produced_by must actually list this
                # artifact in its outputs -- both sides of the relationship must agree.
                if art_id not in step_outputs_map[art.produced_by]:
                    errors.append(
                        Issue(
                            7,
                            f"Artifact '{art_id}' claims produced_by='{art.produced_by}' "
                            f"but that step does not list '{art_id}' in its outputs "
                            f"(step outputs: {sorted(step_outputs_map[art.produced_by])})",
                            artifact_id=art_id,
                        )
                    )

    # Topological check: artifact must be produced before it is consumed.
    # NOTE (known limitation): uses step-list position as a proxy for execution
    # order. This is correct for linear pipelines but would give false positives
    # for parallel branches where depends_on is authoritative. A proper fix would
    # topologically sort from the depends_on graph and validate against that order.
    step_output_index: dict = {}
    for i, step in enumerate(steps):
        for art_id in step.outputs:
            step_output_index[art_id] = i

    for i, step in enumerate(steps):
        for art_id in step.inputs:
            if art_id in step_output_index:
                if step_output_index[art_id] >= i:
                    errors.append(
                        Issue(
                            7,
                            f"Artifact '{art_id}' is consumed at step '{step.id}' (position {i}) "
                            f"but not produced until position {step_output_index[art_id]}",
                            step_id=step.id,
                        )
                    )

    # ------------------------------------------------------------------
    # Rule 8: acyclicity (DFS on depends_on graph)
    adj: dict = {s.id: set(s.depends_on) for s in steps}

    def has_cycle(node: str, visited: set, path: set) -> bool:
        visited.add(node)
        path.add(node)
        for neighbour in adj.get(node, set()):
            if neighbour not in visited:
                if has_cycle(neighbour, visited, path):
                    return True
            elif neighbour in path:
                return True
        path.discard(node)
        return False

    visited: set = set()
    for s in steps:
        if s.id not in visited:
            if has_cycle(s.id, visited, set()):
                # Check for explicit loop declaration
                loop_ids = {s.id for s in steps if s.loop is not None}
                if s.id not in loop_ids:
                    errors.append(
                        Issue(
                            8,
                            f"Workflow graph contains a cycle involving step '{s.id}' "
                            f"with no loop declaration (max_iterations/loop_condition_ref)",
                            step_id=s.id,
                        )
                    )

    # ------------------------------------------------------------------
    # Rule 9: at least one terminal step produces final_output=true
    # NOTE (backlog): the spec §10.2 requires a final_output artifact to also
    # satisfy one of: (1) produced by a terminal delivery step, (2) produced by
    # a human-review step, or (3) marked externally_visible=true. The current
    # check only verifies existence. The stricter check matters most in V3+ when
    # evaluation pipelines downstream of the final artifact would otherwise
    # incorrectly disqualify it. Acceptable for V1 blueprint-only output.
    has_final = any(a.final_output for a in artifacts.values())
    if steps and not has_final:
        errors.append(
            Issue(
                9,
                "No artifact is marked final_output=true. "
                "At least one terminal step must produce a deliverable.",
            )
        )

    # ------------------------------------------------------------------
    # Rule 10: referenced prompt/schema paths -- verify naming convention and existence
    ALLOWED_MARKERS = {"to_be_generated", "tbd", "generated"}
    # The scaffold always creates output_schema.py / output_schema_requirements.json.
    # Any other name will cause load_schema() to silently fall through to regeneration.
    EXPECTED_SCHEMA_REF = "schemas/output_schema.py"
    EXPECTED_REQ_REF = "schemas/output_schema_requirements.json"

    for step in steps:
        for param_key in ("schema_ref", "requirements_ref"):
            val = step.parameters.get(param_key, "")
            if not val:
                continue
            if val.lower() in ALLOWED_MARKERS:
                continue
            # Warn if the path doesn't follow the scaffold convention
            if param_key == "schema_ref" and val != EXPECTED_SCHEMA_REF:
                warnings.append(
                    Issue(
                        10,
                        f"Step '{step.id}': schema_ref='{val}' does not match the scaffold "
                        f"convention '{EXPECTED_SCHEMA_REF}'. The scaffold always writes "
                        f"'schemas/output_schema.py' regardless of schema class name. "
                        f"Mismatched names cause load_schema() to skip the pre-generated schema.",
                        step_id=step.id,
                    )
                )
            elif param_key == "requirements_ref" and val != EXPECTED_REQ_REF:
                warnings.append(
                    Issue(
                        10,
                        f"Step '{step.id}': requirements_ref='{val}' does not match the scaffold "
                        f"convention '{EXPECTED_REQ_REF}'.",
                        step_id=step.id,
                    )
                )
            else:
                # Path follows convention -- only warn that it can't be checked at design time
                warnings.append(
                    Issue(
                        10,
                        f"Parameter '{param_key}' = '{val}' in step '{step.id}' "
                        f"references a path that cannot be verified at design time. "
                        f"Ensure this file exists at runtime or mark as 'to_be_generated'.",
                        step_id=step.id,
                    )
                )

    # ------------------------------------------------------------------
    # Rule 11: assumptions well-formed (warnings only)
    for assumption in blueprint.assumptions:
        if not assumption.id or not assumption.text:
            warnings.append(
                Issue(11, f"Assumption is missing id or text: {assumption.model_dump()}")
            )
        if assumption.status == AssumptionStatus.UNCONFIRMED and assumption.impact in (
            "component_selection",
            "security_constraint",
            "human_review",
        ):
            warnings.append(
                Issue(
                    11,
                    f"High-impact assumption '{assumption.id}' is still unconfirmed. "
                    f"Resolve before production packaging. "
                    f'Text: "{assumption.text}"',
                )
            )

    # ------------------------------------------------------------------
    # Rule 12: redundant sub-component already provided internally (warnings only).
    # If a step uses a component/module that `subsumes` or `uses_components`
    # another component, and a *separate* step also uses that inner component,
    # recommend enabling it via an option on the parent instead. The canonical
    # case: Transcriber(enhanced_transcript=True) on audio input makes a
    # separate TranscriptEnhancer step redundant.
    step_by_component = {}
    for s in steps:
        if s.component:
            step_by_component.setdefault(s.component, s)
    for s in steps:
        if not s.component:
            continue
        entry = registry.lookup_by_name(s.component)
        if not entry:
            continue
        provided = set(entry.get("subsumes", []) or []) | set(
            entry.get("uses_components", []) or []
        )
        for inner in provided:
            other = step_by_component.get(inner)
            if other is not None and other.id != s.id:
                hint = (
                    "set Transcriber(enhanced_transcript=True) on the audio step instead"
                    if s.component == "Transcriber" and inner == "TranscriptEnhancer"
                    else f"enable it via an option/parameter on '{s.component}' instead of a separate step"
                )
                warnings.append(
                    Issue(
                        12,
                        f"Step '{other.id}' uses '{inner}', which is already provided internally by "
                        f"'{s.component}' (step '{s.id}'). Redundant -- {hint}.",
                        step_id=other.id,
                    )
                )

    ok = len(errors) == 0
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)
