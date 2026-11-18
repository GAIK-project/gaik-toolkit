/**
 * Sends a message through the chat from elsewhere on the page: `detail` is the
 * message text. It goes through the same chat turn as a typed message, without
 * passing through the field, so the page has no second path to the backend.
 * The form for what Gate 1 lacks sends its answers this way (components/use-page-send).
 */
export const CHAT_SEND_EVENT = "gaik-wizard:chat-send";

/**
 * A message from CHAT_SEND_EVENT that never reached the agent: the wizard
 * stayed busy with another turn, or the request failed before it started.
 * `detail` is the message text, so its sender can offer it again.
 */
export const CHAT_SEND_FAILED_EVENT = "gaik-wizard:chat-send-failed";

/**
 * A message from CHAT_SEND_EVENT that the agent has started on: `detail` is
 * the message text. Until then its sender keeps it, to offer it again.
 */
export const CHAT_SEND_DELIVERED_EVENT = "gaik-wizard:chat-send-delivered";

/**
 * The wizard started or finished a reply: `detail` is true while one is on
 * its way. The PoC tab waits for the end of a reply before it starts a test
 * run, since the wizard may still be writing the package.
 */
export const CHAT_REPLYING_EVENT = "gaik-wizard:chat-replying";

/**
 * The deployable package is about to be downloaded by a link outside the PoC
 * tab (the finished solution's banner). Cancelable: the PoC tab cancels it
 * when values for the package's .env are typed there, and downloads the
 * package with them itself, so every download carries what was typed.
 */
export const DEPLOYABLE_DOWNLOAD_EVENT = "gaik-wizard:deployable-download";

/**
 * A message waiting for the chat panel to send it: one from CHAT_SEND_EVENT,
 * or the first message of a session started from the start view.
 */
export type QueuedMessage = {
  id: number;
  text: string;
  /** The user typed it: when it never reaches the wizard it goes back into the field. */
  restoreOnFail?: boolean;
};

/**
 * Opens the chat with a reference to one thing on the page (a blueprint step,
 * a gate, a requirement point, an assumption) shown as a removable chip above
 * the composer, and puts the cursor in the input. Nothing is sent until the
 * user writes and sends; the message then starts with `prefix` on its own
 * line, followed by what the user wrote. One composer for every "change this"
 * on the page, so nothing has a second input field that sends to the chat.
 */
export const CHAT_REFERENCE_EVENT = "gaik-wizard:chat-reference";

export type ChatReference = {
  /** The item's stable key ("step:classify", "gate:9", "requirement:3"): a new reference with the same key replaces the chip instead of adding one. */
  key: string;
  /** Short chip label in the UI language, e.g. "Vaihe 3 · Classification". */
  label: string;
  /**
   * The line the message starts with. Text written by the agent or taken from
   * a file goes in as a marked quote built with quoteOneLine (lib/chat-template),
   * e.g. 'Koskee prosessin vaihetta 3 (id classify), lainattuna: "Classification"'.
   */
  prefix: string;
  /** Optional words put into the composer for the user to finish. */
  draft?: string;
};

/** Opens the chat with `reference` (see CHAT_REFERENCE_EVENT). */
export function askInChat(reference: ChatReference): void {
  window.dispatchEvent(new CustomEvent<ChatReference>(CHAT_REFERENCE_EVENT, { detail: reference }));
}

/**
 * "Show me" under the wizard's reply that asks for a gate approval: the gate's
 * decision bar scrolls into view and marks its approve button for a moment.
 * The bar carries GATE_BAR_ATTRIBUTE, so the chat can tell whether there is
 * one on the page to point at.
 */
export const GATE_POINT_EVENT = "gaik-wizard:gate-point";

/**
 * Shows one place in the workspace from elsewhere on the page: `detail` is
 * the place. "test-run" opens the PoC tab and puts the focus on its run
 * button (the notice of an approval refused because the package changed).
 */
export const WORKSPACE_SHOW_EVENT = "gaik-wizard:workspace-show";
export type WorkspacePlace = "test-run";
export const GATE_BAR_ATTRIBUTE = "data-gate-bar";
