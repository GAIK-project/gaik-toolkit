"use client";

import {
  ClaudeIcon,
  CodexIcon,
  CursorIcon,
} from "@/components/no-code/provider-icons";
import { ONBOARD_PROMPT } from "@/lib/agent-setup";
import { Bot, Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

// Codex in its brand blue (devicon): the black mark reads as a blot at this size.
const marks = [
  { Mark: ClaudeIcon, className: "" },
  { Mark: CodexIcon, className: "text-[#5061f7]" },
  { Mark: CursorIcon, className: "" },
];

/**
 * Copies a one-line prompt that has a coding agent (Claude Code, Codex, Cursor,
 * VS Code) install gaik, the GAIK MCP server and the agent skills. When the
 * clipboard is blocked, the prompt is shown to copy by hand.
 */
export function OnboardAgent() {
  const [state, setState] = useState<"idle" | "copied" | "blocked">("idle");

  useEffect(() => {
    if (state !== "copied") return;
    const timer = setTimeout(() => setState("idle"), 2500);
    return () => clearTimeout(timer);
  }, [state]);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(ONBOARD_PROMPT);
      setState("copied");
    } catch {
      setState("blocked");
    }
  }

  const copied = state === "copied";

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <button
        type="button"
        onClick={copy}
        title={ONBOARD_PROMPT}
        aria-label={
          copied
            ? "Copied. Paste it to your coding agent"
            : "Onboard your agent: copy a prompt that sets up GAIK in your coding agent"
        }
        className="group bg-background/70 hover:border-primary/40 focus-visible:ring-ring/50 inline-flex h-11 w-fit items-center gap-2.5 rounded-full border py-1 pr-3.5 pl-1.5 text-sm font-medium shadow-sm transition-colors outline-none focus-visible:ring-[3px]"
      >
        {copied ? (
          <span className="bg-primary/10 text-primary flex size-7 items-center justify-center rounded-full">
            <Bot className="size-4" aria-hidden />
          </span>
        ) : (
          <span className="flex -space-x-1.5" aria-hidden>
            {marks.map(({ Mark, className }, index) => (
              <span
                key={index}
                className="bg-background ring-background flex size-7 items-center justify-center rounded-full border ring-2"
              >
                <Mark className={`size-4 ${className}`} />
              </span>
            ))}
          </span>
        )}
        <span aria-live="polite">
          {copied ? "Paste to your agent" : "Onboard your agent"}
        </span>
        {copied ? (
          <Check className="text-primary size-4" aria-hidden />
        ) : (
          <Copy
            className="text-muted-foreground group-hover:text-foreground size-4 transition-colors"
            aria-hidden
          />
        )}
      </button>
      {state === "blocked" && (
        <p className="text-muted-foreground max-w-md text-xs">
          Copy this to your coding agent:{" "}
          <code className="text-foreground bg-muted rounded px-1 py-0.5 break-words select-all">
            {ONBOARD_PROMPT}
          </code>
        </p>
      )}
    </div>
  );
}
