import { Button } from "@/components/ui/button";
import { formatBytes, launch, type Skill } from "@/lib/no-code/catalog";
import { Download, ExternalLink } from "lucide-react";
import { CopyButton } from "./actions";
import { OpenInMenu } from "./open-in-menu";
import { ClaudeIcon } from "./provider-icons";

/** `agent` skills run inside a coding agent; the rest run in Claude Desktop. */
export function SkillRow({
  skill,
  variant,
}: {
  skill: Skill;
  variant: "desktop" | "agent";
}) {
  const link = skill.guideUrl ?? skill.githubUrl;

  return (
    <li className="grid gap-4 py-6 md:grid-cols-[minmax(0,1fr)_auto] md:gap-8">
      <div className="min-w-0 space-y-2">
        <h3 className="text-lg font-semibold">{skill.title}</h3>
        <p className="text-muted-foreground text-sm">{skill.tagline}</p>
        <p className="text-sm">
          {skill.input} <span aria-label="to">→</span> {skill.output}
          {skill.needs.length > 0 && (
            <span className="text-muted-foreground">
              {" "}
              · needs {skill.needs.join(", ")}
            </span>
          )}
        </p>
        <details className="group text-sm">
          <summary className="text-muted-foreground hover:text-foreground w-fit cursor-pointer">
            Prompt to try
          </summary>
          <p className="bg-muted/50 mt-2 rounded-md p-3">{skill.tryPrompt}</p>
        </details>
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          {skill.guideUrl ? "Setup guide" : "Source"}
          <ExternalLink className="size-3.5" />
        </a>
      </div>

      <div className="flex flex-wrap items-start gap-2 md:max-w-64 md:justify-end">
        <Button
          asChild
          size="sm"
          variant={variant === "desktop" ? "default" : "outline"}
        >
          <a
            href={skill.zip}
            download
            aria-label={`Download ${skill.title} skill`}
          >
            <Download />
            .zip · {formatBytes(skill.zipBytes)}
          </a>
        </Button>
        {variant === "desktop" ? (
          <Button variant="outline" size="sm" asChild>
            <a href={launch.claude(skill.tryPrompt)}>
              <ClaudeIcon />
              Try in Claude
            </a>
          </Button>
        ) : (
          <OpenInMenu prompt={skill.tryPrompt} />
        )}
        <CopyButton text={skill.tryPrompt} label="Copy" variant="ghost" />
      </div>
    </li>
  );
}
