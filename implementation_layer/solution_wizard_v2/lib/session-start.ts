/**
 * The start of a session. While the wizard gathers requirements the session
 * happens in the chat, and with the live agent the workspace has nothing of
 * its own to show before the specification: it held one paragraph that sent
 * the reader to the chat beside it. There the chat is the page instead, and an
 * empty one opens with a question, the field and a few examples to start from.
 */

/** The steps before the specification: session start and requirements gathering. */
const LAST_CHAT_ONLY_STEP = 2;

/**
 * True while the chat is the page's main content. The mock store keeps a
 * checklist for these steps (`points`), which is a view of its own, so there
 * the chat stays docked beside it.
 *
 * The step alone does not say it. A session can stand on these steps with
 * requirements already gathered (it was stepped back from Gate 1, and the
 * wizard's files do not move it on again): the wizard then asks for Gate 1's
 * approval "in the panel", and a page that was only the chat had no panel. So
 * the chat leads only while there is nothing to review (`gathered`: the
 * wizard has recorded no business context, assumption or output field), and
 * never while a gate waits for the user's decision (`gateWaiting`).
 */
export function chatLeads(
  step: number,
  points: readonly string[],
  { gathered = false, gateWaiting = false }: { gathered?: boolean; gateWaiting?: boolean } = {},
): boolean {
  return step <= LAST_CHAT_ONLY_STEP && points.length === 0 && !gathered && !gateWaiting;
}

/** The example whose prompt the field holds as it was picked, if any. */
export function exampleIn(input: string, prompts: readonly string[]): number | null {
  const text = input.trim();
  if (!text) return null;
  const at = prompts.findIndex((prompt) => prompt.trim() === text);
  return at < 0 ? null : at;
}

/**
 * Examples are a way to start an empty field. Once the user has written words
 * of their own, an example would replace them, so none is offered.
 */
export function examplesOffered(input: string, prompts: readonly string[]): boolean {
  return input.trim() === "" || exampleIn(input, prompts) !== null;
}

/**
 * The field after an example is pressed: it holds the example's prompt and
 * nothing else, in place of another example; pressing the one already there
 * empties it again. Words the user wrote themselves are left as they are.
 */
export function toggleExample(input: string, prompt: string, prompts: readonly string[]): string {
  if (!examplesOffered(input, prompts)) return input;
  const current = exampleIn(input, prompts);
  const same = current !== null && prompts[current].trim() === prompt.trim();
  return same ? "" : prompt;
}
