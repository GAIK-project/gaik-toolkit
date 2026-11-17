// The intake the model submits must carry the user's own words. The skill's
// checker verifies quotes against the intake; this checks the intake against
// what the user actually typed in this conversation.

function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export interface SubmittedIntake {
  description: string;
  questions: { id: string; batch?: string; question: string; answer: string }[];
}

/** Problems with the intake's quoted text; empty when it is faithful. */
export function intakeProblems(
  intake: SubmittedIntake,
  userTexts: string[],
): string[] {
  const haystack = collapse(userTexts.join("\n"));
  const problems: string[] = [];
  const parts = intake.description.split(/\n+/).map(collapse).filter(Boolean);
  if (parts.length === 0) problems.push("description is empty");
  for (const part of parts) {
    if (!haystack.includes(part))
      problems.push(
        `description contains words the user did not write: "${part.slice(0, 60)}". Copy the user's own words exactly.`,
      );
  }
  for (const q of intake.questions) {
    const answer = collapse(q.answer);
    if (answer === "unknown" || answer === "") continue;
    if (!haystack.includes(answer))
      problems.push(
        `${q.id}: the answer is not the user's own words: "${answer.slice(0, 60)}". Copy the user's answer exactly, or write unknown.`,
      );
  }
  return problems;
}

/** The text of every user message, for verification. */
export function userTextsOf(
  messages: { role?: unknown; parts?: unknown }[],
): string[] {
  const texts: string[] = [];
  for (const m of messages) {
    if (m.role !== "user" || !Array.isArray(m.parts)) continue;
    for (const p of m.parts as { type?: unknown; text?: unknown }[]) {
      if (p?.type === "text" && typeof p.text === "string") texts.push(p.text);
    }
  }
  return texts;
}
