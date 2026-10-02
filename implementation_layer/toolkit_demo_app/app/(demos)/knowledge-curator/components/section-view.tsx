"use client";

import { Badge } from "@/components/ui/badge";
import type {
  QuoteFailure,
  SectionKnowledge,
} from "@/lib/knowledge-curator/workspace";
import { cn } from "@/lib/utils";

/**
 * The missing items, conflicts and facts of one topic (a section, in a report), with the facts
 * whose quote failed flagged. `noun` is what the page calls it.
 */
export function SectionView({
  knowledge,
  failures,
  noun = "section",
}: {
  knowledge: SectionKnowledge;
  failures: QuoteFailure[];
  noun?: string;
}) {
  const failing = new Map(failures.map((f) => [f.unit_id, f.reason]));
  return (
    <div className="space-y-3 text-xs">
      {knowledge.missing.length > 0 && (
        <div>
          <p className="mb-1 font-medium">Missing (no source covers)</p>
          <ul className="text-muted-foreground list-inside list-disc">
            {knowledge.missing.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {knowledge.conflicts.length > 0 && (
        <div>
          <p className="mb-1 font-medium">Conflicts</p>
          <ul className="space-y-1">
            {knowledge.conflicts.map((c, i) => (
              <li key={i} className="rounded border px-2 py-1">
                <span className="font-medium">{c.topic}</span>{" "}
                <Badge variant="outline" className="text-[10px]">
                  {c.status}
                </Badge>
                <p className="text-muted-foreground">{c.description}</p>
                <p className="text-muted-foreground font-mono">
                  {c.unit_ids.join(", ")}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <p className="mb-1 font-medium">Facts ({knowledge.units.length})</p>
        {knowledge.units.length === 0 && (
          <p className="text-muted-foreground">No facts in this {noun}.</p>
        )}
        <ul className="space-y-2">
          {knowledge.units.map((u) => (
            <li
              key={u.id}
              className={cn(
                "space-y-1 rounded border px-2 py-1.5",
                failing.has(u.id) && "border-destructive",
              )}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-muted-foreground font-mono">{u.id}</span>
                <span className="font-medium">{u.topic}</span>
                {u.time_qualifier && (
                  <span className="text-muted-foreground">
                    ({u.time_qualifier})
                  </span>
                )}
                <Badge variant="outline" className="text-[10px]">
                  {u.confidence}
                </Badge>
                {failing.has(u.id) && (
                  <Badge variant="destructive" className="text-[10px]">
                    {failing.get(u.id)}
                  </Badge>
                )}
              </div>
              <p>{u.summary}</p>
              <blockquote className="text-muted-foreground border-l-2 pl-2">
                {u.quote}
              </blockquote>
              <p className="text-muted-foreground font-mono">
                {u.source.file}
                {u.source.locator ? `, ${u.source.locator}` : ""}
                {u.source_class ? ` · ${u.source_class}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
