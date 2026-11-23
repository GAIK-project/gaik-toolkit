import type { WizardSession } from "@/lib/mock-sessions";
import type { Dict } from "@/lib/i18n";
import { recordRequirementAnswer } from "@/lib/sessions";
import { nextQuestion } from "@/lib/requirements-model";

// Mock assistant used when the wizard_api agent is not in play. The live V1
// agent (#29) runs in wizard_api; the SSE route proxies to it directly when
// `wizardAgentChatEnabled()`, and only falls back here otherwise — so this stays
// the mock, not the integration point.
//
// It is phase-aware. During gathering (steps 1–3) it records the user's message
// as the answer to the current Section-9 checklist question and returns the next
// question (or a wrap-up when all are gathered).
export async function resolveChatReply(
  id: string,
  session: WizardSession,
  userMessage: string,
  t: Dict,
): Promise<string> {
  const req = session.requirements;
  const gathering =
    session.step <= 3 && req !== undefined && req.answers.length < req.points.length;

  if (gathering) {
    await recordRequirementAnswer(id, userMessage);
    // One more answer is now recorded, so ask the point after it (or wrap up).
    return nextQuestion(req.points, req.answers.length + 1);
  }

  const phase = t.phases[session.step - 1];
  return `${t.chatMockReplyPre}"${phase}"${t.chatMockReplyPost}`;
}

/** Split a reply into stream tokens (word + trailing space). */
export function toStreamTokens(reply: string): string[] {
  return reply.match(/\S+\s*/g) ?? [reply];
}
