// Requirement model — the questions the wizard gathers before Gate 1, plus the
// agent's phrasing around them.
//
// In production this comes from the backend (wizard_api / the V1 agent's
// requirement model — the Section-9 completeness check). This module is the mock
// backend's stand-in: the points ride on a session as `requirements.points` and
// the questions reach the UI as chat messages. They live in the data/backend
// layer, NOT hardcoded in a view or in i18n, so the frontend only renders what
// the backend provides. When wizard_api exposes them, this is what it replaces.
//
// Single language by design: like real agent output, the conversation is in one
// language, not switched by the UI locale.

export const REQUIREMENT_POINTS: string[] = [
  "What task should the system support?",
  "Who will use the system?",
  "What input artifacts will the system receive?",
  "What output should the system produce?",
  "Which fields, sections, or answer types are required?",
  "What language is used in the input and output?",
  "Is domain-specific vocabulary needed?",
  "Does the use case require human review?",
  "Are there privacy, security, or compliance constraints?",
  "Should the solution use a specific model provider?",
  "Should the output be integrated into another system?",
  "How should quality be evaluated?",
  "What should the first PoC demonstrate?",
];

/** The agent's opening message: a short lead-in plus the first question. */
export function openingQuestion(points: string[] = REQUIREMENT_POINTS): string {
  return `Let's map out the requirements with a few questions. First: ${points[0]}`;
}

/**
 * The agent's reply after an answer: acknowledge and ask the next question, or
 * wrap up once every point is gathered. `answeredCount` is how many answers are
 * now recorded, so the next question is `points[answeredCount]`.
 */
export function nextQuestion(points: string[], answeredCount: number): string {
  if (answeredCount >= points.length) {
    return "All requirements are gathered. You can review and approve them at Gate 1.";
  }
  return `Thanks, noted! Next: ${points[answeredCount]}`;
}
