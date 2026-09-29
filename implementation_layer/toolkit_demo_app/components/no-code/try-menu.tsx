"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { launch } from "@/lib/no-code/catalog";
import { ChevronDown, Copy } from "lucide-react";
import toast from "react-hot-toast";
import { ClaudeIcon, CursorIcon } from "./provider-icons";

/**
 * Where a skill's try-prompt can open. Every target only pre-fills the prompt;
 * nothing is sent until the person presses Enter in that app.
 */
export function TryMenu({
  prompt,
  variant,
}: {
  prompt: string;
  variant: "desktop" | "agent";
}) {
  const targets =
    variant === "desktop"
      ? [
          {
            label: "Claude Desktop",
            hint: "Opens a new chat",
            href: launch.claude(prompt),
            icon: ClaudeIcon,
          },
        ]
      : [
          {
            label: "Claude Code on the web",
            hint: "Opens in this browser",
            href: launch.claudeCodeWeb(prompt),
            icon: ClaudeIcon,
            external: true,
          },
          {
            label: "Claude Desktop",
            hint: "Code tab in the app",
            href: launch.claudeDesktopCode(prompt),
            icon: ClaudeIcon,
          },
          {
            label: "Claude Code terminal",
            hint: "Needs Claude Code installed",
            href: launch.claudeCode(prompt),
            icon: ClaudeIcon,
          },
          {
            label: "Cursor",
            hint: "Agent chat in the app",
            href: launch.cursor(prompt),
            icon: CursorIcon,
          },
        ];

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt);
      toast.success("Prompt copied");
    } catch {
      toast.error("Could not copy. Select the text and copy it by hand.");
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          Try it
          <ChevronDown />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {targets.map(({ label, hint, href, icon: Icon, ...rest }) => (
          <DropdownMenuItem key={label} asChild className="items-start gap-3">
            <a
              href={href}
              {...("external" in rest
                ? { target: "_blank", rel: "noopener noreferrer" }
                : {})}
            >
              <Icon className="mt-0.5 size-4" />
              <span className="flex flex-col">
                {label}
                <span className="text-muted-foreground text-xs">{hint}</span>
              </span>
            </a>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={copy} className="gap-3">
          <Copy className="size-4" />
          Copy prompt
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
