import { AgentLogos } from "@/components/no-code/agent-logos";
import { InstallPlugin } from "@/components/no-code/install-plugin";
import { NoCodeHeader } from "@/components/no-code/no-code-header";
import { ClaudeIcon } from "@/components/no-code/provider-icons";
import { SkillList } from "@/components/no-code/skill-list";
import {
  developerSkills,
  installGuideUrl,
  noCodeSkills,
  skills,
} from "@/lib/no-code/catalog";
import { ExternalLink, Terminal } from "lucide-react";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent skills",
  description:
    "GAIK skills for Claude Desktop and coding agents: download one, or install them all as a plugin.",
};

export default function SkillsPage() {
  return (
    <div className="space-y-12">
      <NoCodeHeader
        active="/skills"
        lede={`A skill is a folder of instructions that an agent opens when a task calls for it. Install all ${skills.length} as one plugin, or download a single skill as a .zip.`}
      />

      <section aria-labelledby="install-plugin" className="space-y-4">
        <h2 id="install-plugin" className="font-serif text-2xl font-semibold">
          Install the plugin
        </h2>
        <InstallPlugin />
        <AgentLogos lead="Skills also work in" which={["cursor", "gemini"]}>
          <a
            href={installGuideUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground flex items-center gap-1.5 underline underline-offset-4"
          >
            VS Code, ChatGPT and other clients
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        </AgentLogos>
      </section>

      <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-8">
        <section aria-labelledby="desktop-skills" className="min-w-0 space-y-4">
          <div>
            <h2
              id="desktop-skills"
              className="flex items-center gap-2 font-serif text-2xl font-semibold"
            >
              <ClaudeIcon className="size-6" />
              Claude Desktop
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Upload the .zip in Customize → Skills.
            </p>
          </div>
          <SkillList skills={noCodeSkills} variant="desktop" />
        </section>

        <section aria-labelledby="agent-skills" className="min-w-0 space-y-4">
          <div>
            <h2
              id="agent-skills"
              className="flex items-center gap-2 font-serif text-2xl font-semibold"
            >
              <Terminal className="size-6" aria-hidden="true" />
              Coding agents
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              For building document pipelines with the gaik package.
            </p>
          </div>
          <SkillList skills={developerSkills} variant="agent" />
        </section>
      </div>
    </div>
  );
}
