import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import { IoLine } from "./io-line";
import { TryMenu } from "./try-menu";

const needsIcons: [RegExp, LucideIcon][] = [
  [/mcp/i, Plug],
  [/postgres/i, Database],
];

/** What the skill depends on, with a glyph for the kind of dependency. */
function Needs({ needs }: { needs: string[] }) {
  const joined = needs.join(", ");
  const Mark = needsIcons.find(([pattern]) => pattern.test(joined))?.[1];
  const Icon = Mark ?? Package;
  return (
    <p className="text-muted-foreground flex items-start gap-1.5">
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      Needs {joined}
    </p>
  );
}

/** What opens under a row: files in and out, what it needs, and the downloads. */
function SkillDetail({
  skill,
  variant,
}: {
  skill: Skill;
  variant: "desktop" | "agent";
}) {
  const guide = skill.guideUrl ? "Setup guide" : "Source on GitHub";
  return (
    <div className="space-y-3 sm:pl-13">
      <div className="space-y-1.5">
        <IoLine input={skill.input} output={skill.output} />
        {skill.needs.length > 0 && <Needs needs={skill.needs} />}
      </div>

      {skill.setup.length > 0 && (
        <ol className="text-muted-foreground list-decimal space-y-1.5 pl-5 break-words">
          {skill.setup.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
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
        {skill.kit && (
          <Button asChild size="sm" variant="outline">
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
        <TryMenu prompt={skill.tryPrompt} variant={variant} />
        <a
          href={skill.guideUrl ?? skill.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 py-1.5"
        >
          {guide}
          <ExternalLink className="size-3.5" aria-hidden="true" />
        </a>
      </div>
    </div>
  );
}

/**
 * Skills as one quiet list: a row says what the skill does, a press opens the
 * rest. `agent` skills run inside a coding agent; the rest in Claude Desktop.
 */
export function SkillList({
  skills,
  variant,
}: {
  skills: Skill[];
  variant: "desktop" | "agent";
}) {
  return (
    <Accordion
      type="multiple"
      className="bg-card overflow-hidden rounded-xl border"
    >
      {skills.map((skill) => (
        <AccordionItem key={skill.id} value={skill.id}>
          <AccordionTrigger className="hover:bg-muted/50 items-center gap-3 rounded-none px-4 py-3.5 hover:no-underline focus-visible:ring-inset sm:px-5">
            <AssetIcon id={skill.id} />
            <span className="min-w-0 flex-1">
              <span className="block text-base leading-tight font-semibold">
                {skill.title}
              </span>
              <span className="text-muted-foreground mt-1 block font-normal">
                {skill.tagline}
              </span>
            </span>
          </AccordionTrigger>
          <AccordionContent className="px-4 pt-1 pb-5 sm:px-5">
            <SkillDetail skill={skill} variant={variant} />
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
