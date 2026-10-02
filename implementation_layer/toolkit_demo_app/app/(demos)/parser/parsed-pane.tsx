"use client";

import { MarkdownView } from "@/components/demo/markdown-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  ListTree,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  outlineOf,
  parseBlocks,
  splitByQuery,
  statsOf,
  toPlainText,
} from "./parser-data";

export interface ParseRun {
  /** The parser asked for: one run is kept for each. */
  id: string;
  /** The parser that did the work (the HH Parser can fall back to another). */
  parser: string;
  text: string;
  metadata: Record<string, unknown>;
  seconds: number;
  filename: string;
  /** A styled page made by the parser itself: only the Multimodal parser has one. */
  html?: string;
}

export function parserLabel(parser: string): string {
  const names: Record<string, string> = {
    auto: "Auto-detect",
    pymupdf: "PyMuPDF",
    docx: "DOCX",
    vision: "Vision",
    vision_plus: "Vision+",
    docling_api: "HH Parser",
    multimodal: "Multimodal",
  };
  return names[parser] ?? parser;
}

function download(name: string, text: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/markdown;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Raw markdown with line numbers and the search marked. */
function SourceView({ text, query }: { text: string; query: string }) {
  const lines = text.split("\n");
  return (
    <pre className="font-mono text-xs leading-5">
      {lines.map((line, index) => (
        <div key={index} className="flex gap-3">
          <span className="text-muted-foreground w-8 shrink-0 text-right select-none">
            {index + 1}
          </span>
          <span className="min-w-0 break-words whitespace-pre-wrap">
            {splitByQuery(line, query).map((part, partIndex) =>
              part.hit ? (
                <mark
                  key={partIndex}
                  data-hit
                  className="rounded bg-amber-200 px-0.5 text-inherit"
                >
                  {part.text}
                </mark>
              ) : (
                part.text
              ),
            )}
          </span>
        </div>
      ))}
    </pre>
  );
}

/** One parsed document: views, search, outline, statistics, copy and download. */
export function ParsedPane({
  run,
  idPrefix,
}: {
  run: ParseRun;
  idPrefix: string;
}) {
  // The Multimodal parser's own HTML page comes first, and is what opens.
  const [tab, setTab] = useState(run.html ? "html" : "rendered");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(0);
  const [active, setActive] = useState(0);
  const [showOutline, setShowOutline] = useState(false);
  const [copied, setCopied] = useState(false);
  const body = useRef<HTMLDivElement>(null);

  const blocks = useMemo(() => parseBlocks(run.text), [run.text]);
  const outline = useMemo(() => outlineOf(blocks), [blocks]);
  const stats = useMemo(() => statsOf(run.text, blocks), [blocks, run.text]);
  const plain = useMemo(() => toPlainText(run.text), [run.text]);
  const hasMetadata = Object.keys(run.metadata ?? {}).length > 0;

  // The matches that are on screen, counted from the page itself, so the number and
  // the "next" button always agree with what is drawn.
  useEffect(() => {
    const marks = body.current?.querySelectorAll<HTMLElement>("mark[data-hit]");
    const count = marks?.length ?? 0;
    // What is on screen is the source of the count, so it is read after the draw.
    /* eslint-disable react-hooks/set-state-in-effect */
    setHits(count);
    setActive((current) => (current >= count ? 0 : current));
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [query, tab, run.text]);

  useEffect(() => {
    const marks = body.current?.querySelectorAll<HTMLElement>("mark[data-hit]");
    marks?.forEach((mark, index) => {
      mark.classList.toggle("ring-2", index === active);
      mark.classList.toggle("ring-primary", index === active);
    });
    if (query.trim() && marks && marks[active])
      marks[active].scrollIntoView({ block: "center", behavior: "smooth" });
  }, [active, hits, query]);

  const step = (direction: 1 | -1) => {
    if (hits === 0) return;
    setActive((current) => (current + direction + hits) % hits);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(run.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  const jump = (id: string) => {
    setTab("rendered");
    // The rendered view may not be on screen yet.
    setTimeout(
      () =>
        document
          .getElementById(`${idPrefix}${id}`)
          ?.scrollIntoView({ block: "start", behavior: "smooth" }),
      50,
    );
  };

  const statBadges: [string, number][] = [
    ["characters", stats.characters],
    ["words", stats.words],
    ["lines", stats.lines],
    ["headings", stats.headings],
    ["tables", stats.tables],
  ];

  return (
    <div className="bg-card min-w-0 space-y-3 rounded-xl border p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Parsed output</h3>
        <Badge variant="secondary" className="font-normal">
          {parserLabel(run.parser)}
        </Badge>
        <Badge variant="outline" className="font-normal">
          {run.seconds.toFixed(1)} s
        </Badge>
        <div className="ml-auto flex gap-1.5">
          <Button size="sm" variant="outline" onClick={() => void copy()}>
            {copied ? <Check /> : <Copy />}
            Copy
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              download(
                `${run.filename.replace(/\.[^.]+$/, "") || "parsed-document"}.md`,
                run.text,
              )
            }
          >
            <Download />
            .md
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {statBadges
          .filter(([label, value]) => value > 0 || label === "characters")
          .map(([label, value]) => (
            <Badge key={label} variant="outline" className="font-normal">
              {value.toLocaleString()} {label}
            </Badge>
          ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <div className="flex flex-wrap items-center gap-2">
          <TabsList>
            {run.html && <TabsTrigger value="html">HTML view</TabsTrigger>}
            <TabsTrigger value="rendered">Rendered</TabsTrigger>
            <TabsTrigger value="markdown">Markdown</TabsTrigger>
            <TabsTrigger value="plain">Plain text</TabsTrigger>
            {hasMetadata && (
              <TabsTrigger value="metadata">Metadata</TabsTrigger>
            )}
          </TabsList>
          {outline.length > 0 && (
            <Button
              size="sm"
              variant={showOutline ? "secondary" : "ghost"}
              onClick={() => setShowOutline(!showOutline)}
              aria-expanded={showOutline}
            >
              <ListTree />
              Outline
            </Button>
          )}
        </div>

        <div className={cn("relative mt-3", tab === "html" && "hidden")}>
          <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") step(e.shiftKey ? -1 : 1);
            }}
            placeholder="Search in the output"
            aria-label="Search in the output"
            className="pr-36 pl-8"
          />
          {query && (
            <div className="absolute top-1 right-1 flex items-center gap-0.5">
              <span className="text-muted-foreground mr-1 text-xs">
                {hits === 0 ? "no matches" : `${active + 1} of ${hits}`}
              </span>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label="Previous match"
                onClick={() => step(-1)}
                disabled={hits === 0}
              >
                <ChevronUp />
              </Button>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label="Next match"
                onClick={() => step(1)}
                disabled={hits === 0}
              >
                <ChevronDown />
              </Button>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label="Clear the search"
                onClick={() => setQuery("")}
              >
                <X />
              </Button>
            </div>
          )}
        </div>

        {showOutline && outline.length > 0 && (
          <nav
            aria-label="Outline"
            className="bg-muted/30 mt-3 max-h-40 space-y-0.5 overflow-auto rounded-md border p-2 text-sm"
          >
            {outline.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => jump(entry.id)}
                className="hover:text-primary block w-full truncate text-left"
                style={{ paddingLeft: `${(entry.level - 1) * 0.9}rem` }}
              >
                {entry.text}
              </button>
            ))}
          </nav>
        )}

        <div
          ref={body}
          className={cn(
            "bg-background mt-3 max-h-[34rem] overflow-auto rounded-md border p-4",
          )}
        >
          <TabsContent value="rendered" className="mt-0">
            {run.text.trim() === "" ? (
              <p className="text-muted-foreground text-sm">
                The parser found no text.
              </p>
            ) : (
              <MarkdownView blocks={blocks} query={query} idPrefix={idPrefix} />
            )}
          </TabsContent>
          <TabsContent value="markdown" className="mt-0">
            <SourceView text={run.text} query={query} />
          </TabsContent>
          <TabsContent value="plain" className="mt-0">
            <SourceView text={plain} query={query} />
          </TabsContent>
          {run.html && (
            <TabsContent value="html" className="-m-4 mt-0">
              {/* Fully sandboxed: the page is shown, and nothing in it can run. */}
              <iframe
                srcDoc={run.html}
                sandbox=""
                title="The parsed page as HTML"
                className="h-[32rem] w-full bg-white"
              />
            </TabsContent>
          )}
          {hasMetadata && (
            <TabsContent value="metadata" className="mt-0">
              <pre className="font-mono text-xs">
                {JSON.stringify(run.metadata, null, 2)}
              </pre>
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  );
}
