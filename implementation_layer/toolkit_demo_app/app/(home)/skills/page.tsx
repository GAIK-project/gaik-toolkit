import { CodeBlock } from "@/components/code-block";
import { SkillRow } from "@/components/no-code/skill-row";
import {
  developerSkills,
  installTabs,
  noCodeSkills,
} from "@/lib/no-code/catalog";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent skills",
  description:
    "GAIK skills for Claude Desktop and coding agents: download one, or install them all as a plugin.",
};

export default function SkillsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-14">
      <header className="space-y-2">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          Agent skills
        </h1>
        <p className="text-muted-foreground">
          Instructions an AI assistant loads when a task matches.
        </p>
      </header>

      <section aria-labelledby="desktop-skills">
        <h2 id="desktop-skills" className="font-serif text-2xl font-semibold">
          Claude Desktop
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Add the .zip under Settings, Capabilities.
        </p>
        <ul className="divide-border mt-4 divide-y border-y">
          {noCodeSkills.map((skill) => (
            <SkillRow key={skill.id} skill={skill} variant="desktop" />
          ))}
        </ul>
      </section>

      <section aria-labelledby="agent-skills">
        <h2 id="agent-skills" className="font-serif text-2xl font-semibold">
          Coding agents
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          For building document pipelines with the gaik package. Install all
          three as one plugin.
        </p>
        <div className="mt-4">
          <CodeBlock language="bash" filename="Plugin" tabs={installTabs} />
        </div>
        <ul className="divide-border mt-2 divide-y border-y">
          {developerSkills.map((skill) => (
            <SkillRow key={skill.id} skill={skill} variant="agent" />
          ))}
        </ul>
      </section>
    </div>
  );
}
