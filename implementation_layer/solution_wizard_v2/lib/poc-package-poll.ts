/**
 * When the PoC tab re-reads the package by itself.
 *
 * The agent writes the package during its turns, and nothing told the tab: it
 * read the file list once, when opened, so a package that finished after that
 * stayed "not ready" with the sandbox run disabled and no preflight until the
 * page was reloaded (UC01, round 11, 6 Oct 2026). An open tab now asks again:
 * often while the package is being written, now and then once it is ready,
 * because the agent rewrites a ready package too, and a new version is what
 * starts a new preflight.
 *
 * Not while a run is being followed (its last frame re-reads the package
 * anyway), and not in a hidden tab.
 */
export const WRITING_POLL_MS = 4_000;
export const READY_POLL_MS = 15_000;

export function pocPollDelay(input: {
  onPocTab: boolean;
  visible: boolean;
  ready: boolean;
  runActive: boolean;
}): number | null {
  if (!input.onPocTab || !input.visible || input.runActive) return null;
  return input.ready ? READY_POLL_MS : WRITING_POLL_MS;
}
