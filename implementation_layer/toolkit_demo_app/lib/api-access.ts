// Which proxied backend requests need a signed-in, approved user.
//
// Anything that is not a read can change state or cost money: POST runs the
// heavy endpoints, and DELETE clears data (a RAG collection, a tabular-agent
// session). Gating only POST left the DELETE routes open to anonymous callers,
// so the gate keys on the method being a read, not on POST.
//
// A user waiting for approval runs on the daily trial (lib/trial.ts) or on their
// own model key, once their e-mail address is confirmed. Both cover a run on the
// user's own input, never a write to data that every visitor shares: that needs
// an approved user.

const READ_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function isStateChanging(method: string): boolean {
  return !READ_METHODS.has(method.toUpperCase());
}

/** True for a request that needs a signed-in account (see `accessRefusal`). */
export function needsApprovedUser(method: string): boolean {
  return isStateChanging(method);
}

// The video-search index is one table that every visitor searches. The API no
// longer serves a route that clears or writes it (the index is seeded with
// api/scripts/seed_dental_demo.py, and api/tests/test_video_search_router.py
// fails when the router gains one); this keeps such a route off the trial.
const SHARED_DATA_PATHS = [
  "/api/video-search/clear",
  "/api/video-search/ingest",
];

/** True for a write to data that every visitor shares: approved users only. */
export function writesSharedData(method: string, pathname: string): boolean {
  return (
    isStateChanging(method) &&
    SHARED_DATA_PATHS.some(
      (path) => pathname === path || pathname.startsWith(`${path}/`),
    )
  );
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
  /** The sign-in e-mail address is confirmed; a pending user's runs need it. */
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

export const SHARED_DATA_DENIAL: Refusal = {
  status: 403,
  error: "Only an approved account can change the shared demo data.",
};

export const EMAIL_UNCONFIRMED: Refusal = {
  status: 403,
  error: "Confirm your e-mail address to run demos.",
};

/** Whether a Supabase user has confirmed their e-mail address. */
export function isEmailConfirmed(
  user: { email_confirmed_at?: string | null } | null | undefined,
): boolean {
  return !!user?.email_confirmed_at;
}

export interface GatedRequest {
  /**
   * Runs on the user's own model key: spends no trial run, but a pending user
   * still needs a confirmed e-mail address.
   */
  ownModelKey?: boolean;
  /**
   * Is no demo run, such as ending a wizard session: spends no trial run. It
   * still needs the account.
   */
  noTrialRun?: boolean;
  /** Writes data that every visitor shares (`writesSharedData`). */
  sharedData?: boolean;
}

/**
 * Why a request that needs an account is refused, or null when it may run.
 * An approved user runs freely. A pending one with a confirmed e-mail address
 * spends a trial run, or none on their own model key (`ownModelKey`). A request
 * that is no demo run (`noTrialRun`) needs the pending account only. A visitor
 * who is not signed in, or an account that is neither approved nor pending, is
 * refused whatever the request carries. A write to shared data runs for an
 * approved user only.
 */
export async function accessRefusal(
  state: GateState,
  takeTrialRun: (
    userId: string,
  ) => Promise<{ ok: true } | ({ ok: false } & Refusal)>,
  {
    ownModelKey = false,
    noTrialRun = false,
    sharedData = false,
  }: GatedRequest = {},
): Promise<Refusal | null> {
  if (!state.loggedIn)
    return { status: 401, error: "Sign in to use this feature." };
  if (state.approved) return null;
  if (sharedData) return SHARED_DATA_DENIAL;
  if (!state.pending || !state.userId) return PENDING_DENIAL;
  if (noTrialRun) return null;
  if (!state.emailConfirmed) return EMAIL_UNCONFIRMED;
  if (ownModelKey) return null;
  const trial = await takeTrialRun(state.userId);
  return trial.ok ? null : { status: trial.status, error: trial.error };
}
