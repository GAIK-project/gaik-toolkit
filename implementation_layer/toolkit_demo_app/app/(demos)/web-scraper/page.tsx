"use client";

import { parseBlocks } from "@/app/(demos)/parser/parser-data";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { MarkdownView } from "@/components/demo/markdown-view";
import { PageTransition } from "@/components/demo/page-transition";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { downloadBlob } from "@/lib/download";
import { parseSSEEvents } from "@/lib/sse";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  CircleHelp,
  Copy,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  Square,
  Waypoints,
} from "lucide-react";
import dynamic from "next/dynamic";
import posthog from "posthog-js";
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import toast from "react-hot-toast";
import {
  type Citation,
  type CrawlNode,
  DEFAULT_SITES,
  INITIAL_STATE,
  PRESETS,
  type RunEvent,
  type Site,
  cellText,
  citationsByCell,
  citationsPerPage,
  crawlMarkdown,
  findNode,
  inDomains,
  isUrl,
  pageOfRow,
  reduceRun,
  shortUrl,
  tableOf,
} from "./scraper-data";

const Constellation = dynamic(() => import("./constellation"), {
  ssr: false,
  loading: () => <div className="h-full w-full" />,
});

const PAGE_OPTIONS = [3, 6, 12];
const DEPTH_OPTIONS = [
  { value: 0, label: "Start page" },
  { value: 1, label: "1 link away" },
  { value: 2, label: "2 links away" },
];

const VERDICTS: Record<
  Citation["verdict"],
  { label: string; className: string }
> = {
  verified: { label: "Quote found, value matches", className: "bg-teal-500" },
  reworded: {
    label: "Quote found, value in the model's words",
    className: "bg-sky-400",
  },
  check: {
    label: "Check: quote not found or a number differs",
    className: "bg-amber-500",
  },
  unchecked: { label: "Not checked", className: "bg-slate-400" },
};

function StatusLine({
  phase,
  message,
  current,
}: {
  phase: string;
  message: string | null;
  current: CrawlNode | undefined;
}) {
  const text =
    phase === "crawling"
      ? current
        ? `Fetching ${shortUrl(current.url)}`
        : "Starting the crawl"
      : phase === "schema" || phase === "extracting"
        ? (message ?? "Extracting")
        : phase === "error"
          ? "The run stopped"
          : phase === "done"
            ? "Done"
            : null;
  if (!text) return null;
  const busy =
    phase === "crawling" || phase === "schema" || phase === "extracting";
  return (
    <p
      className="flex max-w-[70%] items-center gap-2 truncate text-xs font-medium text-slate-200"
      aria-live="polite"
    >
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          busy
            ? "animate-pulse bg-teal-300"
            : phase === "error"
              ? "bg-rose-400"
              : "bg-teal-400",
        )}
      />
      <span className="truncate">{text}</span>
    </p>
  );
}

function Legend() {
  const items = [
    { label: "Start page", className: "bg-amber-300" },
    { label: "Page", className: "bg-teal-300" },
    { label: "Link not fetched", className: "bg-slate-400/70 size-1.5" },
    { label: "Skipped", className: "bg-rose-400" },
    {
      label: "Holds cited values",
      className: "ring-2 ring-amber-400 bg-transparent",
    },
  ];
  return (
    <ul className="pointer-events-none flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            className={cn("inline-block size-2 rounded-full", item.className)}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** "headline, row 2" for the citation path records[1].headline. */
function fieldLabel(citation: Citation): string {
  const column = (citation.field.split(".").pop() ?? citation.field).replace(
    /\[\d+\]$/,
    "",
  );
  const name = column.replace(/_/g, " ");
  return citation.record === null
    ? name
    : `${name}, row ${citation.record + 1}`;
}

function CitationDetail({
  citation,
  onPage,
}: {
  citation: Citation;
  onPage: (url: string) => void;
}) {
  const verdict = VERDICTS[citation.verdict] ?? VERDICTS.unchecked;
  return (
    <div className="bg-muted/50 space-y-2 rounded-lg border p-3 text-sm">
      <p className="flex items-center gap-2 text-xs font-medium">
        <span className={cn("size-2 rounded-full", verdict.className)} />
        {verdict.label}
        <span className="text-muted-foreground font-normal">
          {fieldLabel(citation)}
        </span>
      </p>
      <blockquote className="border-primary/60 border-l-2 pl-3 italic">
        “{citation.quote}”
      </blockquote>
      {citation.page_url && (
        <button
          type="button"
          onClick={() => onPage(citation.page_url!)}
          className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
        >
          <Waypoints className="size-3.5" />
          {shortUrl(citation.page_url)}
        </button>
      )}
    </div>
  );
}

export default function WebScraperPage() {
  const [sites, setSites] = useState<Site[]>(DEFAULT_SITES);
  const [domains, setDomains] = useState<string[]>(
    DEFAULT_SITES.map((s) => s.domain),
  );
  const [siteId, setSiteId] = useState(DEFAULT_SITES[0].id);
  const [startUrl, setStartUrl] = useState(DEFAULT_SITES[0].url);
  const [maxPages, setMaxPages] = useState(6);
  const [maxDepth, setMaxDepth] = useState(1);
  const [pattern, setPattern] = useState("");
  const [requirements, setRequirements] = useState(
    PRESETS.gaik[0].requirements,
  );
  const [state, dispatch] = useReducer(reduceRun, INITIAL_STATE);
  const [selected, setSelected] = useState<string | null>(null);
  const [cell, setCell] = useState<string | null>(null);
  const [tab, setTab] = useState("data");
  const abortRef = useRef<AbortController | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch("/api/web-scraper/sites")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!data?.sites?.length) return;
        setSites(data.sites);
        setDomains(data.allowed_domains);
      })
      .catch(() => {});
    return () => abortRef.current?.abort();
  }, []);

  const site = sites.find((s) => s.id === siteId) ?? sites[0];
  const presets = PRESETS[site.id] ?? [];
  const running = ["crawling", "schema", "extracting"].includes(state.phase);
  const urlAllowed = inDomains(startUrl, domains);
  const extracting = requirements.trim().length > 0;
  const pages = state.nodes.filter((node) => node.status === "page");
  const skipped = state.nodes.filter((node) => node.status === "skipped");
  const current = [...state.nodes]
    .reverse()
    .find((node) => node.status === "fetching");
  const words = pages.reduce((sum, node) => sum + (node.words ?? 0), 0);

  const citations = useMemo(
    () => citationsPerPage(state.extraction?.sources ?? []),
    [state.extraction],
  );
  const table = useMemo(
    () => tableOf(state.extraction?.records ?? []),
    [state.extraction],
  );
  const cells = useMemo(
    () => citationsByCell(state.extraction?.sources ?? []),
    [state.extraction],
  );
  // Columns of long text get room to wrap in lines, not in single words.
  const wide = useMemo(
    () =>
      new Set(
        table.columns.filter((column) =>
          table.rows.some(
            (row) => !isUrl(row[column]) && cellText(row[column]).length > 24,
          ),
        ),
      ),
    [table],
  );
  const selectedNode = findNode(state.nodes, selected);
  const selectedCitation = cell ? cells.get(cell) : undefined;
  const markdown = useMemo(() => crawlMarkdown(state.nodes), [state.nodes]);

  const select = useCallback((url: string | null) => setSelected(url), []);

  function chooseSite(next: Site) {
    if (running) return;
    setSiteId(next.id);
    setStartUrl(next.url);
    setPattern("");
    setRequirements(PRESETS[next.id]?.[0]?.requirements ?? "");
  }

  function selectPage(url: string) {
    const node = findNode(state.nodes, url);
    setSelected(node ? node.url : null);
  }

  async function handleRun() {
    if (running) return;
    if (!urlAllowed) {
      toast.error(`Start from a page on ${domains.join(" or ")}`);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    dispatch({ type: "start" });
    setSelected(null);
    setCell(null);
    setTab(extracting ? "data" : "pages");
    // On a narrow screen the scene sits below the settings: bring it into view.
    const stage = stageRef.current?.getBoundingClientRect();
    if (stage && (stage.top < 0 || stage.bottom > window.innerHeight)) {
      const reduce = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      stageRef.current?.scrollIntoView({
        behavior: reduce ? "auto" : "smooth",
        block: "center",
      });
    }
    let failed: string | null = null;
    try {
      const response = await apiFetch("/api/web-scraper/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: startUrl.trim(),
          max_pages: maxPages,
          max_depth: maxDepth,
          include_pattern: pattern.trim() || null,
          requirements: requirements.trim() || null,
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const error = await response.json().catch(() => null);
        const detail = error?.detail;
        throw new Error(
          error?.error ??
            (typeof detail === "string" ? detail : null) ??
            (Array.isArray(detail)
              ? "Check the settings: one of them is out of range."
              : null) ??
            "The crawl could not start.",
        );
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEEvents(buffer);
        buffer = remaining;
        for (const event of events) {
          if (event.type === "error")
            failed = String(event.data.message ?? "The run failed.");
          dispatch(event as RunEvent);
        }
      }
      posthog.capture("web_scraper_run", {
        site: site.id,
        max_pages: maxPages,
        max_depth: maxDepth,
        extract: extracting,
        failed: !!failed,
      });
      if (failed) toast.error(failed);
    } catch (error) {
      if (controller.signal.aborted) {
        dispatch({ type: "crawl_done", data: {} });
        toast("Stopped");
        return;
      }
      if (error instanceof RateLimitError) {
        dispatch({ type: "error", data: { message: "Too many requests." } });
        return;
      }
      const message =
        error instanceof Error ? error.message : "The run failed.";
      dispatch({ type: "error", data: { message } });
      toast.error(message);
    } finally {
      abortRef.current = null;
    }
  }

  async function copyMarkdown(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Markdown copied");
    } catch {
      toast.error("Could not copy");
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Globe}
        title="Web Scraper"
        description="Crawl a website into clean Markdown and pull structured data out of it, with the page each value came from"
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-8">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Site</CardTitle>
              <CardDescription>
                This demo scrapes only {domains.join(" and ")}. The crawler
                obeys robots.txt and waits between requests.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div
                role="radiogroup"
                aria-label="Site"
                className="grid grid-cols-2 gap-2"
              >
                {sites.map((option) => {
                  const active = option.id === site.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      aria-label={`${option.label}, ${option.domain}`}
                      disabled={running}
                      onClick={() => chooseSite(option)}
                      className={cn(
                        "focus-visible:ring-ring rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60",
                        active
                          ? "border-primary bg-primary/5"
                          : "hover:bg-muted/60",
                      )}
                    >
                      <span className="block text-sm font-medium">
                        {option.label}
                      </span>
                      <span className="text-muted-foreground block text-xs">
                        {option.domain}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="start-url">Start page</Label>
                <Input
                  id="start-url"
                  value={startUrl}
                  onChange={(event) => setStartUrl(event.target.value)}
                  disabled={running}
                  inputMode="url"
                  aria-invalid={!urlAllowed}
                />
                {!urlAllowed && (
                  <p className="text-destructive text-xs">
                    Use a page on {domains.join(" or ")}.
                  </p>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Pages</Label>
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    value={String(maxPages)}
                    aria-label="Pages"
                    onValueChange={(value) =>
                      value && setMaxPages(Number(value))
                    }
                    disabled={running}
                    className="w-full"
                  >
                    {PAGE_OPTIONS.map((value) => (
                      <ToggleGroupItem
                        key={value}
                        value={String(value)}
                        className="border-border flex-1"
                      >
                        {value}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </div>
                <div className="space-y-1.5">
                  <Label>Follow links</Label>
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    value={String(maxDepth)}
                    aria-label="Follow links"
                    onValueChange={(value) =>
                      value && setMaxDepth(Number(value))
                    }
                    disabled={running}
                    className="w-full"
                  >
                    {DEPTH_OPTIONS.map((option) => (
                      <ToggleGroupItem
                        key={option.value}
                        value={String(option.value)}
                        className="border-border flex-1 px-1.5 text-xs"
                        aria-label={option.label}
                        title={option.label}
                      >
                        {option.value === 0 ? "None" : option.value}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="pattern">
                  Only paths like{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Input
                  id="pattern"
                  value={pattern}
                  onChange={(event) => setPattern(event.target.value)}
                  placeholder={
                    site.id === "haaga-helia"
                      ? "/fi/koulutus*"
                      : "/news-events*"
                  }
                  disabled={running}
                  className="font-mono text-sm"
                />
              </div>

              <div className="space-y-2 border-t pt-5">
                <Label htmlFor="requirements">What to extract</Label>
                <div className="flex flex-wrap gap-2">
                  {presets.map((preset) => {
                    const chosen = requirements === preset.requirements;
                    return (
                      <button
                        key={preset.label}
                        type="button"
                        aria-pressed={chosen}
                        disabled={running}
                        onClick={() => setRequirements(preset.requirements)}
                        className={cn(
                          badgeVariants({
                            variant: chosen ? "default" : "outline",
                          }),
                          "h-7 cursor-pointer px-2.5 disabled:cursor-default disabled:opacity-60",
                          !chosen && "hover:bg-muted",
                        )}
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                </div>
                <Textarea
                  id="requirements"
                  value={requirements}
                  onChange={(event) => setRequirements(event.target.value)}
                  rows={3}
                  maxLength={2000}
                  disabled={running}
                  placeholder="Leave empty to crawl only"
                />
              </div>

              {running ? (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => abortRef.current?.abort()}
                >
                  <Square className="size-4" />
                  Stop
                </Button>
              ) : (
                <Button
                  className="w-full"
                  onClick={() => void handleRun()}
                  disabled={!urlAllowed}
                >
                  <Globe className="size-4" />
                  {extracting ? "Crawl and extract" : "Crawl"}
                </Button>
              )}
            </CardContent>
          </Card>

          <HowItWorksCard description="gaik's WebScraper crawls the site; the schema generator and the extractor turn its Markdown into records.">
            <p>
              <strong>1. Allowlist and robots.txt:</strong> every request,
              redirects included, must stay on the allowed domains and public
              addresses. Pages robots.txt disallows are skipped, and requests to
              one host are spaced out.
            </p>
            <p>
              <strong>2. Breadth-first crawl:</strong> from the start page,
              links on the same host are followed level by level until the page
              limit. Links to files are not followed.
            </p>
            <p>
              <strong>3. Main content as Markdown:</strong> trafilatura drops
              navigation, banners and footers, so the text keeps the page&apos;s
              own content, with its links, tables and JSON-LD.
            </p>
            <p>
              <strong>4. Extraction with evidence:</strong> a schema is
              generated from your words, the extractor reads every page at once,
              and each value comes with a quote that is checked against the page
              it names.
            </p>
            <pre className="bg-muted text-foreground overflow-x-auto rounded-md p-3 font-mono text-xs leading-5">
              {`from gaik.software_components.web_scraper import WebScraper

with WebScraper(allowed_domains=["gaik.ai"]) as scraper:
    result = scraper.crawl("https://gaik.ai/", max_pages=6)
document = result.to_markdown()  # "Source: <url>" per page`}
            </pre>
          </HowItWorksCard>
        </div>

        <div className="min-w-0 space-y-4">
          <div
            ref={stageRef}
            className="relative h-[340px] scroll-mt-20 overflow-hidden rounded-xl border border-slate-800 bg-[radial-gradient(ellipse_at_30%_20%,#123a3a_0%,#0b1220_45%,#060a12_100%)] shadow-sm sm:h-[440px] lg:h-[500px]"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3 sm:p-4">
              <StatusLine
                phase={state.phase}
                message={state.message}
                current={current}
              />
              {state.nodes.length > 0 && (
                <dl className="flex shrink-0 gap-3 text-right text-[11px] text-slate-400">
                  <div>
                    <dt className="sr-only">Pages</dt>
                    <dd>
                      <span className="text-sm font-semibold text-slate-100 tabular-nums">
                        {pages.length}
                      </span>{" "}
                      pages
                    </dd>
                  </div>
                  <div>
                    <dt className="sr-only">Words</dt>
                    <dd>
                      <span className="text-sm font-semibold text-slate-100 tabular-nums">
                        {words.toLocaleString("en")}
                      </span>{" "}
                      words
                    </dd>
                  </div>
                  {skipped.length > 0 && (
                    <div>
                      <dt className="sr-only">Skipped</dt>
                      <dd>
                        <span className="text-sm font-semibold text-rose-300 tabular-nums">
                          {skipped.length}
                        </span>{" "}
                        skipped
                      </dd>
                    </div>
                  )}
                </dl>
              )}
            </div>
            <Constellation
              nodes={state.nodes}
              phase={state.phase}
              citations={citations}
              selected={selected}
              onSelect={select}
              className="absolute inset-0"
            />
            {state.phase === "idle" && (
              <div className="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center">
                <p className="max-w-xs text-sm text-slate-300">
                  Pages appear here as they are fetched, each linked from the
                  page it was found on.
                </p>
              </div>
            )}
            <div className="absolute right-14 bottom-3 left-3 sm:bottom-4 sm:left-4">
              <Legend />
            </div>
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="data">Data</TabsTrigger>
              <TabsTrigger value="pages">
                Pages
                {pages.length > 0 && (
                  <span className="text-muted-foreground ml-1 tabular-nums">
                    {pages.length}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="markdown">Markdown</TabsTrigger>
            </TabsList>

            <TabsContent value="data" className="mt-3">
              <Card>
                <CardContent className="space-y-4 pt-6">
                  {state.error && (
                    <p className="text-destructive flex items-start gap-2 text-sm">
                      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                      {state.error}
                    </p>
                  )}
                  {state.schema && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-muted-foreground mr-1 text-xs">
                        Fields
                      </span>
                      {state.schema
                        .flatMap((field) =>
                          field.children?.length ? field.children : [field],
                        )
                        .map((field) => (
                          <Badge
                            key={field.name}
                            variant="secondary"
                            className="font-mono text-[11px]"
                            title={field.description}
                          >
                            {field.name}
                          </Badge>
                        ))}
                    </div>
                  )}
                  {running && (
                    <p className="text-muted-foreground flex items-center gap-2 text-sm">
                      <Loader2 className="size-4 animate-spin" />
                      {state.phase === "crawling"
                        ? extracting
                          ? "Crawling. The extraction starts when the pages are in."
                          : "Crawling."
                        : state.message}
                    </p>
                  )}
                  {state.extraction && table.rows.length > 0 && (
                    <>
                      <div className="max-h-[420px] overflow-auto rounded-md border">
                        <table className="w-full text-sm">
                          <thead className="bg-muted sticky top-0 z-[1]">
                            <tr>
                              {table.columns.map((column) => (
                                <th
                                  key={column}
                                  className={cn(
                                    "px-3 py-2 text-left text-xs font-medium whitespace-nowrap",
                                    wide.has(column) && "min-w-[12rem]",
                                  )}
                                >
                                  {column.replace(/_/g, " ")}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {table.rows.map((row, index) => {
                              const page = pageOfRow(
                                state.extraction!.sources,
                                index,
                              );
                              const active =
                                !!page && selectedNode?.finalUrl === page;
                              return (
                                <tr
                                  key={index}
                                  className={cn(
                                    "border-t align-top transition-colors",
                                    active && "bg-primary/5",
                                  )}
                                  onClick={() => page && selectPage(page)}
                                >
                                  {table.columns.map((column) => {
                                    const key = `${index}:${column}`;
                                    const citation = cells.get(key);
                                    const value = row[column];
                                    return (
                                      <td key={column} className="px-3 py-2">
                                        <button
                                          type="button"
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            setCell(cell === key ? null : key);
                                            if (citation?.page_url)
                                              selectPage(citation.page_url);
                                          }}
                                          className={cn(
                                            "group focus-visible:ring-ring flex w-full items-start gap-1.5 rounded text-left focus-visible:ring-2 focus-visible:outline-none",
                                            cell === key && "text-primary",
                                          )}
                                        >
                                          {citation && (
                                            <span
                                              className={cn(
                                                "mt-1.5 size-1.5 shrink-0 rounded-full",
                                                (
                                                  VERDICTS[citation.verdict] ??
                                                  VERDICTS.unchecked
                                                ).className,
                                              )}
                                              title={
                                                (
                                                  VERDICTS[citation.verdict] ??
                                                  VERDICTS.unchecked
                                                ).label
                                              }
                                            />
                                          )}
                                          <span
                                            className={cn(
                                              "min-w-0 break-words",
                                              isUrl(value) &&
                                                "font-mono text-xs",
                                              cellText(value).length <= 16 &&
                                                "whitespace-nowrap",
                                            )}
                                          >
                                            {isUrl(value)
                                              ? shortUrl(value)
                                              : cellText(value)}
                                          </span>
                                        </button>
                                      </td>
                                    );
                                  })}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {selectedCitation ? (
                        <CitationDetail
                          citation={selectedCitation}
                          onPage={selectPage}
                        />
                      ) : (
                        <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                          <CircleHelp className="size-3.5" />
                          Click a value for its quote and the page it came from.
                        </p>
                      )}
                      <p className="text-muted-foreground text-xs">
                        {table.rows.length}{" "}
                        {table.rows.length === 1 ? "record" : "records"} from{" "}
                        {pages.length} pages (
                        {state.extraction.documentChars.toLocaleString("en")}{" "}
                        characters)
                        {state.extraction.model
                          ? ` · ${state.extraction.model}`
                          : ""}
                      </p>
                    </>
                  )}
                  {state.extraction && table.rows.length === 0 && (
                    <p className="text-muted-foreground text-sm">
                      The pages hold nothing the requirements ask for. Try other
                      pages or a wider crawl.
                    </p>
                  )}
                  {!state.extraction && !running && !state.error && (
                    <p className="text-muted-foreground text-sm">
                      {state.phase === "done"
                        ? "This run crawled only. Write what to extract and run again."
                        : "Pick what to extract, then crawl. Each value comes with the quote and page it was read from."}
                    </p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="pages" className="mt-3">
              <Card>
                <CardContent className="pt-6">
                  {state.nodes.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      No pages yet.
                    </p>
                  ) : (
                    <ul className="divide-y">
                      {state.nodes.map((node) => {
                        const active = node.url === selected;
                        return (
                          <li key={node.url}>
                            <button
                              type="button"
                              onClick={() =>
                                setSelected(active ? null : node.url)
                              }
                              className={cn(
                                "focus-visible:ring-ring flex w-full items-start gap-3 py-2.5 text-left focus-visible:ring-2 focus-visible:outline-none",
                                active && "text-primary",
                              )}
                            >
                              <span
                                className={cn(
                                  "mt-1.5 size-2 shrink-0 rounded-full",
                                  node.status === "fetching" &&
                                    "animate-pulse bg-slate-400",
                                  node.status === "skipped" && "bg-rose-400",
                                  node.status === "page" &&
                                    (node.depth === 0
                                      ? "bg-amber-400"
                                      : "bg-teal-500"),
                                )}
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-medium">
                                  {node.title || shortUrl(node.url)}
                                </span>
                                <span className="text-muted-foreground block truncate font-mono text-xs">
                                  {shortUrl(node.finalUrl)}
                                </span>
                                {node.status === "skipped" && (
                                  <span className="block text-xs text-rose-600 dark:text-rose-300">
                                    {node.reason}
                                  </span>
                                )}
                              </span>
                              {node.status === "page" && (
                                <span className="text-muted-foreground shrink-0 text-right text-xs tabular-nums">
                                  {(node.words ?? 0).toLocaleString("en")} words
                                  {citations[node.finalUrl] ? (
                                    <span className="block text-amber-600 dark:text-amber-400">
                                      {citations[node.finalUrl]} cited
                                    </span>
                                  ) : null}
                                </span>
                              )}
                            </button>
                            {active && node.status === "page" && (
                              <div className="mb-3 space-y-3 rounded-lg border p-3">
                                <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                                  {node.language && (
                                    <span>lang {node.language}</span>
                                  )}
                                  {node.published && (
                                    <span>{node.published}</span>
                                  )}
                                  <span>
                                    {node.links?.length ?? 0} internal links
                                  </span>
                                  {node.structuredDataTypes?.length ? (
                                    <span>
                                      JSON-LD:{" "}
                                      {node.structuredDataTypes.join(", ")}
                                    </span>
                                  ) : null}
                                  <a
                                    href={node.finalUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-primary inline-flex items-center gap-1 hover:underline"
                                  >
                                    Open <ExternalLink className="size-3" />
                                  </a>
                                </div>
                                <div className="max-h-80 overflow-auto pr-1">
                                  <MarkdownView
                                    blocks={parseBlocks(node.markdown ?? "")}
                                    idPrefix={`p${node.order}-`}
                                  />
                                </div>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="markdown" className="mt-3">
              <Card>
                <CardContent className="space-y-3 pt-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-muted-foreground text-xs">
                      The pages as one document, each headed by its source URL:
                      ready for an LLM or a RAG index.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!markdown}
                        onClick={() => void copyMarkdown(markdown)}
                      >
                        <Copy className="size-3.5" />
                        Copy
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!markdown}
                        onClick={() =>
                          downloadBlob(
                            markdown,
                            `${site.id}-crawl.md`,
                            "text/markdown;charset=utf-8",
                          )
                        }
                      >
                        <Download className="size-3.5" />
                        .md
                      </Button>
                    </div>
                  </div>
                  <pre className="bg-muted/50 max-h-[480px] overflow-auto rounded-md border p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                    {markdown || "No pages yet."}
                  </pre>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          {state.phase === "done" && pages.length > 0 && !state.error && (
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <Check className="size-3.5 text-teal-600" />
              Crawled {pages.length} pages in {state.stats?.durationS ?? 0} s
              {skipped.length ? `, skipped ${skipped.length}` : ""}. Click a
              node or a page to read its Markdown.
            </p>
          )}
        </div>
      </div>
    </PageTransition>
  );
}
