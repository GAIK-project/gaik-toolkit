/**
 * Unsaved BPMN canvas edits kept per session while the tab or notation is
 * switched. Both the BPMN panel and the simple flow view read this so that
 * "Lopeta muokkaus" in the simple flow waits when a BPMN draft is still open.
 */

export type BpmnSessionDraft = { base: string; xml: string };

const drafts = new Map<string, BpmnSessionDraft>();
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function getBpmnDraft(sessionId: string): BpmnSessionDraft | undefined {
  return drafts.get(sessionId);
}

export function hasBpmnDraft(sessionId: string): boolean {
  return drafts.has(sessionId);
}

export function setBpmnDraft(sessionId: string, draft: BpmnSessionDraft): void {
  const prev = drafts.get(sessionId);
  if (prev && prev.base === draft.base && prev.xml === draft.xml) return;
  drafts.set(sessionId, draft);
  emit();
}

export function deleteBpmnDraft(sessionId: string): void {
  if (!drafts.delete(sessionId)) return;
  emit();
}

export function subscribeBpmnDrafts(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
