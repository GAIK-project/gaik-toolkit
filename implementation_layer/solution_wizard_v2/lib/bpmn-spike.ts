/** V2 BPMN workspace — dynamic generation from session blueprint. */

/** Matches mock-sessions BPMN_VISUAL_STEP (onboarding phase 8). */
export const BPMN_VISUAL_STEP = 8;

/** Sprint 2 (#34): V2 BPMN — Modeler, JSON sync, dynamic generation. */
export const BPMN_V2_STARTED = true;

/**
 * From this step the workspace (BPMN/JSON) is primary — chat starts collapsed
 * (#74: canvas needs space; chat stays reopenable).
 */
export const CHAT_COLLAPSE_FROM_STEP = BPMN_VISUAL_STEP;

/** Seed mock sessions that always show BPMN from phase 8 onward. */
export const BPMN_SPIKE_SESSION_IDS = new Set(["ses_chatbot", "ses_laskut"]);

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Mock createSession ids: `ses_` + short hex (not a full UUID). */
const MOCK_SESSION_RE = /^ses_[0-9a-f]+$/i;

/** Seed mocks, newly created mocks (`ses_*`), and wizard_api UUID sessions. */
export function hasBpmnSpike(sessionId: string): boolean {
  return (
    BPMN_SPIKE_SESSION_IDS.has(sessionId) ||
    MOCK_SESSION_RE.test(sessionId) ||
    UUID_RE.test(sessionId)
  );
}

/** BPMN from onboarding phase 8 (visual workflow) onward. */
export function shouldShowBpmnSpike(sessionId: string, wizardStep: number): boolean {
  return hasBpmnSpike(sessionId) && wizardStep >= BPMN_VISUAL_STEP;
}

/**
 * Chat rail starts collapsed so the workspace can breathe, except while the
 * session waits on a gate: the agent's summary of what the gate approves is in
 * the chat, and it belongs beside the decision bar.
 */
export function shouldCollapseChatByDefault(
  wizardStep: number,
  pendingGate = false,
): boolean {
  return wizardStep >= CHAT_COLLAPSE_FROM_STEP && !pendingGate;
}
