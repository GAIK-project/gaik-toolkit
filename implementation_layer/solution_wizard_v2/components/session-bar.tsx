import type { ReactNode } from "react";

/**
 * The slim bar at the top of a session: its name, which is the page's
 * heading, and beside it the four gates of the wizard's process. Below the
 * desktop layout its left end is kept clear for the button that opens the
 * sidebar. Where the chat opens as a sheet over the workspace (768 to 1279 px)
 * the bar stands above it: a stage's panel hangs from the bar and has to be
 * readable with the chat open. The sheet starts under the bar, so the bar
 * covers nothing of it; the drawer and its button stay above both.
 */
export function SessionBar({
  title,
  children,
  className = "",
}: {
  /** The session's name, or a link back to the session from a page under it. */
  title: ReactNode;
  /** The gate row (components/gate-timeline). */
  children?: ReactNode;
  /** How the bar arrives when a session opens (the session page's "session-in"). */
  className?: string;
}) {
  return (
    <div
      data-testid="session-bar"
      className={`relative z-20 md:max-xl:z-[31] flex h-12 shrink-0 items-center gap-4 border-b border-border bg-surface pl-14 pr-4 sm:pr-6 lg:pl-6 ${className}`}
    >
      {/* A name cut short by the bar's width is read in full from its title. */}
      <h1
        title={typeof title === "string" ? title : undefined}
        className="min-w-0 truncate text-sm font-semibold text-text max-md:flex-1 md:max-w-[40%]"
      >
        {title}
      </h1>
      {children}
    </div>
  );
}
