"use client";

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
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { downloadBlob as download } from "@/lib/download";
import { putKnowledgeHandoff } from "@/lib/knowledge-curator/handoff";
import {
  buildRequest,
  DEFAULT_OPTIONS,
  EFFORTS,
  knowledgePath,
  parseKnowledge,
  readKnowledge,
  readWorkspaceZip,
  sectionsProblem,
  zipWorkspace,
  type DroppedUnit,
  type Effort,
  type SectionKnowledge,
  type VerifyResult,
} from "@/lib/knowledge-curator/workspace";
import { processSSEStream } from "@/lib/sse";
import { takeHandoff } from "@/lib/source-normalizer/handoff";
import {
  parseArtifacts,
  readManifest,
} from "@/lib/source-normalizer/workspace";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Download,
  FileArchive,
  FileText,
  LibraryBig,
  ListChecks,
  Loader2,
  NotebookPen,
  Pencil,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

import {
  SectionEditor,
  effectiveId,
  type SectionRow,
} from "../report-writer/components/section-editor";
import { FactsExplorer } from "./components/facts-explorer";
import { EXAMPLES, totalsOf, type CuratorExample } from "./curator-data";

const API = "/api/knowledge-curator";
const MAX_SECTIONS = 12; // the default server limit; the server enforces its own

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Bring the sources",
    text: "Send them from the Source Normalizer, upload its .zip, or start from a ready-made set.",
  },
  {
    icon: ListChecks,
    title: "Define the topics",
    text: "A topic is a subject to collect facts about, with the items it must cover.",
  },
  {
    icon: Sparkles,
    title: "Curate",
    text: "A model reads the sources and writes facts. Each fact has an exact quote, its file and its place.",
  },
  {
    icon: Search,
    title: "Explore and check",
    text: "Filter the facts, see each quote in its source, follow conflicts and missing items, edit, and verify the quotes.",
  },
];
const GUIDE_NOTES = [
  "Every quote must appear word for word in its source. A fact whose quote is not there, even after asking again, is dropped and listed. The instructions decide whether a conflict between sources is resolved: for example, primary sources outrank secondary ones.",
  "The result lives in this browser tab. Reloading or closing the tab loses it, so download the .zip first.",
];

interface RunResult {
  artifacts: unknown;
  usage: Record<string, number>;
  dropped: DroppedUnit[];
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

/** A section row nobody has filled in: the empty starting row is not a defined section. */
const isBlankRow = (r: SectionRow) =>
  !r.title.trim() &&
  !r.instructions.trim() &&
  !r.id.trim() &&
  r.depends_on.length === 0 &&
  (r.required_items ?? []).every((x) => !x.trim());

const newRow = (i: number, over: Partial<SectionRow> = {}): SectionRow => ({
  key: `s${i}`, // deterministic: the first row renders on the server too
  id: "",
  title: "",
  instructions: "",
  depends_on: [],
  required_items: [],
  ...over,
});

export default function KnowledgeCuratorPage() {
  const router = useRouter();
  const [normalized, setNormalized] = useState<Record<string, string> | null>(
    null,
  );
  const [origin, setOrigin] = useState("");
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [loadingExample, setLoadingExample] = useState(false);
  const [sections, setSections] = useState<SectionRow[]>([newRow(0)]);
  const [instructions, setInstructions] = useState("");
  const [options, setOptions] = useState(DEFAULT_OPTIONS);

  const [knowledge, setKnowledge] = useState<Record<string, string>>({});
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [dropped, setDropped] = useState<DroppedUnit[]>([]);
  const [usage, setUsage] = useState<Record<string, number> | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);

  const [running, setRunning] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // A result sent from the Source Normalizer page in this tab.
  useEffect(() => {
    const sent = takeHandoff();
    if (sent) {
      setNormalized(sent);
      setOrigin("Source Normalizer");
      toast.success("Sources received from the Source Normalizer.");
    }
  }, []);

  const files = (() => {
    if (!normalized) return [];
    try {
      return readManifest(normalized);
    } catch {
      return [];
    }
  })();
  const knowledgePaths = Object.keys(knowledge).sort();
  const busy = running || verifying || loadingExample;
  const inputs = sections.map((s) => ({
    id: effectiveId(s),
    title: s.title,
    instructions: s.instructions,
    required_items: s.required_items ?? [],
  }));
  const problem = sectionsProblem(inputs, MAX_SECTIONS);
  const started = sections.some((s) => !isBlankRow(s));
  const readable: SectionKnowledge[] = knowledgePaths.flatMap((path) => {
    const read = readKnowledge(knowledge[path]);
    return read.ok ? [read.value] : [];
  });
  const totals = totalsOf(readable);
  const failuresOf = (path: string) =>
    (verify?.failures ?? []).filter(
      (f) => knowledgePath(f.section_id) === path,
    );
  const selectedText = selected ? knowledge[selected] : undefined;

  function resetResult() {
    setKnowledge({});
    setEdited(new Set());
    setDropped([]);
    setUsage(null);
    setVerify(null);
    setSelected(null);
    setDraft(null);
    setProgress([]);
    setError(null);
  }

  function confirmReplace(what: string): boolean {
    return (
      knowledgePaths.length === 0 ||
      window.confirm(`${what} clears the current knowledge. Continue?`)
    );
  }

  async function pickExample(example: CuratorExample) {
    if (busy || !confirmReplace("Loading an example")) return;
    setLoadingExample(true);
    try {
      const response = await fetch(example.url);
      if (!response.ok)
        throw new Error(`Failed to load the sources (${response.status})`);
      const artifacts = parseArtifacts(await response.json());
      resetResult();
      setNormalized(artifacts);
      setOrigin(example.title);
      setSections(example.sections.map((s, i) => newRow(i, { ...s })));
      setInstructions(example.instructions);
      setExampleId(example.id);
    } catch (e) {
      toast.error(`Loading the example failed: ${message(e)}`);
    } finally {
      setLoadingExample(false);
    }
  }

  function clearAll() {
    if (!confirmReplace("Clearing")) return;
    setNormalized(null);
    setOrigin("");
    setExampleId(null);
    setSections([newRow(0)]);
    setInstructions("");
    setOptions(DEFAULT_OPTIONS);
    resetResult();
  }

  async function loadZip(file: File) {
    if (!confirmReplace("Loading a zip")) return;
    try {
      const loaded = readWorkspaceZip(new Uint8Array(await file.arrayBuffer()));
      resetResult();
      setNormalized(loaded.normalized);
      setOrigin(file.name);
      setExampleId(null);
      const paths = Object.keys(loaded.knowledge);
      if (paths.length) {
        setKnowledge(loaded.knowledge);
        setSelected(paths.sort()[0]);
      }
      toast.success(
        paths.length
          ? `Loaded ${file.name} with ${paths.length} knowledge file(s).`
          : `Loaded ${file.name}.`,
      );
    } catch (e) {
      toast.error(message(e), { duration: 8000 });
    }
  }

  async function curate() {
    if (busy || !normalized) return;
    if (problem) {
      toast.error(problem);
      return;
    }
    if (
      knowledgePaths.length > 0 &&
      !window.confirm(
        "Curating again replaces the knowledge, including your edits. Continue?",
      )
    )
      return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    resetResult();
    setRunning(true);
    try {
      const form = new FormData();
      form.append(
        "request",
        JSON.stringify(buildRequest(inputs, instructions, options)),
      );
      form.append(
        "artifacts",
        new Blob([JSON.stringify(normalized)], { type: "application/json" }),
        "artifacts.json",
      );
      const response = await apiFetch(`${API}/run`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (!response.ok) throw await httpError(response);

      const results: RunResult[] = [];
      const errors: string[] = [];
      await processSSEStream<RunResult>(response, {
        onResult: (data) => results.push(data),
        onError: (msg) => errors.push(msg),
        onCustomEvent: (event) => {
          if (event.type === "progress")
            setProgress((p) => [...p, String(event.data.message)]);
          else
            errors.push(`Unexpected "${event.type}" event from the backend.`);
        },
      });
      const result = results.at(-1);
      if (result) {
        if (!result.usage || typeof result.usage !== "object")
          throw new Error("The result has no usage.");
        if (!Array.isArray(result.dropped))
          throw new Error("The result has no list of dropped facts.");
        const next = parseKnowledge(result.artifacts);
        setKnowledge(next);
        setUsage(result.usage);
        setDropped(result.dropped);
        setSelected(Object.keys(next).sort()[0] ?? null);
      }
      if (errors.length) throw new Error(errors.join("\n"));
      if (!result) throw new Error("Curate ended without a result.");
      toast.success("Knowledge curated");
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return; // apiFetch already showed a toast
      setError(message(e));
    } finally {
      setRunning(false);
    }
  }

  async function verifyQuotes() {
    if (busy || !normalized || knowledgePaths.length === 0) return;
    setVerifying(true);
    setError(null);
    try {
      const form = new FormData();
      form.append(
        "artifacts",
        new Blob([JSON.stringify({ ...normalized, ...knowledge })], {
          type: "application/json",
        }),
        "artifacts.json",
      );
      const response = await apiFetch(`${API}/verify`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw await httpError(response);
      const result = (await response.json()) as VerifyResult;
      if (typeof result?.units !== "number" || !Array.isArray(result.failures))
        throw new Error("The verify response is malformed.");
      setVerify(result);
      if (result.failures.length === 0)
        toast.success(`All ${result.units} quotes are in their sources.`);
      else
        toast.error(
          `${result.failures.length} of ${result.units} quotes are not in their sources.`,
        );
    } catch (e) {
      if (e instanceof RateLimitError) return;
      setError(message(e));
    } finally {
      setVerifying(false);
    }
  }

  function saveDraft() {
    if (selected === null || draft === null) return;
    const parsed = readKnowledge(draft);
    if (!parsed.ok) {
      setDraftError(`Not saved: ${parsed.error}`);
      return;
    }
    setKnowledge((k) => ({ ...k, [selected]: draft }));
    setEdited((s) => new Set(s).add(selected));
    setVerify(null); // an edit makes the last check stale
    setDraft(null);
    setDraftError(null);
    toast.success(`Saved ${selected}. Verify the quotes again.`);
  }

  /** Pass the (edited) knowledge to the Knowledge Synthesis page within this tab. */
  function sendToSynthesis() {
    if (!putKnowledgeHandoff(knowledge)) {
      toast.error(
        "The knowledge is too large to pass within the tab. Download the .zip and upload it on the Knowledge Synthesis page.",
        { duration: 8000 },
      );
      return;
    }
    router.push("/knowledge-synthesis");
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={LibraryBig}
        title="Knowledge Curator"
        description="Collect the facts for a fixed set of topics from normalized sources. Every fact carries an exact quote, its file and its location. Edit the facts and check the quotes again."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Knowledge Curator"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from a ready-made set of sources
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

        <div className="grid items-stretch gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0">
                <div className="min-w-[12rem] flex-1">
                  <CardTitle>1. The sources</CardTitle>
                  <CardDescription>
                    Send them from the{" "}
                    <Link href="/source-normalizer" className="underline">
                      Source Normalizer
                    </Link>
                    , or upload the .zip it downloads.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={clearAll}
                  disabled={busy || (!normalized && !started)}
                >
                  Clear
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                {loadingExample && (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading the sources…
                  </p>
                )}
                {normalized && (
                  <>
                    <p className="text-muted-foreground text-xs">
                      From {origin || "an upload"}: {files.length} source
                      {files.length === 1 ? "" : "s"}
                    </p>
                    <ul className="space-y-1.5">
                      {files.map((f) => (
                        <li
                          key={f.id}
                          className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                        >
                          <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                          <span className="flex-1 truncate">{f.file}</span>
                          <span className="text-muted-foreground shrink-0 text-xs">
                            {f.source_type} ·{" "}
                            {(
                              normalized[`normalized/${f.id}.md`]?.length ?? 0
                            ).toLocaleString()}{" "}
                            chars
                          </span>
                          {f.source_class && (
                            <Badge variant="outline" className="text-[10px]">
                              {f.source_class}
                            </Badge>
                          )}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <label
                  className={cn(
                    "text-muted-foreground hover:border-primary/50 flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-4 text-sm transition-colors",
                    busy && "pointer-events-none opacity-50",
                  )}
                >
                  <Upload className="h-4 w-4" />
                  {normalized
                    ? "Replace with a .zip"
                    : "Upload the .zip from the Source Normalizer"}
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

            <Card className="flex flex-1 flex-col">
              <CardHeader>
                <CardTitle>3. Instructions</CardTitle>
                <CardDescription>
                  Which sources to trust more, scope and style, and the language
                  of the summaries. When sources disagree, this decides whether
                  a conflict is resolved.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1">
                <Textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  disabled={busy}
                  placeholder="e.g. Site notes are primary sources. Customer documents are secondary. Write the summaries in English."
                  className="h-full min-h-[110px] text-sm"
                />
              </CardContent>
            </Card>
          </div>

          <div className="flex flex-col gap-6">
            <Card className="flex-1">
              <CardHeader>
                <CardTitle>2. Topics</CardTitle>
                <CardDescription>
                  The topics to collect facts for. Under Advanced, list the
                  items a topic must cover; the ones no source covers are
                  reported as missing.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <SectionEditor
                  sections={sections}
                  onChange={setSections}
                  disabled={busy}
                  withRequiredItems
                  hideDependsOn
                  noun="Topic"
                />
                {problem && started && (
                  <p className="text-destructive mt-2 text-xs">{problem}</p>
                )}
                {!started && (
                  <p className="mt-2 text-xs font-medium text-amber-700">
                    No topic defined yet. Add a title and what to look for, or
                    load an example.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="options" className="border-none">
                  <AccordionTrigger className="text-muted-foreground hover:text-foreground px-6 py-4 text-left text-sm font-medium hover:no-underline">
                    <div>
                      4. Options
                      <p className="text-muted-foreground mt-1 text-sm font-normal">
                        Model, reasoning effort and parallel topics
                      </p>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="space-y-3 px-6 pb-5">
                    <div className="space-y-1">
                      <Label htmlFor="kc-model" className="text-sm">
                        Model
                      </Label>
                      <Input
                        id="kc-model"
                        value={options.model ?? ""}
                        disabled={busy}
                        onChange={(e) =>
                          setOptions({ ...options, model: e.target.value })
                        }
                        placeholder="The server's model"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-sm">Reasoning effort</Label>
                      <Select
                        value={options.reasoning_effort ?? "default"}
                        disabled={busy}
                        onValueChange={(v) =>
                          setOptions({
                            ...options,
                            reasoning_effort:
                              v === "default" ? null : (v as Effort),
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="default">Model default</SelectItem>
                          {EFFORTS.map((e) => (
                            <SelectItem key={e} value={e}>
                              {e}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-muted-foreground text-xs">
                        Higher effort copies quotes more carefully, at more cost
                        and time.
                      </p>
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="kc-workers" className="text-sm">
                        Topics in parallel
                      </Label>
                      <Input
                        id="kc-workers"
                        type="number"
                        min={1}
                        max={8}
                        value={options.max_workers}
                        disabled={busy}
                        onChange={(e) =>
                          setOptions({
                            ...options,
                            max_workers: Math.min(
                              8,
                              Math.max(1, Number(e.target.value) || 1),
                            ),
                          })
                        }
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
              <CardContent className="flex gap-2 pt-0">
                <Button
                  size="lg"
                  className="flex-1"
                  onClick={curate}
                  disabled={busy || !normalized || problem !== null}
                >
                  {running ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  {running ? "Curating…" : "Curate"}
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
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="space-y-4" aria-live="polite">
          {progress.length > 0 && (
            <Card>
              <CardContent className="space-y-2 py-4">
                <p className="text-sm font-medium">
                  {running ? "Curating…" : "Done"}
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

          {dropped.length > 0 && (
            <Alert className="border-amber-500">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertDescription className="space-y-2 text-xs">
                <p className="font-medium">
                  {dropped.length} fact{dropped.length === 1 ? "" : "s"}{" "}
                  dropped: the quote is not in the source, even after asking
                  again. The rest of each topic was kept. A dropped fact can be
                  true with a wrongly copied quote, so review the list.
                </p>
                <ul className="w-full space-y-1.5">
                  {dropped.map((d, i) => (
                    <li key={i} className="rounded border px-2 py-1">
                      <p>
                        <span className="font-mono">{d.section_id}</span> ·{" "}
                        {d.topic} ·{" "}
                        <span className="text-muted-foreground">
                          {d.reason}
                        </span>
                      </p>
                      <p>{d.summary}</p>
                      <blockquote className="text-muted-foreground border-l-2 pl-2">
                        {d.quote}
                      </blockquote>
                      <p className="text-muted-foreground font-mono">
                        {d.file}
                      </p>
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {knowledgePaths.length > 0 ? (
            <Card>
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>Knowledge</CardTitle>
                  <div className="ml-auto flex flex-wrap items-center gap-1.5">
                    <Button size="sm" onClick={sendToSynthesis} disabled={busy}>
                      <NotebookPen className="mr-1 h-3.5 w-3.5" />
                      Send to Knowledge Synthesis
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={verifyQuotes}
                      disabled={busy || !normalized}
                    >
                      {verifying ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                      )}
                      Verify quotes
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!normalized}
                      onClick={() =>
                        download(
                          new Uint8Array(
                            zipWorkspace(normalized ?? {}, knowledge),
                          ),
                          "knowledge.zip",
                          "application/zip",
                        )
                      }
                    >
                      <FileArchive className="mr-1 h-3.5 w-3.5" />
                      Download all (.zip)
                    </Button>
                    <FeedbackButton demoType="knowledge-curator" />
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Badge variant="outline" className="font-normal">
                    {totals.topics} topics
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {totals.facts} facts
                  </Badge>
                  <Badge
                    variant="outline"
                    className={cn(
                      "font-normal",
                      totals.missing > 0 && "border-amber-500 text-amber-700",
                    )}
                  >
                    {totals.missing} missing
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {totals.conflicts} conflicts
                    {totals.unresolved > 0 &&
                      `, ${totals.unresolved} unresolved`}
                  </Badge>
                  {dropped.length > 0 && (
                    <Badge
                      variant="outline"
                      className="border-amber-500 font-normal text-amber-700"
                    >
                      {dropped.length} dropped
                    </Badge>
                  )}
                  <Badge variant="outline" className="font-normal">
                    {usage && Object.keys(usage).length > 0
                      ? Object.entries(usage)
                          .map(([k, v]) => `${k} ${v.toLocaleString()}`)
                          .join(" · ")
                      : "no token counts reported"}
                  </Badge>
                </div>
                {verify && (
                  <Alert
                    variant={verify.failures.length ? "destructive" : "default"}
                  >
                    {verify.failures.length ? (
                      <AlertTriangle className="h-4 w-4" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    )}
                    <AlertDescription className="text-xs">
                      {verify.failures.length === 0
                        ? `All ${verify.units} quotes are in their sources.`
                        : `${verify.failures.length} of ${verify.units} quotes are not in their sources. Correct or delete these facts, then verify again.`}
                    </AlertDescription>
                  </Alert>
                )}
              </CardHeader>
              <CardContent className="space-y-5">
                <FactsExplorer
                  sections={readable}
                  sources={files}
                  normalized={normalized ?? {}}
                  failures={verify?.failures ?? []}
                />

                <div className="space-y-2 border-t pt-4">
                  <p className="text-sm font-semibold">Topic files</p>
                  <p className="text-muted-foreground text-xs">
                    One JSON file per topic. Edit a file to correct, remove or
                    add facts, then verify the quotes again.
                  </p>
                  <ul className="space-y-1">
                    {knowledgePaths.map((path) => {
                      const read = readKnowledge(knowledge[path]);
                      const bad = failuresOf(path).length;
                      return (
                        <li
                          key={path}
                          className={cn(
                            "hover:bg-muted flex items-center gap-1.5 rounded px-1.5 py-1 text-xs",
                            path === selected && "bg-muted",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setSelected(path);
                              setDraft(null);
                              setDraftError(null);
                            }}
                            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                          >
                            <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                            <span className="truncate font-mono">{path}</span>
                            <span className="text-muted-foreground shrink-0">
                              {read.ok
                                ? `${read.value.units.length} facts · ${read.value.missing.length} missing · ${read.value.conflicts.length} conflicts`
                                : "invalid JSON"}
                            </span>
                          </button>
                          {bad > 0 && (
                            <Badge
                              variant="destructive"
                              className="text-[10px]"
                            >
                              {bad} not verified
                            </Badge>
                          )}
                          {edited.has(path) && (
                            <Badge
                              variant="outline"
                              className="border-amber-500 text-[10px] text-amber-600"
                            >
                              edited
                            </Badge>
                          )}
                          <button
                            type="button"
                            title="Download"
                            aria-label={`Download ${path}`}
                            onClick={() =>
                              download(
                                knowledge[path],
                                path.split("/").pop()!,
                                "application/json",
                              )
                            }
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>

                  {selected && selectedText !== undefined && (
                    <div className="rounded-md border">
                      <div className="flex items-center gap-2 border-b px-3 py-2">
                        <span className="flex-1 truncate font-mono text-xs">
                          {selected}
                        </span>
                        {draft === null && (
                          <Button
                            size="xs"
                            variant="outline"
                            disabled={busy}
                            onClick={() => {
                              setDraft(selectedText);
                              setDraftError(null);
                            }}
                          >
                            <Pencil />
                            Edit JSON
                          </Button>
                        )}
                      </div>
                      {draft !== null ? (
                        <div className="space-y-2 p-3">
                          <Textarea
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            className="min-h-[320px] font-mono text-xs"
                          />
                          {draftError && (
                            <p className="text-destructive text-xs">
                              {draftError}
                            </p>
                          )}
                          <div className="flex gap-2">
                            <Button size="sm" onClick={saveDraft}>
                              Save
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setDraft(null);
                                setDraftError(null);
                              }}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <pre className="max-h-64 overflow-auto p-3 font-mono text-xs">
                          {selectedText}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ) : (
            !running &&
            progress.length === 0 && (
              <EmptyStateCard
                icon={Wand2}
                title="No knowledge yet"
                description="Load an example or add normalized sources, then click Curate. The facts appear here, where you can filter them and see each quote in its source."
                feedbackSlot={<FeedbackButton demoType="knowledge-curator" />}
              />
            )
          )}
        </div>
      </div>
    </PageTransition>
  );
}
