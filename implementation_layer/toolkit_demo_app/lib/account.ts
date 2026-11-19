// What the header's account menu shows about the signed-in user: who they are,
// which avatar is theirs and what they can run. Kept free of Supabase and Redis
// imports, so the mapping can be tested on its own.

/**
 * Approved, the daily trial, waiting, e-mail not confirmed, declined, no access
 * request at all (its insert at sign-up failed), or local development.
 */
export type AccountStatus =
  | "full"
  | "trial"
  | "pending"
  | "unconfirmed"
  | "rejected"
  | "norequest"
  | "bypass";

export interface Account {
  name: string;
  email: string | null;
  status: AccountStatus;
  /** 1 to AVATAR_COUNT: the user's picture is /avatars/avatar-N.webp. */
  avatar: number;
  /** Demo runs a day on the trial; set for status "trial". */
  trialRunsPerDay?: number;
}

/**
 * public/avatars holds avatar-1.webp to avatar-8.webp (GPT Image 2.6, docs/avatars.md).
 * Raising the count gives most users another avatar.
 */
export const AVATAR_COUNT = 8;

/** The same avatar for a user on every visit and device: a hash of the user id picks it. */
export function avatarIndex(userId: string): number {
  let hash = 0;
  for (const char of userId) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return (hash % AVATAR_COUNT) + 1;
}

/** "Ada Lovelace" gives "AL", "ada@example.com" gives "A": the avatar's stand-in. */
export function initials(name: string): string {
  const words = name
    .split("@")[0]
    .split(/[\s._-]+/)
    .filter(Boolean);
  const letters = words.length > 1 ? [words[0], words.at(-1)!] : words;
  return letters.map((word) => word[0]!.toUpperCase()).join("") || "?";
}

/** The part of the access state (lib/queries/access.ts) the menu reads. */
export interface AccountSource {
  user: {
    id: string;
    email?: string | null;
    user_metadata?: { full_name?: unknown } | null;
  } | null;
  isUnlocked: boolean;
  isTrial: boolean;
  emailUnconfirmed: boolean;
  /** Told apart from pending: a declined request sets none of the flags above. */
  requestStatus?: "pending" | "approved" | "rejected" | null;
  bypassAuth: boolean;
}

/** The menu's account, or null for a visitor who is not signed in. */
export function accountOf(
  access: AccountSource,
  trialRunsPerDay: number,
): Account | null {
  if (access.bypassAuth && !access.user)
    return {
      name: "Local development",
      email: null,
      status: "bypass",
      avatar: 1,
    };
  const { user } = access;
  if (!user) return null;
  const fullName = user.user_metadata?.full_name;
  const email = user.email ?? null;
  const name =
    typeof fullName === "string" && fullName.trim()
      ? fullName.trim()
      : (email ?? "Your account");
  const status: AccountStatus = access.isUnlocked
    ? "full"
    : access.requestStatus === "rejected"
      ? "rejected"
      : access.requestStatus === null
        ? "norequest"
        : access.isTrial
          ? "trial"
          : access.emailUnconfirmed
            ? "unconfirmed"
            : "pending";
  return {
    name,
    email,
    status,
    avatar: avatarIndex(user.id),
    ...(status === "trial" ? { trialRunsPerDay } : {}),
  };
}

/** One line on what the account can do now. */
export function statusLine(account: Account): string {
  switch (account.status) {
    case "full":
      // Not "full access": the first wizard in the browser is a grant of its own.
      return "Account approved";
    case "trial":
      return `Trial: ${account.trialRunsPerDay ?? 0} demo runs a day`;
    case "unconfirmed":
      return "Confirm your e-mail address to start";
    case "pending":
      return "Waiting for approval";
    case "rejected":
      return "Your access request was declined";
    case "norequest":
      return "No access request on file";
    case "bypass":
      return "Sign-in is bypassed (BYPASS_AUTH)";
  }
}
