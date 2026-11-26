// What a failed sign-in tells the user, and how it is logged.
//
// Supabase checks the password before it checks a ban, so `user_banned` only
// reaches someone who typed the right password: naming it reveals nothing to a
// guesser, and it stops an expired temporary account from looking like a typo.

export function signInErrorMessage(code: string | undefined): string {
  switch (code) {
    case "email_not_confirmed":
      return "Confirm your e-mail address first: open the link we sent you, then sign in.";
    case "user_banned":
      return "This account has expired or been disabled. Contact the GAIK team to reopen it.";
    default:
      return "Invalid email or password.";
  }
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
): void {
  console.warn(
    `[auth] sign-in failed: ${code ?? "unknown"} for ${maskEmail(email)}`,
  );
}
