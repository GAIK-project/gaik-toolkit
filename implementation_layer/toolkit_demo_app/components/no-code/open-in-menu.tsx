"use client";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { launch } from "@/lib/no-code/catalog";
import { ChevronDown } from "lucide-react";
import { ClaudeIcon, CursorIcon } from "./provider-icons";

/**
 * Where a coding-agent prompt can open. Every target only pre-fills the prompt;
 * nothing is sent until the person presses Enter in that app.
 */
export function OpenInMenu({ prompt }: { prompt: string }) {
  const targets = [
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

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          Try in
          <ChevronDown />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {targets.map(({ label, hint, href, icon: Icon, external }) => (
          <DropdownMenuItem key={label} asChild className="items-start gap-3">
            <a
              href={href}
              {...(external
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
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
