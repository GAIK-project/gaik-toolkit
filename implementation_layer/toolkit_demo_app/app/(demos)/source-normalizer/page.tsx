"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { downloadBlob as download } from "@/lib/download";
import {
  AUDIO_COMPRESS_COMMAND,
  isMediaFile,
  REPORT_UPLOAD_MAX_BYTES,
  REPORT_UPLOAD_MAX_MB,
  totalFileBytes,
} from "@/lib/report-writer/upload-limit";
import { processSSEStream } from "@/lib/sse";
import { putHandoff } from "@/lib/source-normalizer/handoff";
import {
  ACCEPT,
  buildManifest,
  DEFAULT_OPTIONS,
  isSupportedFile,
  MANIFEST_PATH,
  MAX_FILES,
  parseArtifacts,
  readManifest,
  UNSUPPORTED_HINT,
  zipArtifacts,
  type NormalizedEntry,
  type SourceClass,
} from "@/lib/source-normalizer/workspace";
import { cn, formatFileSize } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  FileArchive,
  FileStack,
  FileText,
  Layers,
  LibraryBig,
  Loader2,
  Pencil,
  RotateCcw,
  Search,
  Sparkles,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { countMatches, splitByQuery } from "../parser/parser-data";
import {
  countByClass,
  describeText,
  EXAMPLES,
  hasImages,
  hasRecordings,
  kindOf,
  progressShare,
  type SourceExample,
} from "./normalizer-data";

const API = "/api/source-normalizer";
// The house example reuses the Report Writer v2 house condition assessment inputs. It
// picks one file of each kind: a recording, a PDF, a spreadsheet and an image.
const HOUSE_API = "/api/report-writer-v2/examples/house_condition_assessment";
const HOUSE_FILES = [
  "rec1_exterior_attic.mp3",
  "renovation_report_1998.pdf",
  "maintenance_log.xlsx",
  "floor_plan.png",
];

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add the sources",
    text: "PDFs, Word files, spreadsheets, text, recordings and images, or start from a ready-made set.",
  },
  {
    icon: Layers,
    title: "Label them",
    text: "Mark each file primary (first-hand evidence) or secondary (background).",
  },
  {
    icon: Sparkles,
    title: "Normalize",
    text: "Each file becomes Markdown that keeps its file name and label. Progress shows file by file.",
  },
  {
    icon: Search,
    title: "Explore and use the texts",
    text: "Search across all texts, read them, fix errors, then download them or send them to the Knowledge Curator.",
  },
];
const GUIDE_NOTES = [
  "Documents are converted locally. Only recordings and images call a model. A scanned PDF with no text layer stops the run, and recordings carry no timestamps for each utterance.",
  "The result lives in this browser tab. Reloading or closing the tab loses it, so download the .zip first.",
];

interface Row {
  name: string;
  sourceClass: SourceClass;
  file: File;
}

interface RunResult {
  artifacts: unknown;
  usage: Record<string, number>;
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
    `Run failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
  );
}

/** The Markdown as it is written, with line numbers and the search marked. */
function Source({ text, query }: { text: string; query: string }) {
  return (
    <pre className="font-mono text-xs leading-5">
      {text.split("\n").map((line, index) => (
        <div key={index} className="flex gap-3">
          <span className="text-muted-foreground w-8 shrink-0 text-right select-none">
            {index + 1}
          </span>
          <span className="min-w-0 break-words whitespace-pre-wrap">
            {splitByQuery(line, query).map((part, partIndex) =>
              part.hit ? (
                <mark
                  key={partIndex}
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

export default function SourceNormalizerPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [loadingExample, setLoadingExample] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [original, setOriginal] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<Record<string, number> | null>(null);
  const [edited, setEdited] = useState<Set<string>>(new Set());

  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [tab, setTab] = useState("rendered");
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const entries: NormalizedEntry[] = useMemo(() => {
    try {
      return readManifest(artifacts);
    } catch {
      return [];
    }
  }, [artifacts]);
  const hasResult = MANIFEST_PATH in artifacts;

  const names = rows.map((r) => r.name);
  const uploadBytes = totalFileBytes(rows.map((r) => r.file));
  const uploadTooLarge = uploadBytes > REPORT_UPLOAD_MAX_BYTES;
  const mediaFiles = rows.filter((r) => isMediaFile(r.name));
  const busy = running || loadingExample;
  const recordings = hasRecordings(names);
  const images = hasImages(names);

  const mdPaths = Object.keys(artifacts)
    .filter((p) => p.endsWith(".md"))
    .sort();
  const text = selected ? artifacts[selected] : undefined;
  const entryOf = (path: string) =>
    entries.find(
      (e) => e.id === path.slice("normalized/".length, -".md".length),
    );
  const matchCounts = Object.fromEntries(
    mdPaths.map((path) => [path, countMatches(artifacts[path], query)]),
  );
  const totalMatches = Object.values(matchCounts).reduce((a, b) => a + b, 0);
  const filesWithMatches = Object.values(matchCounts).filter(Boolean).length;
  const totals = describeText(mdPaths.map((p) => artifacts[p]).join("\n"));
  const classCounts = countByClass(entries);
  const selectedEntry = selected ? entryOf(selected) : undefined;
  const selectedKind = selectedEntry ? kindOf(selectedEntry.file) : null;
  const done = progressShare(progress.length, rows.length);

  function addFiles(files: File[], sourceClass: SourceClass = "primary") {
    const unsupported = files.filter((f) => !isSupportedFile(f.name));
    if (unsupported.length)
      toast.error(
        `Not added, unsupported type: ${unsupported.map((f) => f.name).join(", ")}. ${UNSUPPORTED_HINT}`,
        { duration: 8000 },
      );
    const next = [...rows];
    for (const file of files.filter((f) => isSupportedFile(f.name))) {
      const i = next.findIndex((r) => r.name === file.name);
      if (i >= 0) next[i] = { ...next[i], file };
      else next.push({ name: file.name, sourceClass, file });
    }
    if (next.length > MAX_FILES) {
      toast.error(`At most ${MAX_FILES} files per run.`);
      return;
    }
    setRows(next);
    setExampleId(null);
  }

  function resetResult() {
    setArtifacts({});
    setOriginal({});
    setUsage(null);
    setEdited(new Set());
    setSelected(null);
    setDraft(null);
    setProgress([]);
    setError(null);
    setQuery("");
    setTab("rendered");
  }

  function clearAll() {
    if (
      hasResult &&
      !window.confirm("Clearing removes the current result. Continue?")
    )
      return;
    setRows([]);
    setOptions(DEFAULT_OPTIONS);
    setExampleId(null);
    resetResult();
  }

  async function pickExample(example: SourceExample | "house") {
    if (busy) return;
    if (
      hasResult &&
      !window.confirm(
        "Loading an example replaces the current result. Continue?",
      )
    )
      return;
    setLoadingExample(true);
    try {
      const loaded: Row[] = [];
      if (example === "house") {
        const specRes = await fetch(`${HOUSE_API}/spec`);
        if (!specRes.ok) throw new Error(`GET spec failed (${specRes.status})`);
        const spec = (await specRes.json()) as {
          sources: Record<SourceClass, string[]>;
        };
        for (const sourceClass of ["primary", "secondary"] as const) {
          for (const name of spec.sources[sourceClass]) {
            if (!HOUSE_FILES.includes(name)) continue;
            const res = await fetch(
              `${HOUSE_API}/files/${encodeURIComponent(name)}`,
            );
            if (!res.ok) throw new Error(`GET ${name} failed (${res.status})`);
            loaded.push({
              name,
              sourceClass,
              file: new File([await res.blob()], name),
            });
          }
        }
        if (loaded.length !== HOUSE_FILES.length)
          throw new Error("The example is missing files.");
      } else {
        for (const entry of example.files) {
          const res = await fetch(entry.url);
          if (!res.ok) throw new Error(`Failed to load ${entry.name}`);
          loaded.push({
            name: entry.name,
            sourceClass: entry.sourceClass,
            file: new File([await res.blob()], entry.name),
          });
        }
      }
      setRows(loaded);
      setExampleId(example === "house" ? "house" : example.id);
      resetResult();
    } catch (e) {
      toast.error(`Loading the example failed: ${message(e)}`);
    } finally {
      setLoadingExample(false);
    }
  }

  async function normalize() {
    if (busy || rows.length === 0) return;
    if (uploadTooLarge) {
      toast.error(
        `Uploads exceed the ${REPORT_UPLOAD_MAX_MB} MB limit. See the note under Files.`,
      );
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    resetResult();
    setRunning(true);
    try {
      const form = new FormData();
      form.append("manifest", JSON.stringify(buildManifest(rows, options)));
      for (const r of rows) form.append("files", r.file, r.name);
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
        const next = parseArtifacts(result.artifacts);
        setArtifacts(next);
        setOriginal(next);
        setUsage(result.usage);
        setSelected(Object.keys(next).find((p) => p.endsWith(".md")) ?? null);
      }
      if (errors.length) throw new Error(errors.join("\n"));
      if (!result) throw new Error("Normalize ended without a result.");
      toast.success("Sources normalized");
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return; // apiFetch already showed a toast
      setError(message(e));
    } finally {
      setRunning(false);
    }
  }

  /** Pass the (edited) texts to the Knowledge Curator page within this tab. */
  function sendToCurator() {
    if (!putHandoff(artifacts)) {
      toast.error(
        "The result is too large to pass within the tab. Download the .zip and upload it on the Knowledge Curator page.",
        { duration: 8000 },
      );
      return;
    }
    router.push("/knowledge-curator");
  }

  function selectPath(path: string) {
    setSelected(path);
    setDraft(null);
  }

  function saveDraft() {
    if (selected === null || draft === null) return;
    setArtifacts((a) => ({ ...a, [selected]: draft }));
    setEdited((s) => new Set(s).add(selected));
    setDraft(null);
    toast.success(`Saved ${selected}`);
  }

  function resetText() {
    if (selected === null) return;
    setArtifacts((a) => ({ ...a, [selected]: original[selected] }));
    setEdited((s) => {
      const next = new Set(s);
      next.delete(selected);
      return next;
    });
    setDraft(null);
  }

  async function copyText() {
    if (text === undefined) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Could not copy");
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FileStack}
        title="Source Normalizer"
        description="Transform data (PDFs, Word files, spreadsheets, text, recordings and images) in a uniform Markdown format."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Source Normalizer"
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
            <button
              type="button"
              role="radio"
              aria-checked={exampleId === "house"}
              disabled={busy}
              onClick={() => void pickExample("house")}
              className={cn(
                "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                exampleId === "house"
                  ? "border-primary bg-primary/5"
                  : "bg-card hover:border-primary/40",
              )}
            >
              <span className="font-semibold">
                A house condition assessment
              </span>
              <span className="text-muted-foreground text-sm">
                A recording, an old report, a maintenance log and a floor plan:
                one source of every kind. The recording and the image call a
                model, so this takes longer.
              </span>
              <span className="flex flex-wrap gap-1">
                {["recording", "PDF", "spreadsheet", "image"].map((tag) => (
                  <Badge key={tag} variant="outline" className="font-normal">
                    {tag}
                  </Badge>
                ))}
              </span>
            </button>
          </div>
        </section>

        <div className="grid items-stretch gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
              <div>
                <CardTitle>1. The sources</CardTitle>
                <CardDescription>
                  Up to {MAX_FILES} files, {REPORT_UPLOAD_MAX_MB} MB together.
                  File names must be unique.
                </CardDescription>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={clearAll}
                disabled={busy || rows.length === 0}
              >
                Clear
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <label
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!busy) addFiles(Array.from(e.dataTransfer.files));
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (!busy) setIsDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                }}
                className={cn(
                  "flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-5 text-sm transition-all",
                  isDragging
                    ? "border-primary bg-primary/5 text-primary"
                    : "text-muted-foreground hover:border-primary/50 hover:bg-muted/50",
                  busy && "pointer-events-none opacity-50",
                )}
              >
                <Upload className="h-4 w-4" />
                {isDragging
                  ? "Drop the files here"
                  : "Drag & drop or click to add files"}
                <input
                  type="file"
                  multiple
                  className="sr-only"
                  accept={ACCEPT}
                  disabled={busy}
                  onChange={(e) => {
                    addFiles(Array.from(e.target.files || []));
                    e.target.value = "";
                  }}
                />
              </label>

              {loadingExample && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading the sources…
                </p>
              )}

              {rows.length > 0 && (
                <ul className="max-h-80 space-y-1.5 overflow-auto">
                  {rows.map((row, i) => {
                    const kind = kindOf(row.name);
                    return (
                      <li
                        key={row.name}
                        className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
                      >
                        <FileText className="text-muted-foreground h-4 w-4 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate">{row.name}</p>
                          <p className="text-muted-foreground text-xs">
                            {kind.label} · {kind.tool} ·{" "}
                            {formatFileSize(row.file.size)}
                            {kind.usesModel && (
                              <span className="ml-1 text-amber-700">
                                · calls a model
                              </span>
                            )}
                          </p>
                        </div>
                        <button
                          type="button"
                          disabled={busy}
                          title="Primary sources are the evidence; secondary sources give background"
                          onClick={() =>
                            setRows(
                              rows.map((r, j) =>
                                j === i
                                  ? {
                                      ...r,
                                      sourceClass:
                                        r.sourceClass === "primary"
                                          ? "secondary"
                                          : "primary",
                                    }
                                  : r,
                              ),
                            )
                          }
                          className={cn(
                            "shrink-0 rounded-full border px-2 py-0.5 font-mono text-xs transition-colors",
                            row.sourceClass === "primary"
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-border bg-muted text-muted-foreground",
                            busy && "pointer-events-none opacity-50",
                          )}
                        >
                          {row.sourceClass}
                        </button>
                        <button
                          type="button"
                          title="Remove"
                          aria-label={`Remove ${row.name}`}
                          disabled={busy}
                          onClick={() => {
                            setRows(rows.filter((_, j) => j !== i));
                            setExampleId(null);
                          }}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="text-muted-foreground text-xs">
                Click primary or secondary to switch a label. Primary sources
                are your own first-hand evidence, such as site notes or
                recordings. Secondary sources are background, such as older
                reports. {UNSUPPORTED_HINT}
              </p>

              {uploadTooLarge && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription className="space-y-2">
                    <p>
                      The files total {formatFileSize(uploadBytes)}, over the{" "}
                      {REPORT_UPLOAD_MAX_MB} MB limit.
                    </p>
                    {mediaFiles.length > 0 ? (
                      <>
                        <p>
                          Compress {mediaFiles.map((f) => f.name).join(", ")} to
                          speech-quality MP3 (about 14 MB per hour) with ffmpeg,
                          replacing <code>input.mp4</code> with your file:
                        </p>
                        <pre className="bg-muted text-foreground rounded px-2 py-1.5 text-xs break-all whitespace-pre-wrap">
                          {AUDIO_COMPRESS_COMMAND}
                        </pre>
                      </>
                    ) : (
                      <p>
                        Remove some files or split large documents, then try
                        again.
                      </p>
                    )}
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card className="flex flex-col">
            <CardHeader>
              <CardTitle>2. Options</CardTitle>
              <CardDescription>
                Only recordings and images call a model. The other files are
                converted locally, whatever you choose here.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-4">
              <div className="space-y-2">
                <Label htmlFor="sn-language">Recording language</Label>
                <div className="flex flex-wrap items-center gap-2">
                  {["auto", "fi", "en"].map((code) => (
                    <button
                      key={code}
                      type="button"
                      disabled={busy || (rows.length > 0 && !recordings)}
                      aria-pressed={options.language === code}
                      onClick={() => setOptions({ ...options, language: code })}
                      className={cn(
                        "rounded-full border px-3 py-1 text-sm transition-colors disabled:opacity-50",
                        options.language === code
                          ? "border-primary bg-primary/10 text-primary"
                          : "hover:border-primary/40",
                      )}
                    >
                      {code === "auto"
                        ? "Auto-detect"
                        : code === "fi"
                          ? "Finnish"
                          : "English"}
                    </button>
                  ))}
                  <Input
                    id="sn-language"
                    value={options.language}
                    disabled={busy || (rows.length > 0 && !recordings)}
                    onChange={(e) =>
                      setOptions({ ...options, language: e.target.value })
                    }
                    placeholder="auto, en, fi, …"
                    className="w-32"
                  />
                </div>
                <p className="text-muted-foreground text-xs">
                  {rows.length > 0 && !recordings
                    ? "There are no recordings in the sources, so the language is not used."
                    : "The language of the speech in the recordings, or a language code of your own."}
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="sn-transcription">Transcription model</Label>
                <Input
                  id="sn-transcription"
                  value={options.transcription_model ?? ""}
                  disabled={busy || (rows.length > 0 && !recordings)}
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      transcription_model: e.target.value,
                    })
                  }
                  placeholder="The server's model"
                />
                <p className="text-muted-foreground text-xs">
                  {rows.length > 0 && !recordings
                    ? "There are no recordings in the sources."
                    : "Leave it empty to use the server's transcription model."}
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="sn-vision">Image model</Label>
                <Input
                  id="sn-vision"
                  value={options.vision_model ?? ""}
                  disabled={busy || (rows.length > 0 && !images)}
                  onChange={(e) =>
                    setOptions({ ...options, vision_model: e.target.value })
                  }
                  placeholder="The server's model"
                />
                <p className="text-muted-foreground text-xs">
                  {rows.length > 0 && !images
                    ? "There are no images in the sources."
                    : "Leave it empty to use the server's model for describing images."}
                </p>
              </div>

              <div className="mt-auto flex gap-2 pt-2">
                <Button
                  size="lg"
                  className="flex-1"
                  onClick={normalize}
                  disabled={busy || rows.length === 0 || uploadTooLarge}
                >
                  {running ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  {running ? "Normalizing…" : "Normalize"}
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
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {progress.length > 0 && (
            <Card>
              <CardContent className="space-y-2 py-4">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">
                    {running ? "Converting…" : "Converted"}
                  </span>
                  <span className="text-muted-foreground">
                    {Math.min(progress.length, rows.length)} of {rows.length}{" "}
                    sources
                  </span>
                </div>
                <div className="bg-muted h-2 overflow-hidden rounded-full">
                  <div
                    className="bg-primary h-full rounded-full transition-all"
                    style={{ width: `${(running ? done : 1) * 100}%` }}
                  />
                </div>
                <div className="max-h-28 space-y-0.5 overflow-y-auto text-xs">
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

          {hasResult ? (
            <Card>
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>Normalized texts</CardTitle>
                  <div className="ml-auto flex flex-wrap items-center gap-1.5">
                    <Button size="sm" onClick={sendToCurator}>
                      <LibraryBig className="mr-1 h-3.5 w-3.5" />
                      Send to Knowledge Curator
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        download(
                          new Uint8Array(zipArtifacts(artifacts)),
                          "normalized.zip",
                          "application/zip",
                        )
                      }
                    >
                      <FileArchive className="mr-1 h-3.5 w-3.5" />
                      Download all (.zip)
                    </Button>
                    <FeedbackButton demoType="source-normalizer" />
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Badge variant="outline" className="font-normal">
                    {mdPaths.length} {mdPaths.length === 1 ? "text" : "texts"}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {totals.words.toLocaleString()} words
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {totals.chars.toLocaleString()} characters
                  </Badge>
                  {Object.entries(classCounts).map(([name, count]) => (
                    <Badge key={name} variant="outline" className="font-normal">
                      {count} {name}
                    </Badge>
                  ))}
                  <Badge variant="outline" className="font-normal">
                    {usage && Object.keys(usage).length > 0
                      ? Object.entries(usage)
                          .map(([k, v]) => `${k} ${v.toLocaleString()}`)
                          .join(" · ")
                      : "no model calls"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
                    <Input
                      value={query}
                      onChange={(e) => {
                        setQuery(e.target.value);
                        if (e.target.value.trim()) setTab("markdown");
                      }}
                      placeholder="Search in all texts"
                      aria-label="Search in all texts"
                      className="pr-8 pl-8"
                    />
                    {query && (
                      <button
                        type="button"
                        aria-label="Clear the search"
                        onClick={() => setQuery("")}
                        className="text-muted-foreground hover:text-foreground absolute top-2.5 right-2.5"
                      >
                        <X className="size-4" />
                      </button>
                    )}
                  </div>
                  {query.trim() && (
                    <p className="text-muted-foreground text-xs">
                      {totalMatches === 0
                        ? "No matches."
                        : `${totalMatches} ${totalMatches === 1 ? "match" : "matches"} in ${filesWithMatches} ${filesWithMatches === 1 ? "text" : "texts"}`}
                    </p>
                  )}
                  <ul className="space-y-1">
                    {mdPaths.map((path) => {
                      const entry = entryOf(path);
                      const matches = matchCounts[path];
                      return (
                        <li key={path}>
                          <button
                            type="button"
                            onClick={() => selectPath(path)}
                            aria-current={path === selected}
                            className={cn(
                              "hover:bg-muted flex w-full flex-col gap-1 rounded-md border px-2.5 py-2 text-left text-xs transition-colors",
                              path === selected &&
                                "border-primary bg-primary/5",
                              query.trim() && matches === 0 && "opacity-50",
                            )}
                          >
                            <span className="flex items-center gap-1.5">
                              <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                              <span className="truncate font-mono">
                                {entry?.file ?? path}
                              </span>
                              {query.trim() && matches > 0 && (
                                <Badge className="ml-auto px-1.5 text-[10px]">
                                  {matches}
                                </Badge>
                              )}
                            </span>
                            <span className="text-muted-foreground flex flex-wrap items-center gap-1">
                              {entry && (
                                <>
                                  <span>{entry.source_type}</span>·
                                  <span>{entry.tool}</span>·
                                </>
                              )}
                              <span>
                                {artifacts[path].length.toLocaleString()} chars
                              </span>
                              {entry?.source_class && (
                                <Badge
                                  variant="outline"
                                  className="text-[10px]"
                                >
                                  {entry.source_class}
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
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>

                {selected && text !== undefined && (
                  <div className="min-w-0 rounded-md border">
                    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
                      <span className="flex-1 truncate font-mono text-xs">
                        {selectedEntry?.file ?? selected}
                      </span>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => void copyText()}
                      >
                        {copied ? <Check /> : <Copy />}
                        Copy
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() =>
                          download(
                            text,
                            `${selected.slice("normalized/".length)}`,
                            "text/markdown",
                          )
                        }
                      >
                        <Download />
                        .md
                      </Button>
                      {edited.has(selected) && draft === null && (
                        <Button size="xs" variant="outline" onClick={resetText}>
                          <RotateCcw />
                          Reset
                        </Button>
                      )}
                      {draft === null && (
                        <Button
                          size="xs"
                          variant="outline"
                          onClick={() => setDraft(text)}
                        >
                          <Pencil />
                          Edit
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
                        <div className="flex gap-2">
                          <Button size="sm" onClick={saveDraft}>
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setDraft(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Tabs value={tab} onValueChange={setTab} className="p-3">
                        <TabsList>
                          <TabsTrigger value="rendered">Rendered</TabsTrigger>
                          <TabsTrigger value="markdown">Markdown</TabsTrigger>
                          <TabsTrigger value="about">
                            About this text
                          </TabsTrigger>
                        </TabsList>
                        <TabsContent value="rendered" className="mt-3">
                          <div className="max-h-[32rem] overflow-y-auto">
                            <MessageResponse className="text-sm">
                              {text}
                            </MessageResponse>
                          </div>
                        </TabsContent>
                        <TabsContent value="markdown" className="mt-3">
                          <div className="max-h-[32rem] overflow-auto">
                            <Source text={text} query={query} />
                          </div>
                        </TabsContent>
                        <TabsContent value="about" className="mt-3">
                          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[9rem_1fr]">
                            <dt className="text-muted-foreground">
                              Source file
                            </dt>
                            <dd className="font-mono">
                              {selectedEntry?.file ?? "–"}
                            </dd>
                            <dt className="text-muted-foreground">Label</dt>
                            <dd>{selectedEntry?.source_class ?? "none"}</dd>
                            <dt className="text-muted-foreground">Type</dt>
                            <dd>{selectedEntry?.source_type ?? "–"}</dd>
                            <dt className="text-muted-foreground">
                              Converted by
                            </dt>
                            <dd>
                              <span className="font-mono">
                                {selectedEntry?.tool ?? "–"}
                              </span>
                              {selectedKind?.usesModel && (
                                <span className="ml-2 text-amber-700">
                                  (calls a model)
                                </span>
                              )}
                            </dd>
                            <dt className="text-muted-foreground">The text</dt>
                            <dd>{selectedKind?.text}</dd>
                            <dt className="text-muted-foreground">Size</dt>
                            <dd>
                              {describeText(text).words.toLocaleString()} words
                              · {describeText(text).lines.toLocaleString()}{" "}
                              lines ·{" "}
                              {describeText(text).chars.toLocaleString()}{" "}
                              characters
                            </dd>
                            <dt className="text-muted-foreground">Saved as</dt>
                            <dd className="font-mono">{selected}</dd>
                          </dl>
                        </TabsContent>
                      </Tabs>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            !running &&
            progress.length === 0 && (
              <EmptyStateCard
                icon={Wand2}
                title="No result yet"
                description="Load a ready-made set or add files, then click Normalize. The texts appear here, where you can search all of them at once."
                feedbackSlot={<FeedbackButton demoType="source-normalizer" />}
              />
            )
          )}
        </div>
      </div>
    </PageTransition>
  );
}
