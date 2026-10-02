"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  QuoteFailure,
  SectionKnowledge,
} from "@/lib/knowledge-curator/workspace";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  allFacts,
  countBy,
  findQuote,
  matchesFilter,
  NO_FILTER,
  type Fact,
  type FactFilter,
} from "../curator-data";

export interface SourceFile {
  id: string;
  file: string;
  source_class: string | null;
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-red-100 text-red-800",
};

/** The text of a source around a quote, with the quote marked. */
function Context({ source, quote }: { source: string; quote: string }) {
  const found = findQuote(source, quote);
  if (!found) return null;
  const from = Math.max(0, found.start - 160);
  const to = Math.min(source.length, found.end + 160);
  return (
    <p className="bg-muted/40 rounded-md border p-2 text-xs leading-relaxed whitespace-pre-wrap">
      {from > 0 && "…"}
      {source.slice(from, found.start)}
      <mark className="rounded bg-amber-200 px-0.5 text-inherit">
        {source.slice(found.start, found.end)}
      </mark>
      {source.slice(found.end, to)}
      {to < source.length && "…"}
    </p>
  );
}

function FactCard({
  fact,
  source,
  failure,
  isFocus,
}: {
  fact: Fact;
  source: string | undefined;
  failure: QuoteFailure | undefined;
  isFocus: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  // Checked here, on the page, so it shows before the server verifies.
  const inSource =
    source === undefined ? null : findQuote(source, fact.quote) !== null;
  const bad = failure !== undefined || inSource === false;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fact.quote);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <li
      id={`fact-${fact.id}`}
      className={cn(
        "space-y-2 rounded-lg border p-3 text-sm",
        bad && "border-destructive",
        isFocus && "ring-primary ring-2",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground font-mono text-xs">
          {fact.id}
        </span>
        <span className="font-medium">{fact.topic}</span>
        {fact.time_qualifier && (
          <span className="text-muted-foreground text-xs">
            ({fact.time_qualifier})
          </span>
        )}
        <span
          className={cn(
            "ml-auto rounded px-1.5 py-0.5 text-xs",
            CONFIDENCE_STYLE[fact.confidence] ?? "bg-muted",
          )}
        >
          {fact.confidence}
        </span>
      </div>
      <p>{fact.summary}</p>
      <blockquote className="border-primary/30 text-muted-foreground border-l-2 pl-3 text-xs italic">
        {fact.quote}
      </blockquote>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted-foreground font-mono">
          {fact.source.file}
          {fact.source.locator ? `, ${fact.source.locator}` : ""}
        </span>
        {fact.source_class && (
          <Badge variant="outline" className="text-[10px]">
            {fact.source_class}
          </Badge>
        )}
        {failure ? (
          <Badge variant="destructive" className="text-[10px]">
            {failure.reason}
          </Badge>
        ) : inSource === true ? (
          <span className="flex items-center gap-1 text-emerald-700">
            <Check className="size-3" /> quote found in the source
          </span>
        ) : inSource === false ? (
          <span className="flex items-center gap-1 text-red-700">
            <AlertTriangle className="size-3" /> quote not found in the source
          </span>
        ) : null}
        <span className="ml-auto flex gap-1">
          {source !== undefined && inSource && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
            >
              {open ? <ChevronUp /> : <ChevronDown />}
              In the source
            </Button>
          )}
          <Button size="xs" variant="ghost" onClick={() => void copy()}>
            {copied ? <Check /> : <Copy />}
            Quote
          </Button>
        </span>
      </div>
      {open && source !== undefined && (
        <Context source={source} quote={fact.quote} />
      )}
    </li>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "hover:border-primary/40",
      )}
    >
      {children}
    </button>
  );
}

/** The facts of every topic: filter them, read the quote in its source, follow the conflicts. */
export function FactsExplorer({
  sections,
  sources,
  normalized,
  failures,
}: {
  sections: SectionKnowledge[];
  sources: SourceFile[];
  normalized: Record<string, string>;
  failures: QuoteFailure[];
}) {
  const [filter, setFilter] = useState<FactFilter>(NO_FILTER);
  const [topic, setTopic] = useState<string | null>(null);
  const [tab, setTab] = useState("facts");
  const [focus, setFocus] = useState<string[] | null>(null);

  const facts = useMemo(() => allFacts(sections), [sections]);
  const sourceText = (file: string) => {
    const entry = sources.find((s) => s.file === file);
    return entry ? normalized[`normalized/${entry.id}.md`] : undefined;
  };
  const failureOf = (fact: Fact) =>
    failures.find(
      (f) => f.unit_id === fact.id && f.section_id === fact.sectionId,
    );

  const shown = facts.filter(
    (fact) =>
      (topic === null || fact.sectionId === topic) &&
      (focus === null || focus.includes(fact.id)) &&
      matchesFilter(fact, filter),
  );
  const topics = sections.map((section) => section.section_id);
  const missing = sections.filter(
    (section) => topic === null || section.section_id === topic,
  );
  const conflicts = sections.flatMap((section) =>
    section.conflicts
      .filter(() => topic === null || section.section_id === topic)
      .map((conflict) => ({ ...conflict, sectionId: section.section_id })),
  );
  const missingCount = missing.reduce((sum, s) => sum + s.missing.length, 0);
  const filtering =
    filter.query !== "" ||
    filter.confidence !== null ||
    filter.file !== null ||
    filter.sourceClass !== null;

  const goToFacts = (ids: string[]) => {
    setFocus(ids);
    setFilter(NO_FILTER);
    setTopic(null);
    setTab("facts");
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-muted-foreground text-xs">Topic</span>
        <Chip active={topic === null} onClick={() => setTopic(null)}>
          all
        </Chip>
        {topics.map((id) => (
          <Chip
            key={id}
            active={topic === id}
            onClick={() => setTopic(topic === id ? null : id)}
          >
            {id}
          </Chip>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="facts">
            Facts
            <span className="text-muted-foreground ml-1.5 text-xs">
              {shown.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="conflicts">
            Conflicts
            <span className="text-muted-foreground ml-1.5 text-xs">
              {conflicts.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="missing">
            Missing
            <span className="text-muted-foreground ml-1.5 text-xs">
              {missingCount}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="facts" className="mt-3 space-y-3">
          <div className="relative">
            <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
            <Input
              value={filter.query}
              onChange={(e) => setFilter({ ...filter, query: e.target.value })}
              placeholder="Search the facts, their quotes and topics"
              aria-label="Search the facts"
              className="pr-8 pl-8"
            />
            {filter.query && (
              <button
                type="button"
                aria-label="Clear the search"
                onClick={() => setFilter({ ...filter, query: "" })}
                className="text-muted-foreground hover:text-foreground absolute top-2.5 right-2.5"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground text-xs">Confidence</span>
              {countBy(facts, (f) => f.confidence).map(([name, count]) => (
                <Chip
                  key={name}
                  active={filter.confidence === name}
                  onClick={() =>
                    setFilter({
                      ...filter,
                      confidence: filter.confidence === name ? null : name,
                    })
                  }
                >
                  {name} {count}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground text-xs">Source</span>
              {countBy(facts, (f) => f.source.file).map(([name, count]) => (
                <Chip
                  key={name}
                  active={filter.file === name}
                  onClick={() =>
                    setFilter({
                      ...filter,
                      file: filter.file === name ? null : name,
                    })
                  }
                >
                  {name} {count}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground text-xs">Class</span>
              {countBy(facts, (f) => f.source_class).map(([name, count]) => (
                <Chip
                  key={name}
                  active={filter.sourceClass === name}
                  onClick={() =>
                    setFilter({
                      ...filter,
                      sourceClass: filter.sourceClass === name ? null : name,
                    })
                  }
                >
                  {name} {count}
                </Chip>
              ))}
            </div>
          </div>
          {focus && (
            <div className="bg-primary/5 flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs">
              Showing the {focus.length} facts of a conflict.
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setFocus(null)}
                className="ml-auto"
              >
                <X />
                Show all
              </Button>
            </div>
          )}
          {filtering && (
            <p className="text-muted-foreground text-xs">
              {shown.length} of {facts.length} facts match.{" "}
              <button
                type="button"
                className="text-primary underline"
                onClick={() => setFilter(NO_FILTER)}
              >
                Clear the filters
              </button>
            </p>
          )}
          {shown.length === 0 ? (
            <p className="text-muted-foreground text-sm">No facts to show.</p>
          ) : (
            <div className="max-h-[40rem] space-y-4 overflow-auto pr-1">
              {sections
                .filter((section) =>
                  shown.some((fact) => fact.sectionId === section.section_id),
                )
                .map((section) => (
                  <section key={section.section_id} className="space-y-2">
                    <h4 className="text-sm font-semibold">
                      {section.section_id}
                      <span className="text-muted-foreground ml-2 text-xs font-normal">
                        {
                          shown.filter(
                            (fact) => fact.sectionId === section.section_id,
                          ).length
                        }{" "}
                        facts
                      </span>
                    </h4>
                    <ul className="space-y-2">
                      {shown
                        .filter((fact) => fact.sectionId === section.section_id)
                        .map((fact) => (
                          <FactCard
                            key={`${fact.sectionId}-${fact.id}`}
                            fact={fact}
                            source={sourceText(fact.source.file)}
                            failure={failureOf(fact)}
                            isFocus={focus !== null}
                          />
                        ))}
                    </ul>
                  </section>
                ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="conflicts" className="mt-3">
          {conflicts.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No conflicts: the sources do not disagree on any topic.
            </p>
          ) : (
            <ul className="space-y-2">
              {conflicts.map((conflict, index) => (
                <li
                  key={index}
                  className="space-y-2 rounded-lg border p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{conflict.topic}</span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px]",
                        conflict.status.toLowerCase() === "unresolved" &&
                          "border-amber-500 text-amber-700",
                      )}
                    >
                      {conflict.status}
                    </Badge>
                    <span className="text-muted-foreground font-mono text-xs">
                      {conflict.sectionId}
                    </span>
                  </div>
                  <p className="text-muted-foreground">
                    {conflict.description}
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {conflict.unit_ids.map((id) => {
                      const fact = facts.find(
                        (f) =>
                          f.id === id && f.sectionId === conflict.sectionId,
                      );
                      return (
                        <span
                          key={id}
                          className="bg-muted rounded px-1.5 py-0.5 text-xs"
                          title={fact?.quote}
                        >
                          <span className="font-mono">{id}</span>
                          {fact && (
                            <span className="text-muted-foreground">
                              {" "}
                              · {fact.source.file}
                            </span>
                          )}
                        </span>
                      );
                    })}
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => goToFacts(conflict.unit_ids)}
                      className="ml-auto"
                    >
                      Show these facts
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="missing" className="mt-3">
          {missingCount === 0 ? (
            <p className="text-muted-foreground text-sm">
              Nothing is missing: the sources cover every required item.
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-muted-foreground text-xs">
                Required items that no source covers. A source for them is
                needed, or the item can be taken off the topic.
              </p>
              {missing
                .filter((section) => section.missing.length > 0)
                .map((section) => (
                  <div key={section.section_id}>
                    <p className="mb-1 text-sm font-semibold">
                      {section.section_id}
                    </p>
                    <ul className="space-y-1">
                      {section.missing.map((item, index) => (
                        <li
                          key={index}
                          className="flex items-center gap-2 rounded border border-dashed px-3 py-1.5 text-sm"
                        >
                          <AlertTriangle className="size-3.5 text-amber-600" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
