"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
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
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import {
  AUDIO_COMPRESS_COMMAND,
  isMediaFile,
  REPORT_UPLOAD_MAX_BYTES,
  REPORT_UPLOAD_MAX_MB,
  totalFileBytes,
} from "@/lib/report-writer/upload-limit";
import { downloadBlob as download } from "@/lib/download";
import { processSSEStream } from "@/lib/sse";
import { putHandoff } from "@/lib/source-normalizer/handoff";
import {
  ACCEPT,
  buildManifest,
  DEFAULT_OPTIONS,
  FILE_KINDS,
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
  Download,
  FileArchive,
  FileStack,
  FileText,
  LibraryBig,
  Loader2,
  Pencil,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const API = "/api/source-normalizer";
// The example reuses the Report Writer v2 house condition assessment inputs. It picks
// one file of each kind: a recording, a PDF, a spreadsheet and an image.
const EXAMPLE_API = "/api/report-writer-v2/examples/house_condition_assessment";
const EXAMPLE_FILES = [
  "rec1_exterior_attic.mp3",
  "renovation_report_1998.pdf",
  "maintenance_log.xlsx",
  "floor_plan.png",
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

export default function SourceNormalizerPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const [loadingExample, setLoadingExample] = useState(false);

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<Record<string, number> | null>(null);
  const [edited, setEdited] = useState<Set<string>>(new Set());

  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const entries: NormalizedEntry[] = (() => {
    try {
      return readManifest(artifacts);
    } catch {
      return [];
    }
  })();
  const hasResult = MANIFEST_PATH in artifacts;

  const uploadBytes = totalFileBytes(rows.map((r) => r.file));
  const uploadTooLarge = uploadBytes > REPORT_UPLOAD_MAX_BYTES;
  const mediaFiles = rows.filter((r) => isMediaFile(r.name));
  const busy = running || loadingExample;

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
  }

  function resetResult() {
    setArtifacts({});
    setUsage(null);
    setEdited(new Set());
    setSelected(null);
    setDraft(null);
    setProgress([]);
    setError(null);
  }

  function clearAll() {
    if (hasResult && !window.confirm("Clearing removes the current result. Continue?"))
      return;
    setRows([]);
    setOptions(DEFAULT_OPTIONS);
    resetResult();
  }

  async function loadExample() {
    if (hasResult && !window.confirm("Loading the example replaces the current result. Continue?"))
      return;
    setLoadingExample(true);
    try {
      const specRes = await fetch(`${EXAMPLE_API}/spec`);
      if (!specRes.ok) throw new Error(`GET spec failed (${specRes.status})`);
      const spec = (await specRes.json()) as {
        sources: Record<SourceClass, string[]>;
      };
      const loaded: Row[] = [];
      for (const sourceClass of ["primary", "secondary"] as const) {
        for (const name of spec.sources[sourceClass]) {
          if (!EXAMPLE_FILES.includes(name)) continue;
          const res = await fetch(`${EXAMPLE_API}/files/${encodeURIComponent(name)}`);
          if (!res.ok) throw new Error(`GET ${name} failed (${res.status})`);
          loaded.push({ name, sourceClass, file: new File([await res.blob()], name) });
        }
      }
      if (loaded.length !== EXAMPLE_FILES.length)
        throw new Error("The example is missing files.");
      setRows(loaded);
      resetResult();
      toast.success("Example loaded. Click Normalize.");
    } catch (e) {
      toast.error(`Loading the example failed: ${message(e)}`);
    } finally {
      setLoadingExample(false);
    }
  }

  async function normalize() {
    if (busy || rows.length === 0) return;
    if (uploadTooLarge) {
      toast.error(`Uploads exceed the ${REPORT_UPLOAD_MAX_MB} MB limit. See the note under Files.`);
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
          else errors.push(`Unexpected "${event.type}" event from the backend.`);
        },
      });
      const result = results.at(-1);
      if (result) {
        if (!result.usage || typeof result.usage !== "object")
          throw new Error("The result has no usage.");
        const next = parseArtifacts(result.artifacts);
        setArtifacts(next);
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

  const mdPaths = Object.keys(artifacts).filter((p) => p.endsWith(".md")).sort();
  const text = selected ? artifacts[selected] : undefined;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FileStack}
        title="Source Normalizer"
        description="Transform data (PDFs, Word files, spreadsheets, text, recordings and images) in a uniform Markdown format."
        className="mb-6"
      >
        <p className="mt-1 text-xs text-muted-foreground">
          Note: The result lives in this browser tab. Reloading or closing the
          tab loses it, so download the .zip first.
        </p>
      </DemoPageHeader>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── LEFT COLUMN ── */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-3">
              <div>
                <CardTitle className="text-base">Files</CardTitle>
                <CardDescription>
                  Up to {MAX_FILES} files, {REPORT_UPLOAD_MAX_MB} MB together. File
                  names must be unique.
                </CardDescription>
              </div>
              <div className="flex max-w-full flex-wrap gap-1">
                <Button size="sm" variant="outline" onClick={loadExample} disabled={busy}>
                  {loadingExample && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                  Load example
                </Button>
                <Button size="sm" variant="ghost" onClick={clearAll} disabled={busy}>
                  Clear
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {rows.length > 0 && (
                <ul className="space-y-1">
                  {rows.map((row, i) => (
                    <li
                      key={row.name}
                      className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="flex-1 truncate">{row.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatFileSize(row.file.size)}
                      </span>
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
                                      r.sourceClass === "primary" ? "secondary" : "primary",
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
                        disabled={busy}
                        onClick={() => setRows(rows.filter((_, j) => j !== i))}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <label
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-muted-foreground/50",
                  busy && "pointer-events-none opacity-50",
                )}
              >
                <Upload className="h-4 w-4" />
                Add files
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

              <div className="space-y-1 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">Accepted file types</p>
                <ul className="space-y-0.5">
                  {FILE_KINDS.map((k) => (
                    <li key={k.kind}>
                      <span className="font-medium">{k.kind}</span>{" "}
                      <span className="font-mono">{k.extensions.join(" ")}</span>
                      <span> ({k.note})</span>
                    </li>
                  ))}
                </ul>
                <p>{UNSUPPORTED_HINT}</p>
              </div>

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
                        <pre className="whitespace-pre-wrap break-all rounded bg-muted px-2 py-1.5 text-xs text-foreground">
                          {AUDIO_COMPRESS_COMMAND}
                        </pre>
                      </>
                    ) : (
                      <p>Remove some files or split large documents, then try again.</p>
                    )}
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="options" className="border-none">
                <AccordionTrigger className="px-6 py-4 text-left text-sm font-medium text-muted-foreground hover:text-foreground hover:no-underline">
                  <div>
                    Options
                    <p className="mt-1 text-sm font-normal text-muted-foreground">
                      Only recordings and images call a model
                    </p>
                  </div>
                </AccordionTrigger>
                <AccordionContent className="space-y-3 px-6 pb-5">
                  <div className="space-y-1">
                    <Label htmlFor="sn-language" className="text-sm">
                      Recording language
                    </Label>
                    <Input
                      id="sn-language"
                      value={options.language}
                      disabled={busy}
                      onChange={(e) => setOptions({ ...options, language: e.target.value })}
                      placeholder="auto, en, fi, ..."
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="sn-transcription" className="text-sm">
                      Transcription model
                    </Label>
                    <Input
                      id="sn-transcription"
                      value={options.transcription_model ?? ""}
                      disabled={busy}
                      onChange={(e) =>
                        setOptions({ ...options, transcription_model: e.target.value })
                      }
                      placeholder="Server default, e.g. gpt-4o-transcribe"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="sn-vision" className="text-sm">
                      Image model
                    </Label>
                    <Input
                      id="sn-vision"
                      value={options.vision_model ?? ""}
                      disabled={busy}
                      onChange={(e) => setOptions({ ...options, vision_model: e.target.value })}
                      placeholder="Server default"
                    />
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </Card>

          <div className="flex gap-2">
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
              Normalize
            </Button>
            {running && (
              <Button variant="outline" size="lg" onClick={() => abortRef.current?.abort()}>
                <X className="mr-2 h-4 w-4" />
                Cancel
              </Button>
            )}
          </div>
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="space-y-4">
          <HowItWorksCard description="Why sources are normalized, and what happens next">
            <p>
              <strong>Purpose.</strong> Sources come in many formats: a PDF, a
              spreadsheet, a recording and a photo cannot be read, searched or
              checked in the same way. Normalizing turns each of them into plain
              Markdown text, so every source can be read by a person or a model
              in one uniform format. Each text keeps its original file name and
              its primary or secondary label, so later steps can say where a
              fact came from.
            </p>
            <p>
              <strong>How each file is converted.</strong> PDFs and Word files
              are parsed locally, spreadsheets become tables, recordings are
              transcribed and images are described by a vision model.
            </p>
            <p>
              <strong>Primary and secondary sources.</strong> Mark each file as
              primary or secondary by clicking its label in the file list; new
              files start as primary. Primary sources are your own first-hand
              evidence, such as site notes or recordings. Secondary sources are
              background, such as older reports or customer documents. The label
              does not change how a file is converted. It is saved with the text
              so that later steps know how far to trust each source: when
              sources disagree, the Knowledge Curator can prefer primary over
              secondary if its instructions say so.
            </p>
            <p>
              A file that cannot be converted fully, such as a scanned PDF with
              no text layer or an unsupported type, stops the run and is named
              in the error. Recordings carry no per-utterance timestamps.
            </p>
            <p>
              <strong>What you can do with the result.</strong> Read and edit
              the texts to fix a transcription error, then download them, one
              Markdown file each or everything as a .zip, or click{" "}
              <strong>Send to Knowledge Curator</strong> to carry them to the
              next step in this tab.
            </p>
            <p>
              <strong>What the Knowledge Curator does.</strong> It reads the
              normalized texts and, for the topics you define, collects the
              facts that matter. Each fact is a short summary with the exact
              quote it came from, its source file and its location. It also
              lists what no source covers and where the sources disagree, so the
              facts can be checked and reused, for example as the basis of a
              report.
            </p>
          </HowItWorksCard>

          {progress.length > 0 && (
            <Card>
              <CardContent className="max-h-40 space-y-0.5 overflow-y-auto py-3 text-xs">
                {progress.map((m, i) => (
                  <p key={i} className="flex items-center gap-1.5">
                    {running && i === progress.length - 1 && (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    )}
                    {m}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="whitespace-pre-wrap text-xs">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {usage && (
            <p className="text-xs text-muted-foreground">
              <span className="font-medium">Usage:</span>{" "}
              {Object.entries(usage)
                .map(([k, v]) => `${k} ${v.toLocaleString()}`)
                .join(" · ") || "no model calls"}
            </p>
          )}

          {hasResult ? (
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 space-y-0 pb-3">
                <div className="min-w-[12rem] flex-1">
                  <CardTitle className="text-base">Normalized texts</CardTitle>
                  <CardDescription>
                    Select a text to read it. Edit it before you download.
                  </CardDescription>
                </div>
                <div className="flex max-w-full flex-wrap items-center justify-end gap-1">
                  <Button size="sm" onClick={sendToCurator}>
                    <LibraryBig className="mr-1 h-3.5 w-3.5" />
                    Send to Knowledge Curator
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      download(new Uint8Array(zipArtifacts(artifacts)), "normalized.zip", "application/zip")
                    }
                  >
                    <FileArchive className="mr-1 h-3.5 w-3.5" />
                    Download all (.zip)
                  </Button>
                  <FeedbackButton demoType="source-normalizer" />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="space-y-0.5">
                  {mdPaths.map((path) => {
                    const id = path.slice("normalized/".length, -".md".length);
                    const entry = entries.find((e) => e.id === id);
                    return (
                      <li
                        key={path}
                        className={cn(
                          "flex items-center gap-1.5 rounded px-1.5 py-1 text-xs hover:bg-muted",
                          path === selected && "bg-muted",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => selectPath(path)}
                          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                        >
                          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          <span className="truncate font-mono">{entry?.file ?? id}</span>
                          {entry && (
                            <span className="shrink-0 text-muted-foreground">
                              {entry.source_type} · {entry.tool} ·{" "}
                              {artifacts[path].length.toLocaleString()} chars
                            </span>
                          )}
                        </button>
                        {entry?.source_class && (
                          <Badge variant="outline" className="text-[10px]">
                            {entry.source_class}
                          </Badge>
                        )}
                        {edited.has(path) && (
                          <Badge variant="outline" className="border-amber-500 text-[10px] text-amber-600">
                            edited
                          </Badge>
                        )}
                        <button
                          type="button"
                          title="Download"
                          onClick={() => download(artifacts[path], `${id}.md`, "text/markdown")}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <Download className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    );
                  })}
                </ul>

                {selected && text !== undefined && (
                  <div className="rounded-md border">
                    <div className="flex items-center gap-2 border-b px-3 py-2">
                      <span className="flex-1 truncate font-mono text-xs">{selected}</span>
                      {draft === null && (
                        <Button size="xs" variant="outline" onClick={() => setDraft(text)}>
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
                          <Button size="sm" variant="outline" onClick={() => setDraft(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="max-h-[480px] overflow-y-auto p-3">
                        <MessageResponse className="text-sm">{text}</MessageResponse>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <EmptyStateCard
              icon={FileStack}
              title="No result yet"
              description="Load the example or add files, then click Normalize."
              feedbackSlot={<FeedbackButton demoType="source-normalizer" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
