import { Button } from "@/components/ui/button";
import { formatBytes, type Skill } from "@/lib/no-code/catalog";
import { Download, ExternalLink } from "lucide-react";
import { AssetIcon } from "./asset-icon";
import { Disclosure } from "./disclosure";
import { IoLine } from "./io-line";
import { TryMenu } from "./try-menu";

/** `agent` skills run inside a coding agent; the rest run in Claude Desktop. */
export function SkillCard({
  skill,
  variant,
}: {
  skill: Skill;
  variant: "desktop" | "agent";
}) {
  return (
    <article className="bg-card flex flex-col gap-4 rounded-xl border p-5">
      <header className="flex items-start gap-3">
        <AssetIcon id={skill.id} />
        <div className="space-y-1">
          <h3 className="text-lg leading-tight font-semibold">{skill.title}</h3>
          <p className="text-muted-foreground text-sm">{skill.tagline}</p>
        </div>
      </header>

      <div className="space-y-1 text-sm">
        <IoLine input={skill.input} output={skill.output} />
        {skill.needs.length > 0 && (
          <p className="text-muted-foreground">
            Needs {skill.needs.join(", ")}
          </p>
        )}
      </div>

      <Disclosure label="Prompt to try">
        <p className="bg-muted/50 rounded-md p-3 text-sm">{skill.tryPrompt}</p>
      </Disclosure>

      <footer className="mt-auto flex items-center gap-2 pt-1">
        <Button asChild size="sm">
          <a
            href={skill.zip}
            download
            aria-label={`Download ${skill.title} skill`}
          >
            <Download />
            .zip · {formatBytes(skill.zipBytes)}
          </a>
        </Button>
        <TryMenu prompt={skill.tryPrompt} variant={variant} />
        <a
          href={skill.guideUrl ?? skill.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={skill.guideUrl ? "Setup guide" : "Source on GitHub"}
          title={skill.guideUrl ? "Setup guide" : "Source on GitHub"}
          className="text-muted-foreground hover:text-foreground ml-auto p-1"
        >
          <ExternalLink className="size-4" />
        </a>
      </footer>
    </article>
  );
}
