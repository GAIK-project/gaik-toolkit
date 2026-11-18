/**
 * Edits to the full blueprint draft from the browser, as typed operations.
 *
 * The workspace's diagram does not save a whole blueprint: it sends what the
 * user did as operations (`POST /api/sessions/{id}/blueprint/operations`),
 * named against the version it shows. wizard_api applies them all or none
 * (`wizard_api/schemas/blueprint_ops.py`, the union these types mirror) and
 * answers with the session after the edit, what the edit left for the wizard
 * to complete and whether the diagram changed. A refusal (another tab or the
 * agent saved meanwhile, an operation that cannot apply) is thrown as
 * `OperationRefused` with the api's own words.
 */

import type { Blueprint } from "@/lib/mock-sessions";

/**
 * The largest blueprint, as JSON characters: `MAX_BLUEPRINT_CHARS` in
 * `solution_wizard/blueprint.py`, which refuses a larger one. The full
 * blueprint route takes a body up to this (and its small wrapper); the
 * operations, undo and layout routes take at most `MAX_EDIT_BODY_BYTES`.
 */
export const MAX_BLUEPRINT_CHARS = 1_000_000;

/** `MAX_REQUEST_BYTES` in `wizard_api/schemas/blueprint_ops.py`: an edit, an undo, a layout. */
export const MAX_EDIT_BODY_BYTES = 64 * 1024;

/** `MAX_OPERATIONS` there: the most operations one request carries. */
export const MAX_OPERATIONS = 50;

export type StepType = "user_task" | "automated_task" | "human_review";

/** `LaneKind` there: a lane for people in a role, or for a system. */
export type LaneKind = "human_role" | "system";

/** A decision's branches: `MIN_BRANCHES`..`MAX_BRANCHES` there, each condition 1..`MAX_CONDITION_CHARS`. */
export const MIN_BRANCHES = 2;
export const MAX_BRANCHES = 5;
export const MAX_CONDITION_CHARS = 200;
/** A step's or a decision's name: `MAX_NAME_CHARS` there. */
export const MAX_NAME_CHARS = 200;
/** The target of a branch that ends the process. */
export const DECISION_END = "end";

/**
 * A rework or rejection path's outcome: `"end"`, or back to a step,
 * `"loop_to:<step id>"` (an earlier step or the same one).
 */
export const REWORK_END = "end";
export const REWORK_LOOP_TO = "loop_to:";

/** A data object's name (`Artifact.label`): `MAX_LABEL_CHARS` there. */
export const MAX_LABEL_CHARS = 200;

/** How a step has a data object: it uses it (`inputs`) or makes it (`outputs`). */
export type DataRole = "input" | "output";

/** One way out of a business decision: its condition and the step it leads to, or `"end"`. */
export type DecisionBranch = { condition: string; target: string };

export type BlueprintOperation =
  | { op: "rename_step"; step_id: string; name: string }
  | { op: "set_step_description"; step_id: string; description: string }
  | { op: "add_step"; name: string; type: StepType; after?: string | null; before?: string | null }
  | { op: "remove_step"; step_id: string }
  | { op: "move_step"; step_id: string; after: string | null }
  | { op: "connect"; source: string; target: string }
  | { op: "disconnect"; source: string; target: string }
  | { op: "set_step_type"; step_id: string; type: StepType }
  | { op: "add_lane"; name: string; kind?: LaneKind }
  | { op: "rename_lane"; lane_id: string; name: string }
  | { op: "remove_lane"; lane_id: string }
  /** Who does the step: a lane's participant id, or null for the lane of its type. */
  | { op: "set_step_lane"; step_id: string; lane_id: string | null }
  /** A business decision (`business_process.decision_points`) after the step `after`. */
  | { op: "add_decision"; after: string; name: string; branches: DecisionBranch[] }
  | { op: "update_decision"; decision_id: string; name?: string | null; branches?: DecisionBranch[] | null }
  | { op: "remove_decision"; decision_id: string }
  /** A rework or rejection path (`business_process.exceptions`) on the step `attached_to`. */
  | { op: "add_rework_path"; attached_to: string; name: string; condition?: string; outcome: string }
  | {
      op: "update_rework_path";
      exception_id: string;
      name?: string | null;
      condition?: string | null;
      outcome?: string | null;
    }
  | { op: "remove_rework_path"; exception_id: string }
  /** A data object's name in the diagram; "" clears it (the generated name is used again). */
  | { op: "rename_data_object"; artifact_id: string; label: string }
  /** The step uses the data object (input) or makes it (output); a second step that makes it is refused. */
  | { op: "link_data"; artifact_id: string; step_id: string; role: DataRole }
  /** The only step that makes a data object another step uses is refused (`still_used`). */
  | { op: "unlink_data"; artifact_id: string; step_id: string; role: DataRole };

export type OperationsResult = {
  blueprint: Blueprint;
  warnings: string[];
  needsAttention: string[];
  bpmnChanged: boolean;
  /** The session's active version after the edit: the base of the next one. */
  version: number;
};

/** A 409 or 422 from the edit: `code` is wizard_api's error code (changed_elsewhere, invalid_operation...). */
export class OperationRefused extends Error {
  readonly status: number;
  readonly code: string;
  /** Where in the request: `operations[2].step_id`, a read-only section's name. */
  readonly field?: string;
  /** Which operation of the request was refused. */
  readonly index?: number;
  /** The operation's own reason (not_found, cycle...), the detail's `code`. */
  readonly reason?: string;

  constructor(
    status: number,
    refusal: { code: string; message: string; field?: string; index?: number; reason?: string },
  ) {
    super(refusal.message || refusal.code);
    this.name = "OperationRefused";
    this.status = status;
    this.code = refusal.code;
    if (refusal.field !== undefined) this.field = refusal.field;
    if (refusal.index !== undefined) this.index = refusal.index;
    if (refusal.reason !== undefined) this.reason = refusal.reason;
  }
}

export type Refusal = { code: string; message: string; field?: string; index?: number; reason?: string };

/**
 * The refusal in a route's answer: the `{detail: {...}}` a relay passes on
 * from wizard_api (lib/safe-error), or a route's own flat `{error}`. Null for
 * anything else (a FastAPI validation list, plain text).
 */
export function refusalOf(body: unknown): Refusal | null {
  if (!body || typeof body !== "object") return null;
  const outer = body as { detail?: unknown; error?: unknown; message?: unknown };
  const inner =
    outer.detail && typeof outer.detail === "object" && !Array.isArray(outer.detail)
      ? (outer.detail as Record<string, unknown>)
      : (outer as Record<string, unknown>);
  if (typeof inner.error !== "string" || !inner.error) return null;
  const refusal: Refusal = {
    code: inner.error,
    message: typeof inner.message === "string" ? inner.message : "",
  };
  if (typeof inner.field === "string") refusal.field = inner.field;
  if (typeof inner.index === "number") refusal.index = inner.index;
  if (typeof inner.code === "string") refusal.reason = inner.code;
  return refusal;
}

/**
 * What a save of the form, the flow view or the canvas was told, when it was
 * refused: `changed` when the blueprint changed since the edit started (the
 * page reads the newer one), else the refusal's own words for a 409 or 422.
 * Null when there is nothing to say beyond "the save failed".
 */
export function saveRefusal(
  status: number,
  body: unknown,
): { kind: "changed" } | { kind: "refused"; message: string } | null {
  if (status !== 409 && status !== 422) return null;
  const refusal = refusalOf(body);
  if (!refusal) return null;
  if (refusal.code === "changed_elsewhere") return { kind: "changed" };
  return refusal.message ? { kind: "refused", message: refusal.message } : null;
}

/** Applies `ops` to the session's draft, made on `baseVersion`. */
export async function postOperations(
  sessionId: string,
  baseVersion: number,
  ops: BlueprintOperation[],
): Promise<OperationsResult> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/blueprint/operations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_version: baseVersion, operations: ops }),
  });
  const body = (await res.json().catch(() => null)) as unknown;
  if (res.status === 409 || res.status === 422) {
    const refusal = refusalOf(body);
    if (refusal) throw new OperationRefused(res.status, refusal);
  }
  if (!res.ok) throw new Error(`the edit failed (${res.status})`);
  const data = body as {
    session?: { blueprint?: Blueprint; active_version?: number };
    warnings?: string[];
    needs_attention?: string[];
    bpmn_changed?: boolean;
  } | null;
  const blueprint = data?.session?.blueprint;
  if (!blueprint || typeof data?.session?.active_version !== "number") {
    throw new Error("the edit's answer has no blueprint");
  }
  return {
    blueprint,
    warnings: data.warnings ?? [],
    needsAttention: data.needs_attention ?? [],
    bpmnChanged: Boolean(data.bpmn_changed),
    version: data.session.active_version,
  };
}

/**
 * Undoes the last write to the session's blueprint (`POST .../blueprint/undo`),
 * made on `baseVersion`: wizard_api goes back to the version before it, as a
 * new version. Refusals (nothing_to_undo, changed_elsewhere, agent_busy...)
 * are thrown as `OperationRefused`; anything else, the 503 without wizard_api
 * included, as a plain Error.
 */
export async function postUndo(
  sessionId: string,
  baseVersion: number,
): Promise<{ blueprint: Blueprint; version: number }> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/blueprint/undo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_version: baseVersion }),
  });
  const body = (await res.json().catch(() => null)) as unknown;
  if (res.status === 409 || res.status === 422) {
    const refusal = refusalOf(body);
    if (refusal) throw new OperationRefused(res.status, refusal);
  }
  if (!res.ok) throw new Error(`the undo failed (${res.status})`);
  const data = body as { blueprint?: Blueprint; active_version?: number } | null;
  if (!data?.blueprint || typeof data.active_version !== "number") {
    throw new Error("the undo's answer has no blueprint");
  }
  return { blueprint: data.blueprint, version: data.active_version };
}
