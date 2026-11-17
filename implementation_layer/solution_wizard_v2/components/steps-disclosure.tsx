"use client";

import { useState, type ReactNode } from "react";
import { Icon } from "./icons";

/**
 * The timeline on a screen too narrow for the gate row of the session bar:
 * the step line opens it under the step's title. It is rendered only while
 * open, so the page never holds a second copy of the timeline.
 */
export function StepsDisclosure({
  summary,
  children,
  besideButton = true,
}: {
  /** "Step 1/13", the line that opens it. */
  summary: string;
  children: ReactNode;
  /** The chat button shares the summary's line, so the list opens below it.
   *  False where the line stands alone (the chat is the page). */
  besideButton?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        // The way to the stages on a phone: a button with an edge, not a
        // line of grey text. Small beside the title, pressed from 44 px:
        // pointer-coarse:min-h-7 overrides btn-inline's touch min-h-11, and
        // hit-area gives the 44 px around it.
        className="btn-inline hit-area min-h-7 gap-1 px-2 py-0.5 font-normal pointer-coarse:min-h-7"
        data-testid="steps-disclosure"
      >
        {summary}
        <Icon
          name="chevronDown"
          size={12}
          className={`transition-transform duration-150 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
        />
      </button>
      {/* Opens below the chat button that shares the line with the summary. */}
      {open && <div className={`mb-2 max-w-sm ${besideButton ? "mt-7" : "mt-2"}`}>{children}</div>}
    </div>
  );
}
