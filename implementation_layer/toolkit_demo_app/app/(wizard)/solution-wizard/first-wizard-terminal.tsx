"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

// The first wizard is a Claude Code skill in the repository's .claude/skills, so
// Claude Code started at the repository root offers /solution-wizard.
const SHELL_COMMANDS = [
  "git clone https://github.com/GAIK-project/gaik-toolkit.git",
  "cd gaik-toolkit && claude",
];
const CLAUDE_COMMAND = "/solution-wizard";

/** The commands that start the first wizard, with a copy button for the shell part. */
export function FirstWizardTerminal() {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(SHELL_COMMANDS.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard blocked: the commands stay selectable.
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-sm">
      <div className="flex items-center gap-1.5 border-b border-zinc-800 bg-zinc-900 py-1.5 pr-1.5 pl-3.5">
        <span aria-hidden className="size-2.5 rounded-full bg-zinc-700" />
        <span aria-hidden className="size-2.5 rounded-full bg-zinc-700" />
        <span aria-hidden className="size-2.5 rounded-full bg-zinc-700" />
        <span className="ml-2 flex-1 text-xs text-zinc-400">terminal</span>
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? "Commands copied" : "Copy the commands"}
          title="Copy the commands"
          className="rounded-md p-1.5 text-zinc-400 transition-[color,background-color,scale] hover:bg-zinc-800 hover:text-zinc-100 active:scale-95"
        >
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
        </button>
      </div>
      <pre className="px-4 py-3.5 font-mono text-[13px] leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap">
        {SHELL_COMMANDS.map((command) => (
          <code key={command} className="block text-zinc-100">
            <span aria-hidden className="text-teal-400 select-none">
              ${" "}
            </span>
            {command}
          </code>
        ))}
        <code className="mt-2 block text-zinc-100">
          <span aria-hidden className="text-[#D97757] select-none">
            &gt;{" "}
          </span>
          {CLAUDE_COMMAND}
          <span className="ml-3 text-zinc-500 select-none">in Claude Code</span>
        </code>
      </pre>
    </div>
  );
}
