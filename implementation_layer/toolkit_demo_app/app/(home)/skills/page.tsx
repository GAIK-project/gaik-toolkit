import { CodeBlock } from "@/components/code-block";
import { NoCodeHeader } from "@/components/no-code/no-code-header";
import { ClaudeIcon } from "@/components/no-code/provider-icons";
import { SkillCard } from "@/components/no-code/skill-card";
import {
  developerSkills,
  installTabs,
  noCodeSkills,
} from "@/lib/no-code/catalog";
import { Terminal } from "lucide-react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent skills",
  description:
    "GAIK skills for Claude Desktop and coding agents: download one, or install them all as a plugin.",
};

export default function SkillsPage() {
  return (
    <div className="space-y-12">
      <NoCodeHeader active="/skills" />

      <section aria-labelledby="desktop-skills" className="space-y-4">
        <div>
          <h2
            id="desktop-skills"
            className="flex items-center gap-2 font-serif text-2xl font-semibold"
          >
            <ClaudeIcon className="size-6" />
            Claude Desktop
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Add the .zip under Settings, Capabilities.
          </p>
        </div>
        <div className="grid items-start gap-5 md:grid-cols-2">
          {noCodeSkills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} variant="desktop" />
          ))}
        </div>
      </section>

      <section aria-labelledby="agent-skills" className="space-y-4">
        <div>
          <h2
            id="agent-skills"
            className="flex items-center gap-2 font-serif text-2xl font-semibold"
          >
            <Terminal className="size-6" aria-hidden="true" />
            Coding agents
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            For building document pipelines with the gaik package. Install all
            three as one plugin.
          </p>
        </div>
        <CodeBlock language="bash" filename="Plugin" tabs={installTabs} />
        <div className="grid items-start gap-5 md:grid-cols-2 lg:grid-cols-3">
          {developerSkills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} variant="agent" />
          ))}
        </div>
      </section>
    </div>
  );
}
