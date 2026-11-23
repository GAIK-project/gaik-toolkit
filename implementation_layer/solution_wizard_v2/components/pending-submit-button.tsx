"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { Icon, type IconName } from "./icons";

// A submit button that says what it is doing. The step and gate actions take
// 20–60 s when the agent is busy on the same session (#170); a plain button
// gave no sign that the click registered, so people clicked again.
export function PendingSubmitButton({
  label,
  pendingLabel,
  className,
  disabled = false,
  title,
  icon,
  iconAfter = false,
  describedBy,
}: {
  /** The label, and the one shown while the action runs. A node lets a narrow
   *  layout keep part of it for screen readers only. */
  label: ReactNode;
  pendingLabel: ReactNode;
  className: string;
  disabled?: boolean;
  /** Says why the button is disabled, where that is not obvious. */
  title?: string;
  /** Drawn beside the label; a spinner takes its place while pending. */
  icon?: IconName;
  /** Put the icon after the label (forward), not before it (back, confirm). */
  iconAfter?: boolean;
  /** Id of the text that says what the button leads to. */
  describedBy?: string;
}) {
  const { pending } = useFormStatus();
  const glyph = pending ? (
    <Icon name="loaderCircle" size={16} className="animate-spin" />
  ) : icon ? (
    <Icon name={icon} size={16} />
  ) : null;
  return (
    <button
      type="submit"
      title={title}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      aria-describedby={describedBy}
      aria-live="polite"
      className={className}
    >
      {!iconAfter && glyph}
      {pending ? pendingLabel : label}
      {iconAfter && glyph}
    </button>
  );
}
