import { Button } from "@/components/ui/button";
import { formatBytes, launch, type Skill } from "@/lib/no-code/catalog";
import { ArrowRight, Download, ExternalLink } from "lucide-react";
import { CopyButton } from "./actions";
import { ClaudeIcon, CursorIcon } from "./provider-icons";

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
      <header className="space-y-1">
        <h3 className="text-lg font-semibold">{skill.title}</h3>
        <p className="text-muted-foreground text-sm">{skill.tagline}</p>
      </header>

      <dl className="text-muted-foreground grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt>Takes</dt>
        <dd className="text-foreground">{skill.input}</dd>
        <dt>Gives</dt>
        <dd className="text-foreground">{skill.output}</dd>
        <dt>Needs</dt>
        <dd className="text-foreground">{skill.needs.join(", ")}</dd>
      </dl>

      <div className="bg-muted/50 mt-auto space-y-3 rounded-lg p-3">
        <p className="text-sm">
          <span className="text-muted-foreground">Try: </span>
          {skill.tryPrompt}
        </p>
        <div className="flex flex-wrap gap-2">
          <CopyButton text={skill.tryPrompt} />
          {variant === "desktop" ? (
            <Button variant="outline" size="sm" asChild>
              <a href={launch.claude(skill.tryPrompt)}>
                <ClaudeIcon />
                Open in Claude
              </a>
            </Button>
          ) : (
            <>
              <Button variant="outline" size="sm" asChild>
                <a href={launch.claudeCode(skill.tryPrompt)}>
                  <ClaudeIcon />
                  Open in Claude Code
                </a>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <a href={launch.cursor(skill.tryPrompt)}>
                  <CursorIcon />
                  Open in Cursor
                </a>
              </Button>
            </>
          )}
        </div>
      </div>

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <Button asChild size="sm">
          <a href={skill.zip} download aria-label={`Download ${skill.title} skill`}>
            <Download />
            Download .zip
            <span className="text-primary-foreground/70 font-normal">
              {formatBytes(skill.zipBytes)}
            </span>
          </a>
        </Button>
        <a
          href={skill.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        >
          Source on GitHub
          <ExternalLink className="size-3.5" />
        </a>
        {skill.guideUrl && (
          <a
            href={skill.guideUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
          >
            Setup guide
            <ArrowRight className="size-3.5" />
          </a>
        )}
      </footer>
    </article>
  );
}
