// What a failed sign-in tells the user, and how it is logged.
//
// Supabase checks a ban before the password, so naming `user_banned` tells
// anyone who types that address that the account exists and has expired. That
// is accepted: sign-up already says when an address is registered, and the
// clear message stops an expired temporary account from looking like a typo.

export function signInErrorMessage(
  code: string | undefined,
  status?: number,
): string {
  switch (code) {
    case "email_not_confirmed":
      return "Confirm your e-mail address first: open the link we sent you, then sign in.";
    case "user_banned":
      return "This account has expired or been disabled. Contact the GAIK team to reopen it.";
    case "over_request_rate_limit":
      return "Too many sign-in attempts. Wait a minute and try again.";
  }
  // No code, or a 5xx: the sign-in service did not answer, the password was not checked.
  if (status === undefined || status === 0 || status >= 500)
    return "Sign-in is not available right now. Try again in a moment.";
  return "Invalid email or password.";
}

/** `gaik-testi@example.com` → `ga***@example.com`: enough to tell accounts apart in a log. */
export function maskEmail(email: string): string {
  const at = email.lastIndexOf("@");
  if (at < 1) return "***";
  return `${email.slice(0, Math.min(2, at))}***${email.slice(at)}`;
}

/** One log line per failed sign-in: the reason and a masked address, never the password. */
export function logSignInFailure(
  email: string,
  code: string | undefined,
  status?: number,
): void {
  console.warn(
    `[auth] sign-in failed: ${code ?? "unknown"}${status ? ` (${status})` : ""} for ${maskEmail(email)}`,
  );
}
