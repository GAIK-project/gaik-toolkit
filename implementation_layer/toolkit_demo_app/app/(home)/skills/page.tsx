import { CodeBlock } from "@/components/code-block";
import { SkillCard } from "@/components/no-code/skill-card";
import {
  developerSkills,
  installTabs,
  noCodeSkills,
  plugin,
} from "@/lib/no-code/catalog";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent skills",
  description:
    "GAIK skills for Claude Desktop and coding agents: download one, or install them all as a plugin.",
};

export default function SkillsPage() {
  return (
    <div className="space-y-14">
      <header className="max-w-2xl space-y-3">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          Agent skills
        </h1>
        <p className="text-muted-foreground">
          A skill is a folder of instructions an AI assistant loads when the
          task matches. Download one below, or install the developer skills as a
          plugin.
        </p>
      </header>

      <section className="space-y-5" aria-labelledby="desktop-skills">
        <div className="max-w-2xl space-y-1">
          <h2 id="desktop-skills" className="font-serif text-2xl font-semibold">
            Skills for Claude Desktop
          </h2>
          <p className="text-muted-foreground text-sm">
            Add the .zip under Settings, Capabilities, then start a chat with
            the prompt. Each skill&apos;s setup guide covers the MCP servers it
            needs.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          {noCodeSkills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} variant="desktop" />
          ))}
        </div>
      </section>

      <section className="space-y-5" aria-labelledby="agent-skills">
        <div className="max-w-2xl space-y-1">
          <h2 id="agent-skills" className="font-serif text-2xl font-semibold">
            Skills for coding agents
          </h2>
          <p className="text-muted-foreground text-sm">
            For building document pipelines with the gaik Python package. One
            plugin holds all three, version {plugin.version}.
          </p>
        </div>
        <CodeBlock
          language="bash"
          filename="Install the plugin"
          tabs={installTabs}
        />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {developerSkills.map((skill) => (
            <SkillCard key={skill.id} skill={skill} variant="agent" />
          ))}
        </div>
      </section>
    </div>
  );
}
