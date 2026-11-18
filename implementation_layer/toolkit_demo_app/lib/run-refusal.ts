// Why the demo pages hold a run, in the words the page shows. The proxy's rule
// is in lib/api-access.ts (accessRefusal); these texts follow it.

import type { ModelUse } from "./model-use";

/** Why a visitor cannot run a demo now. */
export type RunRefusal = "sign-in" | "confirm-email" | "approval";

export function runRefusal({
  loggedIn,
  emailUnconfirmed,
}: {
  loggedIn: boolean;
  /** Pending approval and the sign-in e-mail address is not confirmed yet. */
  emailUnconfirmed: boolean;
}): RunRefusal {
  if (!loggedIn) return "sign-in";
  return emailUnconfirmed ? "confirm-email" : "approval";
}

/** The access notice's sentence after "View only." */
export function accessNoticeText(reason: RunRefusal): string {
  switch (reason) {
    case "sign-in":
      return "Sign in to run this demo.";
    case "confirm-email":
      return "Confirm your e-mail address to run demos: open the link we sent you.";
    case "approval":
      return "Your access is pending approval, so running demos is off for now.";
  }
}

/** The label of the disabled run button. */
export function runBlockedLabel(reason: RunRefusal): string {
  switch (reason) {
    case "sign-in":
      return "Sign in to run";
    case "confirm-email":
      return "Confirm your e-mail to run";
    case "approval":
      return "Waiting for approval";
  }
}

/** The model notice's line when an own key is saved but runs are refused. */
export function ownKeyHeldText(reason: RunRefusal): string {
  switch (reason) {
    case "sign-in":
      return "Your own key is saved, but it runs no demo until you sign in.";
    case "confirm-email":
      return "Your own key is saved, but it runs no demo until you confirm your e-mail address.";
    case "approval":
      return "Your own key is saved, but it runs no demo until your account is approved.";
  }
}

/**
 * The model notice for a saved own key while the proxy refuses this account's
 * runs: the key runs nothing here, so the notice says why instead of naming it
 * as the model that runs the demo. A server model's notice stays as it is.
 */
export function heldOwnKeyUse(
  use: ModelUse,
  own: boolean,
  reason: RunRefusal | null,
): ModelUse {
  if (!own || !reason) return use;
  return {
    runsHere: false,
    summary: ownKeyHeldText(reason),
    details: [],
    problem: null,
  };
}
