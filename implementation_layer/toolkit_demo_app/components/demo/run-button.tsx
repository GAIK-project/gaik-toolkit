"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Loader2, type LucideIcon, Square } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

type ButtonProps = ComponentProps<typeof Button>;

/**
 * A demo's run button that becomes its Stop button while the run is going.
 *
 * A run shows one progress indicator. Where the page has a progress panel of its
 * own, the button shows a stop square, not a second spinner. Where the button
 * is the run's only sign of progress, `spinner` keeps a spinner beside "Stop".
 * Stopping cancels the request in the browser and returns the page to ready
 * with its input kept; a step the server is already running may still finish
 * there. A run that must not be stopped, because the server would go on and a
 * retry would clash with it (indexing into a collection, a query on a shared
 * connection), passes no `onStop`: the button then stays disabled while it runs.
 */
export function RunButton({
  running,
  onRun,
  onStop,
  icon: Icon,
  children,
  spinner = false,
  disabled,
  className,
  size = "lg",
  variant,
}: {
  running: boolean;
  onRun: () => void;
  /** Leave out for a run that must not be stopped. */
  onStop?: () => void;
  /** The icon beside the label when idle. */
  icon?: LucideIcon;
  /** The label when idle, such as "Extract data". */
  children: ReactNode;
  /** The button is the run's only progress indicator. */
  spinner?: boolean;
  /** Disables the run, never the stop. */
  disabled?: boolean;
  className?: string;
  size?: ButtonProps["size"];
  variant?: ButtonProps["variant"];
}) {
  if (running && !onStop)
    return (
      <Button
        type="button"
        variant={variant}
        size={size}
        disabled
        className={className}
      >
        {spinner ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : Icon ? (
          <Icon className="size-4" aria-hidden />
        ) : null}
        {children}
      </Button>
    );
  if (running)
    return (
      <Button
        type="button"
        variant="outline"
        size={size}
        onClick={onStop}
        className={cn(
          "transition-[background-color,scale] active:scale-[0.98]",
          className,
        )}
      >
        {spinner ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Square className="size-3.5 fill-current" aria-hidden />
        )}
        Stop
      </Button>
    );
  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      onClick={onRun}
      disabled={disabled}
      className={cn(
        "transition-[background-color,scale] active:scale-[0.98]",
        className,
      )}
    >
      {Icon ? <Icon className="size-4" aria-hidden /> : null}
      {children}
    </Button>
  );
}
