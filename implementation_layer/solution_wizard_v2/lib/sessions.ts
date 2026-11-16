/**
 * Session store — wizard_api when WIZARD_API_URL is set, else in-memory mock.
 */

import { ownerId } from "@/lib/owner-id";
import {
  apiClaimLegacySessions,
  apiCreateSession,
  apiDeleteSession,
  apiEndAgent,
  apiGetPocFiles,
  apiGetSession,
  apiListSessions,
  apiPatchSession,
  apiPatchBlueprint,
  apiPostMessages,
  apiReopenGate,
  WizardApiError,
  type ApiSessionDetail,
  type ApiSessionSummary,
  wizardApiEnabled,
} from "@/lib/wizard-api-client";
import {
  PHASE_COUNT,
  isGateStep,
  type Blueprint,
  type BlueprintStepType,
  type BlueprintVersion,
  type ChatMessage,
  type GateReopened,
  type WizardSession,
} from "@/lib/mock-sessions";
import * as mock from "@/lib/mock-sessions";

export {
  GATE_STEPS,
  PHASE_COUNT,
  PHASES,
  BPMN_VISUAL_STEP,
  isBpmnVisualPhase,
  isGateStep,
} from "@/lib/mock-sessions";
export type {
  Assumption,
  BusinessContext,
  Blueprint,
  BlueprintStep,
  BlueprintStepType,
  BlueprintVersion,
  ChatMessage,
  ChatRole,
  GateReopened,
  GateStatus,
  PendingTurn,
  WizardSession,
} from "@/lib/mock-sessions";

import {
  apiGatesToUi,
  uiGateApprovalPatch,
} from "@/lib/session-gate-map";
import { GATE_STEPS, transition } from "@/lib/wizard-state-machine";
import { packageChangedSinceRun } from "@/lib/poc-result-state";

/** metadata.gate_reopened as the page shows it, while that gate still waits. */
function gateReopenedIn(detail: ApiSessionDetail): GateReopened | null {
  const raw = detail.metadata.gate_reopened;
  if (!raw || typeof raw !== "object") return null;
  const { gate, by, reason, at } = raw as Record<string, unknown>;
  const match = typeof gate === "string" ? /^gate_([1-4])$/.exec(gate) : null;
  if (!match || detail.gate_statuses[gate as string] === "approved") return null;
  return {
    gate: Number(match[1]),
    by: by === "agent" || by === "change" ? by : "user",
    reason: typeof reason === "string" ? reason : "",
    ...(typeof at === "string" ? { at } : {}),
  };
}

function metadataDigest(detail: ApiSessionDetail, key: string): string | null {
  const value = detail.metadata[key];
  return typeof value === "string" && value ? value : null;
}

function detailToWizardSession(detail: ApiSessionDetail): WizardSession {
  return {
    id: detail.id,
    userId: detail.user_id,
    title: detail.title,
    step: detail.step,
    gateStatus: apiGatesToUi(detail.step, detail.gate_statuses),
    status: detail.status === "done" ? "done" : "active",
    outputDir: detail.output_dir,
    createdAt: detail.created_at,
    updatedAt: detail.updated_at,
    versions: detail.versions.map(
      (v): BlueprintVersion => ({
        version: v.version,
        createdAt: v.created_at,
        note: v.note,
      }),
    ),
    activeVersion: detail.active_version,
    messages: detail.messages as ChatMessage[],
    blueprint: {
      ...detail.blueprint,
      steps: detail.blueprint.steps.map((s) => ({
        ...s,
        type: s.type as BlueprintStepType,
      })),
    } satisfies Blueprint,
    businessContext: detail.business_context
      ? {
          currentProcess: detail.business_context.current_process ?? "",
          painPoints: detail.business_context.pain_points ?? [],
          intendedUsers: detail.business_context.intended_users ?? [],
          reviewers: detail.business_context.reviewers ?? [],
          expectedValue: detail.business_context.expected_value ?? [],
          knowledgeProcesses: detail.business_context.knowledge_processes ?? [],
          domain: detail.business_context.domain ?? "",
        }
      : null,
    targetOutputSpec: detail.target_output_spec
      ? {
          schemaName: detail.target_output_spec.schema_name ?? "",
          fields: detail.target_output_spec.fields ?? [],
          fieldTypes: detail.target_output_spec.field_types ?? {},
          requiredFields: detail.target_output_spec.required_fields ?? [],
          optionalFields: detail.target_output_spec.optional_fields ?? [],
          fieldDescriptions: detail.target_output_spec.field_descriptions ?? {},
          allowedValues: detail.target_output_spec.allowed_values ?? {},
          missingValuePolicy: detail.target_output_spec.missing_value_policy ?? "",
          validationRules: detail.target_output_spec.validation_rules ?? [],
        }
      : null,
    assumptions: (detail.assumptions ?? []).map((a) => ({
      id: a.id,
      text: a.text,
      status: a.status,
      impact: a.impact,
    })),
    lastSuccessfulRun:
      typeof detail.metadata.last_successful_run === "string" && detail.metadata.last_successful_run
        ? detail.metadata.last_successful_run
        : null,
    latestRun:
      typeof detail.metadata.latest_run === "string" && detail.metadata.latest_run
        ? detail.metadata.latest_run
        : null,
    // The digests wizard_api keeps with the runs; null from an api without them.
    latestRunPackage: metadataDigest(detail, "latest_run_package"),
    lastSuccessfulRunPackage: metadataDigest(detail, "last_successful_run_package"),
    pendingTurn: detail.pending_turn
      ? { userMessage: detail.pending_turn.user_message, startedAt: detail.pending_turn.started_at }
      : null,
    agentLive: typeof detail.agent_live === "boolean" ? detail.agent_live : null,
    gateReopened: gateReopenedIn(detail),
    // wizard_api's reading of the wizard's files (artifact_sync.step_reached).
    reachedStep: typeof detail.metadata.agent_step === "number" ? detail.metadata.agent_step : null,
  };
}

function summaryToWizardSession(summary: ApiSessionSummary): WizardSession {
  const title =
    typeof summary.metadata.title === "string" && summary.metadata.title.trim()
      ? summary.metadata.title.trim()
      : "Nimetön sessio";
  const status =
    summary.metadata.status === "done" || summary.step >= PHASE_COUNT
      ? "done"
      : "active";
  return {
    id: String(summary.id),
    userId: summary.user_id,
    title,
    step: summary.step,
    gateStatus: apiGatesToUi(summary.step, summary.gate_statuses),
    status,
    outputDir: summary.output_dir,
    createdAt: summary.created_at,
    updatedAt: summary.updated_at,
    versions: [],
    activeVersion: summary.active_version,
    messages: [],
    blueprint: {
      name: title,
      description: "",
      goal: "",
      steps: [],
    },
  };
}

// Owner ids whose sessions under the e-mail address have been moved in this
// process; each user's are moved once, on their first request here.
const claimedOwners = new Set<string>();

/**
 * Sessions made before owner ids are saved under the e-mail address: move the
 * user's to their owner id before anything looks them up. A failure is left for
 * the next request to retry and does not stop this one.
 */
export async function claimLegacySessions(email: string): Promise<void> {
  if (!wizardApiEnabled()) return;
  const owner = ownerId(email);
  if (claimedOwners.has(owner)) return;
  try {
    await apiClaimLegacySessions(email);
    claimedOwners.add(owner);
  } catch {
    // The API is down or older than this app; the next request tries again.
  }
}

/** Test hook: forget which owners were already claimed. */
export function resetClaimedOwnersForTests(): void {
  claimedOwners.clear();
}

/**
 * The owner `email`'s sessions are saved under: its owner id in wizard_api, the
 * address itself in the in-memory mock store, which never leaves the process.
 */
export function sessionOwnerFor(email: string): string {
  return wizardApiEnabled() ? ownerId(email) : email;
}

/** The signed-in user's sessions; `email` is their address, the owner id is derived. */
export async function listSessions(email: string): Promise<WizardSession[]> {
  if (!wizardApiEnabled()) {
    return mock.listSessions(email);
  }
  await claimLegacySessions(email);
  const summaries = await apiListSessions(ownerId(email));
  return summaries.map(summaryToWizardSession);
}

export async function getSession(id: string): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    return mock.getSession(id);
  }
  try {
    const detail = await apiGetSession(id);
    return detailToWizardSession(detail);
  } catch {
    return undefined;
  }
}

export type CreateSessionOptions = {
  /**
   * The session starts from the user's first message, as the live wizard's do:
   * an empty conversation and no requirement checklist. Only the mock store
   * reads it; the live API starts every session that way.
   */
  chatLed?: boolean;
};

/** A new session owned by the signed-in user; `email` is their address. */
export async function createSession(
  email: string,
  title: string,
  options?: CreateSessionOptions,
): Promise<WizardSession> {
  if (!wizardApiEnabled()) {
    return options ? mock.createSession(email, title, options) : mock.createSession(email, title);
  }
  const detail = await apiCreateSession(ownerId(email), title);
  return detailToWizardSession(detail);
}

/**
 * Gives the session another name. The blueprint keeps the name it was made
 * with. False when the session is gone or the API refused.
 */
export async function renameSessionTitle(id: string, title: string): Promise<boolean> {
  if (!wizardApiEnabled()) {
    return mock.renameSession(id, title) !== undefined;
  }
  try {
    await apiPatchSession(id, { metadata: { title } });
    return true;
  } catch {
    return false;
  }
}

export type DeleteResult = "deleted" | "busy" | "protected" | "failed";

/** Removes the session for good. A 404 means it is gone already. */
export async function deleteSession(id: string): Promise<DeleteResult> {
  if (!wizardApiEnabled()) {
    mock.deleteSession(id);
    return "deleted";
  }
  const res = await apiDeleteSession(id);
  if (res.ok || res.status === 404) return "deleted";
  if (res.status === 409) {
    const body = (await res.json().catch(() => null)) as {
      detail?: { error?: string };
    } | null;
    return body?.detail?.error === "session_protected" ? "protected" : "busy";
  }
  return "failed";
}

export async function postMessage(
  id: string,
  userContent: string,
  assistantContent: string,
): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    return mock.postMessage(id, userContent, assistantContent);
  }
  try {
    const detail = await apiPostMessages(id, userContent, assistantContent);
    return detailToWizardSession(detail);
  } catch {
    return undefined;
  }
}

/**
 * Move one step on. With `from`, only when the session stands on that step:
 * the caller read the session a moment ago, and a move decided on that read
 * must not be applied to wherever another request has taken the session since.
 */
export async function advanceSession(
  id: string,
  from?: number,
): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    const standing = mock.getSession(id);
    if (from !== undefined && standing && standing.step !== from) return standing;
    return mock.advanceSession(id);
  }
  const current = await getSession(id);
  if (!current) return current;
  if (from !== undefined && current.step !== from) return current;
  const t = transition(
    { step: current.step, gateStatus: current.gateStatus },
    "ADVANCE",
  );
  if (t.noop) return current;
  // Moving a step changes no blueprint, so it makes no version: a version
  // posted without content copied the latest one, and every click on "Next
  // step" added a duplicate. Blueprint edits make their own versions.
  await apiPatchSession(id, { step: t.state.step });
  return getSession(id);
}

export async function regressSession(
  id: string,
): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    return mock.regressSession(id);
  }
  const current = await getSession(id);
  if (!current) return current;
  const t = transition(
    { step: current.step, gateStatus: current.gateStatus },
    "REGRESS",
  );
  if (t.noop) return current;
  await apiPatchSession(id, {
    step: t.state.step,
    metadata: { status: "active" },
  });
  return getSession(id);
}

// With `gateStep`, only that gate: a request decided for one gate must not
// approve the next one because the session has moved onto it meanwhile.
export async function approveGate(id: string, gateStep?: number): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    const standing = mock.getSession(id);
    if (gateStep !== undefined && standing && standing.step !== gateStep) return standing;
    // As wizard_api answers: Gate 3 is not approved on a run of another package.
    if (
      standing?.step === GATE_STEPS[2] &&
      packageChangedSinceRun(standing.packageDigest, standing.lastSuccessfulRunPackage)
    ) {
      throw new WizardApiError(
        409,
        `/sessions/${id}`,
        JSON.stringify({
          detail: {
            error: "gate_not_ready",
            gate: "gate_3",
            reason: "package_changed",
            message: "The package changed after the last successful test run. Run the test again, then approve.",
          },
        }),
      );
    }
    return mock.approveGate(id);
  }
  const current = await getSession(id);
  if (!current || !isGateStep(current.step)) return current;
  if (gateStep !== undefined && current.step !== gateStep) return current;
  const patch = uiGateApprovalPatch(current.step);
  if (!patch) return current;
  if (current.step >= PHASE_COUNT) {
    const detail = await apiPatchSession(id, {
      gate_statuses: patch,
      metadata: { status: "done" },
    });
    return detailToWizardSession(detail);
  }
  await apiPatchSession(id, { gate_statuses: patch });
  // Move on from the gate this approval was for, not from wherever a fresh read
  // finds the session: two approvals of one gate sent at about the same time
  // each re-read the step, and the second moved one step past the first.
  // Setting the step after the gate is the same write for both.
  const t = transition(
    { step: current.step, gateStatus: { ...current.gateStatus, [current.step]: "approved" } },
    "ADVANCE",
  );
  if (!t.noop) await apiPatchSession(id, { step: t.state.step });
  return getSession(id);
}

/**
 * The digest of the session's package as it is now, as a test run is tied to
 * it (wizard_api's `package_digest`). Null when there is no package, when the
 * api does not give one, or when it could not be read: an unknown digest is
 * never held against a result.
 */
export async function getPackageDigest(id: string): Promise<string | null> {
  if (!wizardApiEnabled()) return mock.getSession(id)?.packageDigest ?? null;
  try {
    const digest = (await apiGetPocFiles(id)).package_digest;
    return typeof digest === "string" && digest ? digest : null;
  } catch {
    return null;
  }
}

/**
 * Releases the wizard held for a session: a live one is a process on the
 * server, and they are few. The session, its files and the conversation stay,
 * and the next message starts the wizard again from where it left off.
 */
export async function endAgent(id: string): Promise<"ended" | "busy" | "failed"> {
  if (!wizardApiEnabled()) return "ended";
  try {
    await apiEndAgent(id);
    return "ended";
  } catch (err) {
    return err instanceof WizardApiError && err.status === 409 ? "busy" : "failed";
  }
}

export type ReopenResult = "reopened" | "busy" | "not_approved" | "failed";

/**
 * Takes back the approval of gate 1–4 and of the gates after it, so a change
 * to what it covers is reviewed and approved again. The session goes back onto
 * that gate's step.
 */
export async function reopenGate(id: string, gate: number): Promise<ReopenResult> {
  if (!wizardApiEnabled()) {
    return mock.reopenGate(id, gate) ? "reopened" : "not_approved";
  }
  try {
    await apiReopenGate(id, gate);
    return "reopened";
  } catch (err) {
    if (err instanceof WizardApiError && err.status === 409) {
      return err.code === "agent_busy" ? "busy" : "not_approved";
    }
    return "failed";
  }
}

export async function recordRequirementAnswer(
  id: string,
  answer: string,
): Promise<WizardSession | undefined> {
  // Chat-driven requirements gathering is mock; the real agent is #29/#31.
  if (wizardApiEnabled()) {
    return getSession(id);
  }
  return mock.recordRequirementAnswer(id, answer);
}

export async function saveBlueprintAfterBpmnSync(
  id: string,
  blueprint: Blueprint,
): Promise<WizardSession | undefined> {
  return patchSessionBlueprint(id, blueprint, "BPMN canvas sync");
}

export async function patchSessionBlueprint(
  id: string,
  blueprint: Blueprint,
  note = "Blueprint päivitetty",
): Promise<WizardSession | undefined> {
  if (!wizardApiEnabled()) {
    return mock.updateBlueprint(id, blueprint, note);
  }
  try {
    const detail = await apiPatchBlueprint(id, blueprint, note);
    return detailToWizardSession(detail);
  } catch {
    return undefined;
  }
}
