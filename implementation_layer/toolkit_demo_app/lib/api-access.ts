// Which proxied backend requests need a signed-in, approved user.
//
// Anything that is not a read can change state or cost money: POST runs the
// heavy endpoints, and DELETE clears data (DELETE /video-search/clear empties
// the video_segments table). Gating only POST left the DELETE routes open to
// anonymous callers, so the gate keys on the method being a read, not on POST.

const READ_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function isStateChanging(method: string): boolean {
  return !READ_METHODS.has(method.toUpperCase());
}

/**
 * `ownModelKey` is true when the request carries the user's own model key for a
 * route that supports it. That call runs on the user's credential, so it does not
 * need a signed-in, approved account.
 */
export function needsApprovedUser(
  method: string,
  pathname: string,
  ownModelKey = false,
): boolean {
  // The wizard API has its own gate, including the team-key path.
  return (
    isStateChanging(method) &&
    !pathname.startsWith("/api/wizard") &&
    !ownModelKey
  );
}

export interface GateState {
  loggedIn: boolean;
  approved: boolean;
  /** Waiting for approval: may run on the trial allowance (lib/trial.ts). */
  pending: boolean;
  userId: string | null;
}

export interface Refusal {
  status: number;
  error: string;
}

export const PENDING_DENIAL: Refusal = {
  status: 403,
  error: "Your access is pending approval.",
};

/**
 * Why a request that needs an account is refused, or null when it may run.
 * An approved user runs freely; a pending one spends a trial run.
 */
export async function accessRefusal(
  state: GateState,
  takeTrialRun: (
    userId: string,
  ) => Promise<{ ok: true } | ({ ok: false } & Refusal)>,
): Promise<Refusal | null> {
  if (!state.loggedIn)
    return { status: 401, error: "Sign in to use this feature." };
  if (state.approved) return null;
  if (!state.pending || !state.userId) return PENDING_DENIAL;
  const trial = await takeTrialRun(state.userId);
  return trial.ok ? null : { status: trial.status, error: trial.error };
}
