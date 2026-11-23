"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { type Account, initials, statusLine } from "@/lib/account";
import { GAIK_CONTACT_URL } from "@/lib/onboarding/mailto";
import { setModelSettings } from "@/lib/model-settings-store";
import { forgetServerModels } from "@/lib/server-model-store";
import { cn } from "@/lib/utils";
import { CircleUser, LogOut, Mail } from "lucide-react";
import Link from "next/link";

/**
 * Clears this browser's model settings and the server's model list for this user,
 * signs out and follows the API's redirect.
 */
export async function handleSignOut(): Promise<void> {
  setModelSettings(null);
  forgetServerModels();
  const res = await fetch("/api/auth/sign-out", { method: "POST" });
  const data = await res.json();
  if (data.redirectTo) {
    window.location.href = data.redirectTo;
  }
}

// A dot that says at a glance whether the account can run demos now.
const STATUS_DOT: Record<Account["status"], string> = {
  full: "bg-emerald-500",
  trial: "bg-primary",
  pending: "bg-amber-500",
  unconfirmed: "bg-amber-500",
  rejected: "bg-destructive",
  norequest: "bg-amber-500",
  bypass: "bg-muted-foreground",
};

function AccountAvatar({
  account,
  className,
}: {
  account: Account;
  className?: string;
}) {
  return (
    <Avatar className={className}>
      <AvatarImage src={`/avatars/avatar-${account.avatar}.webp`} alt="" />
      <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
        {initials(account.name)}
      </AvatarFallback>
    </Avatar>
  );
}

/**
 * The signed-in user's avatar in the header. It opens who is signed in, what
 * they can run, and sign-out. A user on the trial or waiting for approval also
 * gets the access status page, which explains both; it says nothing true for
 * an unconfirmed e-mail address or a declined request, so they do not. With a
 * declined request or none at all, the way on is the GAIK team.
 *
 * The name and address stay out of analytics: PostHog's autocapture records a
 * clicked element's text and attributes, so the trigger has a generic label and
 * both parts carry `ph-no-capture`.
 */
export function AccountMenu({ account }: { account: Account }) {
  const notApproved =
    account.status === "trial" || account.status === "pending";
  const askTeam =
    account.status === "rejected" || account.status === "norequest";
  // With BYPASS_AUTH there is no session to end.
  const canSignOut = account.status !== "bypass";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Account menu"
        className="ph-no-capture focus-visible:ring-ring/50 hover:ring-primary/30 data-[state=open]:ring-primary/40 rounded-full ring-2 ring-transparent transition-[box-shadow,scale] outline-none focus-visible:ring-[3px] active:scale-95"
      >
        <AccountAvatar account={account} className="size-8" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="ph-no-capture w-72">
        <DropdownMenuLabel className="flex items-center gap-3 py-2 font-normal">
          <AccountAvatar account={account} className="size-10" />
          <span className="min-w-0">
            <span className="block truncate font-medium">{account.name}</span>
            {account.email && account.email !== account.name ? (
              <span className="text-muted-foreground block truncate text-xs">
                {account.email}
              </span>
            ) : null}
          </span>
        </DropdownMenuLabel>
        <p className="text-muted-foreground flex items-center gap-2 px-2 pb-2 text-xs">
          <span
            aria-hidden
            className={cn(
              "size-2 shrink-0 rounded-full",
              STATUS_DOT[account.status],
            )}
          />
          {statusLine(account)}
        </p>
        {notApproved || askTeam || canSignOut ? (
          <DropdownMenuSeparator />
        ) : null}
        {notApproved ? (
          <DropdownMenuItem asChild>
            <Link href="/access-pending">
              <CircleUser className="size-4" />
              Access status
            </Link>
          </DropdownMenuItem>
        ) : null}
        {askTeam ? (
          <DropdownMenuItem asChild>
            <a
              href={GAIK_CONTACT_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Mail className="size-4" />
              Contact the GAIK team
            </a>
          </DropdownMenuItem>
        ) : null}
        {canSignOut ? (
          <DropdownMenuItem onSelect={() => void handleSignOut()}>
            <LogOut className="size-4" />
            Sign out
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
