"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { installTabs } from "@/lib/no-code/catalog";
import type { ComponentType, SVGProps } from "react";
import { CopyIconButton } from "./actions";
import { ClaudeIcon, CodexIcon, CopilotIcon } from "./provider-icons";

const marks: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
  "claude-desktop": ClaudeIcon,
  "claude-code": ClaudeIcon,
  codex: CodexIcon,
  copilot: CopilotIcon,
};

/** One tab per client: what to paste, a copy control per line, and where it goes. */
export function InstallPlugin() {
  return (
    <Tabs defaultValue={installTabs[0].id} className="gap-3">
      <TabsList className="w-full flex-wrap justify-start gap-1 bg-transparent p-0 group-data-[orientation=horizontal]/tabs:h-auto">
        {installTabs.map(({ id, name }) => {
          const Mark = marks[id];
          return (
            <TabsTrigger
              key={id}
              value={id}
              className="data-[state=active]:bg-muted h-12 flex-none gap-2 rounded-lg px-3 data-[state=active]:shadow-none"
            >
              {Mark && <Mark className="size-4" />}
              {name}
            </TabsTrigger>
          );
        })}
      </TabsList>
      {installTabs.map(({ id, lines, copyLabel, note }) => (
        <TabsContent key={id} value={id} className="max-w-2xl">
          <ul className="bg-card divide-y rounded-lg border">
            {lines.map((line) => (
              <li key={line} className="flex items-center gap-2 py-1 pr-1 pl-4">
                <code className="min-w-0 flex-1 py-1.5 font-mono text-sm break-words">
                  {line}
                </code>
                <CopyIconButton text={line} label={copyLabel} />
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-2 text-sm">{note}</p>
        </TabsContent>
      ))}
    </Tabs>
  );
}
