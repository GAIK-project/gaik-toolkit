"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { downloadBlob } from "@/lib/download";
import { takeKnowledgeHandoff } from "@/lib/knowledge-curator/handoff";
import {
  parseKnowledge,
  readKnowledge,
} from "@/lib/knowledge-curator/workspace";
import {
  assemble,
  buildRequest,
  DEFAULT_OPTIONS,
  decodeDocx,
  diagnose,
  EFFORTS,
  isSampleFile,
  knowledgeId,
  MAX_SAMPLE_BYTES,
  parseResult,
  readKnowledgeZip,
  SAMPLE_ACCEPT,
  type Effort,
  type SynthResult,
  writingOrder,
  zipReport,
} from "@/lib/knowledge-synthesis/workspace";
import { processSSEStream } from "@/lib/sse";
import { cn, formatFileSize } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  Download,
  FileArchive,
  FileText,
  Layers,
  ListChecks,
  Loader2,
  NotebookPen,
  RefreshCw,
  Search,
  Sparkles,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

import { Row, SwitchRow } from "../report-writer/components/options-form";
import {
  SectionEditor,
  effectiveId,
  type SectionRow,
} from "../report-writer/components/section-editor";
import { SectionInspector } from "./components/section-inspector";
import {
  citationCounts,
  EXAMPLES,
  figuresOf,
  sourceFilesOf,
  type SynthesisExample,
  wordCount,
} from "./synthesis-data";

const API = "/api/knowledge-synthesis";
const MAX_SECTIONS = 12; // the default server limit; the server enforces its own

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Bring the knowledge",
    text: "Send the curated facts from the Knowledge Curator, upload its .zip, or start from a ready-made set.",
  },
  {
    icon: ListChecks,
    title: "Plan the report",
    text: "Name the sections. A derived section is written last, from the sections before it. A sample report can set the shape and tone.",
  },
  {
    icon: Sparkles,
    title: "Synthesize",
    text: "A writer drafts each section from its facts only, and a second model reviews it.",
  },
  {
    icon: Search,
    title: "Read and improve",
    text: "Read the report, see which sources it cites and what the reviewer changed, edit a section, and rebuild the .docx.",
  },
];
const GUIDE_NOTES = [
  "The report is written from the facts only: it reads no sources itself. Items no source covers appear as (missing: …) markers, and unresolved conflicts show both sides.",
  "The result lives in this browser tab. Reloading or closing the tab loses it, so download the .zip first.",
];

interface Run {
  result: SynthResult;
  /** The settings this run used, to tell two runs apart when comparing them. */
  label: string;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function httpError(res: Response): Promise<Error> {
  const text = await res.text();
  let detail: unknown = text;
  try {
    const body = JSON.parse(text);
    detail = body.error ?? body.detail ?? text;
  } catch {
    // Not JSON: show the raw body.
  }
  return new Error(
    `Request failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
  );
}

const newRow = (i: number, over: Partial<SectionRow> = {}): SectionRow => ({
  key: `s${i}`, // deterministic: the first row renders on the server too
  id: "",
  title: "",
  instructions: "",
  depends_on: [],
  required_items: [],
  ...over,
});

/** A section row nobody has filled in: the empty starting row is not a defined section. */
const isBlankRow = (r: SectionRow) =>
  !r.title.trim() &&
  !r.instructions.trim() &&
  !r.id.trim() &&
  r.depends_on.length === 0 &&
  (r.required_items ?? []).every((x) => !x.trim());

const humanize = (id: string) => {
  const words = id.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

export default function KnowledgeSynthesisPage() {
  const [knowledge, setKnowledge] = useState<Record<string, string>>({});
  const [origin, setOrigin] = useState("");
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [loadingExample, setLoadingExample] = useState(false);

  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("English");
  const [instructions, setInstructions] = useState("");
  const [rows, setRows] = useState<SectionRow[]>([newRow(0)]);
  const [sample, setSample] = useState<{ name: string; file: File } | null>(
    null,
  );
  const [options, setOptions] = useState(DEFAULT_OPTIONS);

  const [run, setRun] = useState<Run | null>(null);
  const [previous, setPrevious] = useState<Run | null>(null);
  const [view, setView] = useState<"current" | "previous">("current");
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [docx, setDocx] = useState<Uint8Array<ArrayBuffer> | null>(null);
  const [docxStale, setDocxStale] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState("report");

  const [running, setRunning] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Knowledge sent from the Knowledge Curator page in this tab.
  useEffect(() => {
    const sent = takeKnowledgeHandoff();
    if (sent) {
      setKnowledge(sent);
      setOrigin("Knowledge Curator");
      toast.success("Knowledge received from the Knowledge Curator.");
    }
  }, []);

  const knowledgePaths = Object.keys(knowledge).sort();
  const knowledgeIds = knowledgePaths.map(knowledgeId);
  const defined = rows.filter((r) => !isBlankRow(r));
  const inputs = defined.map((r) => ({
    id: effectiveId(r),
    title: r.title,
    instructions: r.instructions,
    required_items: r.required_items ?? [],
    depends_on: r.depends_on,
  }));
  // Nothing is checked until there is knowledge and at least one defined section: an empty
  // starting row or a missing input is a prompt to the user, not an error.
  const problems =
    knowledgePaths.length > 0 && inputs.length > 0
      ? diagnose(inputs, knowledgeIds, MAX_SECTIONS)
      : [];
  const order = inputs.length > 0 ? writingOrder(inputs) : null;
  const titleOf = (id: string) => inputs.find((s) => s.id === id)?.title || id;
  const busy = running || rebuilding || loadingExample;
  const ready =
    knowledgePaths.length > 0 &&
    problems.length === 0 &&
    title.trim().length > 0;
  const sourceFiles = sourceFilesOf(Object.values(knowledge));

  function resetResult() {
    setRun(null);
    setPrevious(null);
    setView("current");
    setTexts({});
    setDocx(null);
    setDocxStale(false);
    setSelected(null);
    setTab("report");
    setProgress([]);
    setError(null);
  }

  function confirmReplace(what: string): boolean {
    return (
      !run || window.confirm(`${what} clears the current report. Continue?`)
    );
  }

  async function loadZip(file: File) {
    if (!confirmReplace("Loading a zip")) return;
    try {
      const loaded = readKnowledgeZip(new Uint8Array(await file.arrayBuffer()));
      resetResult();
      setKnowledge(loaded);
      setOrigin(file.name);
      setExampleId(null);
      toast.success(
        `Loaded knowledge for ${Object.keys(loaded).length} topic(s).`,
      );
    } catch (e) {
      toast.error(message(e), { duration: 8000 });
    }
  }

  async function pickExample(example: SynthesisExample) {
    if (busy || !confirmReplace("Loading an example")) return;
    setLoadingExample(true);
    try {
      const response = await fetch(example.url);
      if (!response.ok)
        throw new Error(`Failed to load the knowledge (${response.status})`);
      const loaded = parseKnowledge(await response.json());
      resetResult();
      setKnowledge(loaded);
      setOrigin(example.title);
      setTitle(example.reportTitle);
      setLanguage(example.language);
      setInstructions(example.instructions);
      setRows(example.sections.map((s, i) => newRow(i, { ...s })));
      setSample(
        example.sample
          ? {
              name: example.sample.name,
              file: new File([example.sample.text], example.sample.name, {
                type: "text/markdown",
              }),
            }
          : null,
      );
      setExampleId(example.id);
    } catch (e) {
      toast.error(`Loading the example failed: ${message(e)}`);
    } finally {
      setLoadingExample(false);
    }
  }

  function startFromKnowledge() {
    setRows(
      knowledgeIds.map((id, i) => newRow(i, { id, title: humanize(id) })),
    );
    if (!title.trim()) setTitle("Report");
  }

  function clearAll() {
    if (!confirmReplace("Clearing")) return;
    setKnowledge({});
    setOrigin("");
    setExampleId(null);
    setTitle("");
    setLanguage("English");
    setInstructions("");
    setRows([newRow(0)]);
    setSample(null);
    setOptions(DEFAULT_OPTIONS);
    resetResult();
  }

  function pickSample(file: File) {
    if (!isSampleFile(file.name)) {
      toast.error(
        `The sample report must be a ${SAMPLE_ACCEPT.replaceAll(",", ", ")} file.`,
      );
      return;
    }
    if (file.size > MAX_SAMPLE_BYTES) {
      toast.error("The sample report is over 1 MB.");
      return;
    }
    setSample({ name: file.name, file });
  }

  async function synthesize() {
    if (busy || !ready) return;
    if (
      run &&
      Object.keys(texts).length > 0 &&
      !window.confirm(
        "Synthesizing again replaces the report, including your text edits. Continue?",
      )
    )
      return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setProgress([]);
    setRunning(true);
    try {
      const form = new FormData();
      form.append(
        "request",
        JSON.stringify(
          buildRequest(title, language, instructions, inputs, options),
        ),
      );
      form.append(
        "artifacts",
        new Blob([JSON.stringify(knowledge)], { type: "application/json" }),
        "artifacts.json",
      );
      if (sample) form.append("sample_report", sample.file, sample.name);
      const response = await apiFetch(`${API}/run`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (!response.ok) throw await httpError(response);

      const results: unknown[] = [];
      const errors: string[] = [];
      await processSSEStream<unknown>(response, {
        onResult: (data) => results.push(data),
        onError: (msg) => errors.push(msg),
        onCustomEvent: (event) => {
          if (event.type === "progress")
            setProgress((p) => [...p, String(event.data.message)]);
          else
            errors.push(`Unexpected "${event.type}" event from the backend.`);
        },
      });
      const raw = results.at(-1);
      if (raw) {
        const result = parseResult(raw);
        // Keep the last report so the effect of a setting can be compared.
        if (run) setPrevious(run);
        setRun({
          result,
          label: `citations ${options.citations ? "on" : "off"} · sample report: ${sample?.name ?? "none"} · ${language.trim() || "English"}`,
        });
        setView("current");
        setTexts({});
        setDocx(result.docx_b64 ? decodeDocx(result.docx_b64) : null);
        setDocxStale(false);
        setSelected(result.sections[0]?.id ?? null);
        setTab("report");
        if (result.docx_error)
          toast.error(
            "The report was written, but the .docx could not be built.",
            {
              duration: 8000,
            },
          );
      }
      if (errors.length) throw new Error(errors.join("\n"));
      if (!raw) throw new Error("Synthesize ended without a result.");
      toast.success("Report written");
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return; // apiFetch already showed a toast
      setError(message(e));
    } finally {
      setRunning(false);
    }
  }

  const sections = run
    ? run.result.sections.map((s) => ({ ...s, text: texts[s.id] ?? s.text }))
    : [];

  async function rebuild() {
    if (!run || busy) return;
    setRebuilding(true);
    setError(null);
    try {
      const form = new FormData();
      form.append(
        "request",
        JSON.stringify({
          title: run.result.title,
          sections: sections.map(({ id, title, text }) => ({
            id,
            title,
            text,
          })),
          docx: options.docx,
        }),
      );
      const response = await apiFetch(`${API}/rebuild`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw await httpError(response);
      const body = (await response.json()) as {
        docx_b64: string | null;
        docx_error: string | null;
      };
      setDocx(body.docx_b64 ? decodeDocx(body.docx_b64) : null);
      setDocxStale(false);
      if (body.docx_error)
        toast.error(`The .docx could not be built: ${body.docx_error}`, {
          duration: 8000,
        });
      else toast.success("Report rebuilt from your edits");
    } catch (e) {
      if (e instanceof RateLimitError) return;
      setError(message(e));
    } finally {
      setRebuilding(false);
    }
  }

  function saveText(id: string, text: string) {
    setTexts((t) => ({ ...t, [id]: text }));
    setDocxStale(true);
    toast.success("Saved. Rebuild the report to update the .docx.");
  }

  function resetText(id: string) {
    setTexts((t) => {
      const { [id]: _dropped, ...rest } = t;
      return rest;
    });
    setDocxStale(true);
  }

  const shown = view === "previous" && previous ? previous : run;
  const markdown =
    view === "previous" && previous
      ? previous.result.markdown
      : run
        ? assemble(run.result.title, sections)
        : "";
  const selectedSection = sections.find((s) => s.id === selected);
  const selectedInput = inputs.find((s) => s.id === selected);
  const selectedKnowledge = (() => {
    const text = selected ? knowledge[`knowledge/${selected}.json`] : undefined;
    const read = text ? readKnowledge(text) : null;
    return read?.ok ? read.value : null;
  })();
  const figures = figuresOf(sections, sourceFiles);
  const cited = citationCounts(markdown, sourceFiles);
  const reviewApplied =
    run?.result.review_log.reduce((n, r) => n + r.applied.length, 0) ?? 0;
  const reviewNotApplied =
    run?.result.review_log.reduce((n, r) => n + r.unresolved.length, 0) ?? 0;
  const totalMissing = figures.reduce((n, f) => n + f.missing, 0);

  return (
    <PageTransition>
      <DemoPageHeader
        icon={NotebookPen}
        title="Knowledge Synthesis"
        description="Write a reviewed, source-grounded report from the facts curated in the Knowledge Curator."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Knowledge Synthesis"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from ready-made knowledge and a report plan
          </h2>
          <div
            role="radiogroup"
            aria-label="Ready-made sets"
            className="grid gap-3 sm:grid-cols-2"
          >
            {EXAMPLES.map((example) => (
              <button
                key={example.id}
                type="button"
                role="radio"
                aria-checked={exampleId === example.id}
                disabled={busy}
                onClick={() => void pickExample(example)}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                  exampleId === example.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <span className="font-semibold">{example.title}</span>
                <span className="text-muted-foreground text-sm">
                  {example.summary}
                </span>
                <span className="flex flex-wrap gap-1">
                  {example.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="font-normal">
                      {tag}
                    </Badge>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0">
                <div className="min-w-[12rem] flex-1">
                  <CardTitle>1. Curated knowledge</CardTitle>
                  <CardDescription>
                    The facts the report is written from. Send them from the{" "}
                    <Link href="/knowledge-curator" className="underline">
                      Knowledge Curator
                    </Link>
                    , or upload its .zip.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={clearAll}
                  disabled={busy || (knowledgePaths.length === 0 && !title)}
                >
                  Clear
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                {loadingExample && (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading the knowledge…
                  </p>
                )}
                {knowledgePaths.length > 0 ? (
                  <>
                    <p className="text-muted-foreground text-xs">
                      From {origin || "an upload"}: knowledge for{" "}
                      {knowledgePaths.length} topic
                      {knowledgePaths.length === 1 ? "" : "s"}
                    </p>
                    <ul className="space-y-1.5">
                      {knowledgePaths.map((path) => {
                        const read = readKnowledge(knowledge[path]);
                        return (
                          <li
                            key={path}
                            className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                          >
                            <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                            <span className="flex-1 truncate font-mono text-xs">
                              {knowledgeId(path)}
                            </span>
                            <span className="text-muted-foreground shrink-0 text-xs">
                              {read.ok
                                ? `${read.value.units.length} facts · ${read.value.missing.length} missing · ${read.value.conflicts.length} conflicts`
                                : "invalid JSON"}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : (
                  <p className="text-xs font-medium text-amber-700">
                    No knowledge yet. Pick a ready-made set above, or add
                    knowledge from the Knowledge Curator.
                  </p>
                )}
                <label
                  className={cn(
                    "text-muted-foreground hover:border-primary/50 flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-4 text-sm transition-colors",
                    busy && "pointer-events-none opacity-50",
                  )}
                >
                  <Upload className="h-4 w-4" />
                  {knowledgePaths.length
                    ? "Replace with a .zip"
                    : "Upload the .zip from the Knowledge Curator"}
                  <input
                    type="file"
                    accept=".zip,application/zip"
                    className="sr-only"
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) void loadZip(file);
                    }}
                  />
                </label>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>2. The report</CardTitle>
                <CardDescription>
                  Its title and language, the rules for every section, and an
                  optional sample report to copy the shape of.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
                  <div className="space-y-1">
                    <Label htmlFor="ks-title" className="text-sm">
                      Report title
                    </Label>
                    <Input
                      id="ks-title"
                      value={title}
                      disabled={busy}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="e.g. Site report, 12 Example Road"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="ks-language" className="text-sm">
                      Language
                    </Label>
                    <Input
                      id="ks-language"
                      value={language}
                      disabled={busy}
                      onChange={(e) => setLanguage(e.target.value)}
                      placeholder="English"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="ks-instructions" className="text-sm">
                    Report instructions
                  </Label>
                  <Textarea
                    id="ks-instructions"
                    value={instructions}
                    disabled={busy}
                    onChange={(e) => setInstructions(e.target.value)}
                    placeholder="Rules for every section: which source to trust, tone, how to cite."
                    className="min-h-[96px] text-sm"
                  />
                </div>

                <div className="space-y-1">
                  <Label className="text-sm">
                    Sample report{" "}
                    <span className="text-muted-foreground font-normal">
                      (optional; the report copies its structure, length and
                      tone, never its facts)
                    </span>
                  </Label>
                  {sample && (
                    <div className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                      <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                      <span className="flex-1 truncate">{sample.name}</span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {formatFileSize(sample.file.size)}
                      </span>
                      <button
                        type="button"
                        title="Remove"
                        aria-label="Remove the sample report"
                        disabled={busy}
                        onClick={() => setSample(null)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                  <label
                    className={cn(
                      "text-muted-foreground hover:border-muted-foreground/50 flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm transition-colors",
                      busy && "pointer-events-none opacity-50",
                    )}
                  >
                    <Upload className="h-4 w-4" />
                    {sample
                      ? "Replace the sample report"
                      : "Upload a sample report (.md, .txt, .docx, .pdf)"}
                    <input
                      type="file"
                      accept={SAMPLE_ACCEPT}
                      className="sr-only"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        e.target.value = "";
                        if (file) pickSample(file);
                      }}
                    />
                  </label>
                </div>
              </CardContent>
            </Card>
            <Card>
              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="options" className="border-none">
                  <AccordionTrigger className="text-muted-foreground hover:text-foreground px-6 py-4 text-left text-sm font-medium hover:no-underline">
                    <div>
                      4. Options
                      <p className="text-muted-foreground mt-1 text-sm font-normal">
                        Citations, review, models and output
                      </p>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="space-y-3 px-6 pb-5">
                    <SwitchRow
                      label="Citations"
                      description="Cite the source file and place of each fact. Off writes plain statements, even if the report instructions ask for citations. Run twice to compare."
                      checked={options.citations}
                      onCheckedChange={(v) =>
                        setOptions({ ...options, citations: v })
                      }
                      disabled={busy}
                    />
                    <SwitchRow
                      label="Strict review"
                      description="Stop the run when a reviewer correction cannot be applied"
                      checked={options.strict_review}
                      onCheckedChange={(v) =>
                        setOptions({ ...options, strict_review: v })
                      }
                      disabled={busy}
                    />
                    <SwitchRow
                      label="Generate DOCX"
                      description="Also build report.docx next to the Markdown"
                      checked={options.docx}
                      onCheckedChange={(v) =>
                        setOptions({ ...options, docx: v })
                      }
                      disabled={busy}
                    />
                    <Row label="Review attempts">
                      <Input
                        type="number"
                        min={1}
                        max={5}
                        value={options.review_attempts}
                        disabled={busy}
                        onChange={(e) =>
                          setOptions({
                            ...options,
                            review_attempts: Math.min(
                              5,
                              Math.max(1, Number(e.target.value) || 1),
                            ),
                          })
                        }
                        className="h-8 text-sm"
                      />
                    </Row>
                    {(["writer", "reviewer"] as const).map((step) => (
                      <div key={step} className="space-y-3">
                        <p className="text-muted-foreground text-xs font-medium capitalize">
                          {step}
                        </p>
                        <Row label="Model">
                          <Input
                            placeholder="The server's model"
                            value={options[`${step}_model`] ?? ""}
                            disabled={busy}
                            onChange={(e) =>
                              setOptions({
                                ...options,
                                [`${step}_model`]: e.target.value,
                              })
                            }
                            className="h-8 font-mono text-sm"
                          />
                        </Row>
                        <Row label="Reasoning effort">
                          <Select
                            value={options[`${step}_effort`] ?? "default"}
                            disabled={busy}
                            onValueChange={(v) =>
                              setOptions({
                                ...options,
                                [`${step}_effort`]:
                                  v === "default" ? null : (v as Effort),
                              })
                            }
                          >
                            <SelectTrigger className="h-8 text-sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="default">
                                model default
                              </SelectItem>
                              {EFFORTS.map((e) => (
                                <SelectItem key={e} value={e}>
                                  {e}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </Row>
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
              <CardContent className="space-y-2 pt-0">
                <div className="flex gap-2">
                  <Button
                    size="lg"
                    className="flex-1"
                    onClick={synthesize}
                    disabled={busy || !ready}
                  >
                    {running ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="mr-2 h-4 w-4" />
                    )}
                    {running ? "Writing the report…" : "Synthesize"}
                  </Button>
                  {running && (
                    <Button
                      variant="outline"
                      size="lg"
                      onClick={() => abortRef.current?.abort()}
                    >
                      <X className="mr-2 h-4 w-4" />
                      Cancel
                    </Button>
                  )}
                </div>
                {!ready && !running && (
                  <p className="text-muted-foreground text-xs">
                    {knowledgePaths.length === 0
                      ? "Add knowledge first: pick a ready-made set, or use the Knowledge Curator."
                      : inputs.length === 0
                        ? "Define the sections of the report first."
                        : !title.trim()
                          ? "Give the report a title."
                          : problems.length > 0
                            ? "Fix the problems listed under the sections."
                            : ""}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0">
                <div className="min-w-[12rem] flex-1">
                  <CardTitle>3. Sections</CardTitle>
                  <CardDescription>
                    A section without dependencies is written from the knowledge
                    with the same id. A section that depends on others is{" "}
                    <strong>derived</strong>: it is written from their finished
                    text and needs no knowledge of its own.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startFromKnowledge}
                  disabled={busy || knowledgePaths.length === 0}
                  title="Create one section for each knowledge file"
                >
                  Start from the knowledge
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <SectionEditor
                  sections={rows}
                  onChange={setRows}
                  disabled={busy}
                  withRequiredItems
                />

                {inputs.length === 0 && (
                  <p className="text-xs font-medium text-amber-700">
                    No sections defined yet. Define your sections above, pick a
                    ready-made set, or start from the knowledge.
                  </p>
                )}

                {problems.length > 0 && (
                  <ul className="text-destructive space-y-1 text-xs">
                    {problems.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                )}

                {order && (
                  <div className="bg-muted/30 space-y-1.5 rounded-md border p-3">
                    <p className="flex items-center gap-1.5 text-xs font-medium">
                      <Layers className="h-3.5 w-3.5" />
                      Writing order
                    </p>
                    {order.map((level, i) => (
                      <div
                        key={i}
                        className="flex flex-wrap items-center gap-1.5 text-xs"
                      >
                        <span className="text-muted-foreground w-14 shrink-0">
                          Step {i + 1}
                        </span>
                        {level.map((id) => {
                          const deps =
                            inputs.find((s) => s.id === id)?.depends_on ?? [];
                          return (
                            <Badge
                              key={id}
                              variant="outline"
                              className="gap-1 font-normal"
                            >
                              {titleOf(id)}
                              {deps.length > 0 && (
                                <span className="text-muted-foreground">
                                  ← {deps.map(titleOf).join(", ")}
                                </span>
                              )}
                            </Badge>
                          );
                        })}
                        <span className="text-muted-foreground">
                          {i === 0
                            ? "from the knowledge, in parallel"
                            : "from the text of the sections before"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="space-y-4" aria-live="polite">
          {progress.length > 0 && (
            <Card>
              <CardContent className="space-y-2 py-4">
                <p className="text-sm font-medium">
                  {running ? "Writing and reviewing…" : "Done"}
                </p>
                <div className="max-h-32 space-y-0.5 overflow-y-auto text-xs">
                  {progress.map((m, i) => (
                    <p key={i} className="flex items-center gap-1.5">
                      {running && i === progress.length - 1 ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Check className="h-3 w-3 text-emerald-600" />
                      )}
                      {m}
                    </p>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-xs whitespace-pre-wrap">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {run && shown ? (
            <Card>
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="min-w-[12rem] flex-1">
                    <CardTitle>{run.result.title}</CardTitle>
                    <CardDescription>{shown.label}</CardDescription>
                  </div>
                  <div className="flex max-w-full flex-wrap items-center justify-end gap-1.5">
                    {(docxStale || rebuilding) && view === "current" && (
                      <Button size="sm" onClick={rebuild} disabled={busy}>
                        {rebuilding ? (
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="mr-1 h-3.5 w-3.5" />
                        )}
                        Rebuild report
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        downloadBlob(markdown, "report.md", "text/markdown")
                      }
                    >
                      <Download className="mr-1 h-3.5 w-3.5" />
                      .md
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!docx || view === "previous" || docxStale}
                      title={
                        run.result.docx_error
                          ? run.result.docx_error
                          : !docx
                            ? "No .docx was built"
                            : docxStale
                              ? "Out of date: rebuild the report first"
                              : ""
                      }
                      onClick={() =>
                        docx &&
                        downloadBlob(
                          docx,
                          "report.docx",
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                      }
                    >
                      <Download className="mr-1 h-3.5 w-3.5" />
                      .docx
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        downloadBlob(
                          new Uint8Array(
                            zipReport(
                              run.result.title,
                              sections,
                              run.result.review_log,
                              docxStale ? null : docx,
                            ),
                          ),
                          "report.zip",
                          "application/zip",
                        )
                      }
                    >
                      <FileArchive className="mr-1 h-3.5 w-3.5" />
                      .zip
                    </Button>
                    <FeedbackButton demoType="knowledge-synthesis" />
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Badge variant="outline" className="font-normal">
                    {sections.length} sections
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {wordCount(markdown).toLocaleString()} words
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {cited.reduce((n, [, c]) => n + c, 0)} citations
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {reviewApplied} review edits applied
                    {reviewNotApplied > 0 &&
                      `, ${reviewNotApplied} not applied`}
                  </Badge>
                  {totalMissing > 0 && (
                    <Badge
                      variant="outline"
                      className="border-amber-500 font-normal text-amber-700"
                    >
                      {totalMissing} missing markers
                    </Badge>
                  )}
                  <Badge variant="outline" className="font-normal">
                    {Object.entries(run.result.usage)
                      .map(([k, v]) => `${k} ${v.toLocaleString()}`)
                      .join(" · ") || "no token counts reported"}
                  </Badge>
                </div>
                {previous && (
                  <div className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="text-muted-foreground">Compare:</span>
                    <Button
                      size="xs"
                      variant={view === "current" ? "default" : "outline"}
                      onClick={() => setView("current")}
                    >
                      This run
                    </Button>
                    <Button
                      size="xs"
                      variant={view === "previous" ? "default" : "outline"}
                      onClick={() => setView("previous")}
                    >
                      Previous run
                    </Button>
                  </div>
                )}
                {docxStale && view === "current" && (
                  <p className="text-xs text-amber-600">
                    Your text edits are in the preview and the .md, but not yet
                    in the .docx. Rebuild the report to update it.
                  </p>
                )}
                {run.result.docx_error && (
                  <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription className="text-xs">
                      The .docx could not be built: {run.result.docx_error}
                    </AlertDescription>
                  </Alert>
                )}
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
                <div className="space-y-4">
                  <div className="space-y-1">
                    <p className="text-sm font-semibold">Sections</p>
                    <ul className="space-y-1">
                      {sections.map((s) => {
                        const input = inputs.find((i) => i.id === s.id);
                        const derived = (input?.depends_on.length ?? 0) > 0;
                        const entry = run.result.review_log.find(
                          (r) => r.section_id === s.id,
                        );
                        const figure = figures.find((f) => f.id === s.id);
                        return (
                          <li key={s.id}>
                            <button
                              type="button"
                              onClick={() => {
                                setSelected(s.id);
                                setTab("section");
                              }}
                              aria-current={s.id === selected}
                              className={cn(
                                "hover:bg-muted flex w-full flex-col gap-1 rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                                s.id === selected &&
                                  "border-primary bg-primary/5",
                              )}
                            >
                              <span className="flex items-center gap-1.5">
                                <span className="min-w-0 flex-1 truncate font-medium">
                                  {s.title}
                                </span>
                                <Badge
                                  variant="outline"
                                  className="text-[10px]"
                                >
                                  {derived ? "derived" : "from knowledge"}
                                </Badge>
                              </span>
                              <span className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5">
                                <span>{figure?.words ?? 0} words</span>
                                <span>{figure?.citations ?? 0} citations</span>
                                {entry && (
                                  <span>
                                    {entry.applied.length} edit
                                    {entry.applied.length === 1 ? "" : "s"}
                                    {entry.unresolved.length > 0 &&
                                      `, ${entry.unresolved.length} not applied`}
                                  </span>
                                )}
                                {(figure?.missing ?? 0) > 0 && (
                                  <span className="text-amber-700">
                                    {figure?.missing} missing
                                  </span>
                                )}
                                {texts[s.id] !== undefined && (
                                  <span className="text-amber-700">edited</span>
                                )}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <div className="space-y-1">
                    <p className="text-sm font-semibold">Sources cited</p>
                    {cited.length === 0 ? (
                      <p className="text-muted-foreground text-xs">
                        {options.citations
                          ? "No source file is named in the report."
                          : "Citations are off, so the report names no sources."}
                      </p>
                    ) : (
                      <ul className="space-y-1">
                        {cited.map(([file, count]) => (
                          <li
                            key={file}
                            className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs"
                          >
                            <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                            <span className="min-w-0 flex-1 truncate font-mono">
                              {file}
                            </span>
                            <Badge variant="secondary" className="font-normal">
                              {count}×
                            </Badge>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                <div className="min-w-0">
                  <Tabs value={tab} onValueChange={setTab}>
                    <TabsList>
                      <TabsTrigger value="report">Report</TabsTrigger>
                      <TabsTrigger value="section">
                        {selectedSection
                          ? `Section: ${selectedSection.title}`
                          : "Section"}
                      </TabsTrigger>
                      <TabsTrigger value="markdown">Markdown</TabsTrigger>
                    </TabsList>
                    <TabsContent value="report" className="mt-3">
                      <div className="max-h-[40rem] overflow-y-auto rounded-md border p-4">
                        <MessageResponse className="text-sm">
                          {markdown}
                        </MessageResponse>
                      </div>
                    </TabsContent>
                    <TabsContent value="section" className="mt-3">
                      {selectedSection ? (
                        <SectionInspector
                          key={selectedSection.id}
                          section={selectedSection}
                          original={
                            run.result.sections.find(
                              (s) => s.id === selectedSection.id,
                            )?.text ?? ""
                          }
                          derived={(selectedInput?.depends_on.length ?? 0) > 0}
                          knowledge={selectedKnowledge}
                          prerequisites={(selectedInput?.depends_on ?? []).map(
                            (id) => ({ id, title: titleOf(id) }),
                          )}
                          review={run.result.review_log.find(
                            (r) => r.section_id === selectedSection.id,
                          )}
                          citations={options.citations}
                          disabled={busy || view === "previous"}
                          onSaveText={saveText}
                          onResetText={resetText}
                        />
                      ) : (
                        <p className="text-muted-foreground text-sm">
                          Pick a section on the left.
                        </p>
                      )}
                    </TabsContent>
                    <TabsContent value="markdown" className="mt-3">
                      <pre className="bg-muted/30 max-h-[40rem] overflow-auto rounded-md border p-4 font-mono text-xs whitespace-pre-wrap">
                        {markdown}
                      </pre>
                    </TabsContent>
                  </Tabs>
                </div>
              </CardContent>
            </Card>
          ) : (
            !running &&
            progress.length === 0 && (
              <EmptyStateCard
                icon={Wand2}
                title="No report yet"
                description="Pick a ready-made set, or load knowledge and define sections, then click Synthesize. The report appears here with the sources it cites and what the reviewer changed."
                feedbackSlot={<FeedbackButton demoType="knowledge-synthesis" />}
              />
            )
          )}
        </div>
      </div>
    </PageTransition>
  );
}
