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

/** True for a request that needs a signed-in account (see `accessRefusal`). */
export function needsApprovedUser(method: string): boolean {
  return isStateChanging(method);
}

/** The first Solution Wizard's API: the paths under /api/wizard. */
export function isWizardApiPath(pathname: string): boolean {
  return pathname === "/api/wizard" || pathname.startsWith("/api/wizard/");
}

/** The backend header that names the user a wizard session belongs to. */
export const WIZARD_USER_HEADER = "x-gaik-wizard-user";

/**
 * Why a first-wizard request is refused, or null when it may go on. Its agent
 * has shell tools and runs in the demo API pod, so approval is not enough: an
 * admin grants the wizard to each user (`wizard_access`, set in /admin). This
 * holds for reads too, since they list and download a session's files. A
 * request that changes state also meets `accessRefusal`.
 */
export function wizardRefusal(state: {
  loggedIn: boolean;
  wizardAccess: boolean;
}): Refusal | null {
  if (!state.loggedIn)
    return { status: 401, error: "Sign in to use this feature." };
  if (!state.wizardAccess)
    return {
      status: 403,
      error: "The first wizard in the browser needs access from the GAIK team.",
    };
  return null;
}

export interface GateState {
  loggedIn: boolean;
  approved: boolean;
  /** Waiting for approval: may run on the trial allowance (lib/trial.ts). */
  pending: boolean;
  /** The sign-in e-mail address is confirmed; trial runs need it. */
  emailConfirmed: boolean;
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

export const EMAIL_UNCONFIRMED: Refusal = {
  status: 403,
  error: "Confirm your e-mail address to use the trial runs.",
};

/** Whether a Supabase user has confirmed their e-mail address. */
export function isEmailConfirmed(
  user: { email_confirmed_at?: string | null } | null | undefined,
): boolean {
  return !!user?.email_confirmed_at;
}

/**
 * Why a request that needs an account is refused, or null when it may run.
 * An approved user runs freely; a pending one with a confirmed e-mail address
 * spends a trial run, unless the request runs on their own model key
 * (`ownModelKey`), which needs the account but no trial run.
 */
export async function accessRefusal(
  state: GateState,
  takeTrialRun: (
    userId: string,
  ) => Promise<{ ok: true } | ({ ok: false } & Refusal)>,
  ownModelKey = false,
): Promise<Refusal | null> {
  if (!state.loggedIn)
    return { status: 401, error: "Sign in to use this feature." };
  if (state.approved) return null;
  if (!state.pending || !state.userId) return PENDING_DENIAL;
  if (ownModelKey) return null;
  if (!state.emailConfirmed) return EMAIL_UNCONFIRMED;
  const trial = await takeTrialRun(state.userId);
  return trial.ok ? null : { status: trial.status, error: trial.error };
}
