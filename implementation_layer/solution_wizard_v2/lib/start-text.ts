/**
 * The words the start view sends: what its state holds, or, when that is
 * still empty, what the field itself shows. Text typed (or pasted) before the
 * page had finished loading is in the field but never reached the state, and
 * the send button then did nothing although the words were on screen.
 */
export function startText(state: string, fieldValue: string | null | undefined): string {
  return state.trim() || (fieldValue ?? "").trim();
}
