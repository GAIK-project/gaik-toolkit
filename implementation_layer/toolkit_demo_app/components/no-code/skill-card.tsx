import { Button } from "@/components/ui/button";
import { formatBytes, type Skill } from "@/lib/no-code/catalog";
import {
  Database,
  Download,
  ExternalLink,
  type LucideIcon,
  Package,
  Plug,
} from "lucide-react";
import { AssetIcon } from "./asset-icon";
import { Disclosure } from "./disclosure";
import { IoLine } from "./io-line";
import { TryMenu } from "./try-menu";

const needsIcons: [RegExp, LucideIcon][] = [
  [/mcp/i, Plug],
  [/postgres/i, Database],
];

/** What the skill depends on; opens the setup steps when there are any. */
function Needs({ needs }: { needs: string[] }) {
  const joined = needs.join(", ");
  const Icon = needsIcons.find(([pattern]) => pattern.test(joined))?.[1];
  const Mark = Icon ?? Package;
  return (
    <span className="flex items-center gap-1.5 text-left">
      <Mark className="size-4 shrink-0" aria-hidden="true" />
      Needs {joined}
    </span>
  );
}

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
        {skill.setup.length > 0 ? (
          <Disclosure label={<Needs needs={skill.needs} />}>
            <ol className="text-muted-foreground list-decimal space-y-1.5 pl-5 text-sm">
              {skill.setup.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            {skill.kit && (
              <Button asChild size="sm" variant="outline" className="mt-3">
                <a
                  href={skill.kit.zip}
                  download
                  aria-label={`Download setup kit for ${skill.title}`}
                >
                  <Download />
                  Setup kit · {formatBytes(skill.kit.zipBytes)}
                </a>
              </Button>
            )}
          </Disclosure>
        ) : (
          skill.needs.length > 0 && (
            <p className="text-muted-foreground py-1">
              <Needs needs={skill.needs} />
            </p>
          )
        )}
      </div>

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
