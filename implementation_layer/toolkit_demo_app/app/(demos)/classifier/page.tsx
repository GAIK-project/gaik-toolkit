"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn, formatFileSize } from "@/lib/utils";
import {
  Check,
  Download,
  Eye,
  ListChecks,
  Loader2,
  Sparkles,
  Tags,
  Upload,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  ACCEPTED_EXTENSIONS,
  agreement,
  CLASSIFIER_PARSERS,
  countByClass,
  EXAMPLES,
  fileNameOf,
  MAX_FILE_MB,
  MAX_FILES,
  parseClasses,
  toCsv,
  type Classified,
  type ClassifierExample,
  type ClassifierParser,
} from "./classifier-data";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add documents",
    text: "Upload one or several PDFs, Word files or images, or start from a ready-made set.",
  },
  {
    icon: ListChecks,
    title: "Define the classes",
    text: "Name the categories the documents can belong to. “unknown” is added for you.",
  },
  {
    icon: Sparkles,
    title: "Sort",
    text: "Each document gets one class, a confidence score and the reason for it.",
  },
  {
    icon: Tags,
    title: "Review the result",
    text: "See how many documents each class got, filter by class, and check the reasons.",
  },
];
const GUIDE_NOTES = [
  "For a PDF or a Word file the classifier reads the first 1,000 characters of the text. For an image it looks at the whole image.",
  "Every document is sorted on its own, and only into one class. Nothing is saved.",
];

const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
const WORKERS = 3;

interface Entry {
  /** What identifies the file in this session. */
  key: string;
  file: File;
  /** The class an example says it should get. */
  expected?: string;
  status: "waiting" | "running" | "done" | "failed";
  result?: Classified;
  error?: string;
}

const keyOf = (file: File): string => `${file.name}:${file.size}`;

function validate(file: File): string | null {
  const ext = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  if (!ACCEPTED_EXTENSIONS.includes(ext))
    return `Unsupported type: ${ext}. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`;
  if (file.size > MAX_FILE_MB * 1024 * 1024)
    return `File too large (max ${MAX_FILE_MB}MB)`;
  return null;
}

function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** A document in a dialog, for the files the person has added. */
function FileViewer({
  file,
  onClose,
}: {
  file: File | null;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    const next = URL.createObjectURL(file);
    // The object URL is made here, and revoked below, so it belongs in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);

  const isPdf = file ? /\.pdf$/i.test(file.name) : false;
  const isImage = file ? /\.(png|jpe?g)$/i.test(file.name) : false;

  return (
    <Dialog open={file !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[90vh] w-[90vw] max-w-4xl flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{file?.name}</DialogTitle>
          <DialogDescription>
            {file ? formatFileSize(file.size) : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="bg-muted/30 min-h-0 flex-1 overflow-auto rounded-md border">
          {url && isPdf && (
            <iframe
              src={url}
              title={file?.name}
              className="h-[70vh] min-h-96 w-full"
            />
          )}
          {url && isImage && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={file?.name} className="mx-auto max-w-full" />
          )}
          {!isPdf && !isImage && (
            <p className="text-muted-foreground p-6 text-center text-sm">
              A preview is not available for this file type.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  const percent = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="flex items-center gap-2">
      <div
        className="bg-muted h-2 w-20 overflow-hidden rounded-full"
        role="meter"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full",
            percent >= 85
              ? "bg-emerald-500"
              : percent >= 60
                ? "bg-amber-500"
                : "bg-red-500",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="font-mono text-xs">{percent}%</span>
    </div>
  );
}

export default function ClassifierPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [classes, setClasses] = useState<string[]>(EXAMPLES[0].classes);
  const [classInput, setClassInput] = useState("");
  const [parserType, setParserType] = useState<ClassifierParser>("auto");
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [viewing, setViewing] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isRunning || isLoadingExample;
  const parser =
    CLASSIFIER_PARSERS.find((option) => option.id === parserType) ??
    CLASSIFIER_PARSERS[0];
  const done = entries.filter(
    (entry): entry is Entry & { result: Classified } =>
      entry.status === "done" && entry.result !== undefined,
  );
  const failed = entries.filter((entry) => entry.status === "failed");
  const finished = done.length + failed.length;
  const started = entries.some((entry) => entry.status !== "waiting");
  const counts = countByClass(done.map((entry) => entry.result));
  const match = agreement(
    done.map((entry) => entry.result),
    Object.fromEntries(
      entries.flatMap((entry) =>
        entry.expected !== undefined ? [[entry.file.name, entry.expected]] : [],
      ),
    ),
  );
  const shown = done.filter(
    (entry) => filter === null || entry.result.classification === filter,
  );

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  // The first set is loaded and selected when the page opens.
  useEffect(() => {
    void pickExample(EXAMPLES[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clearResults(next: Entry[]): Entry[] {
    return next.map((entry) => ({
      ...entry,
      status: "waiting",
      result: undefined,
      error: undefined,
    }));
  }

  function addFiles(incoming: FileList | File[]): void {
    const accepted: Entry[] = [];
    const errors: string[] = [];
    for (const file of Array.from(incoming)) {
      const error = validate(file);
      if (error) {
        errors.push(`${file.name}: ${error}`);
        continue;
      }
      if (entries.some((entry) => entry.key === keyOf(file))) continue;
      accepted.push({ key: keyOf(file), file, status: "waiting" });
    }
    if (errors.length > 0) toast.error(errors.join("\n"));
    const room = MAX_FILES - entries.length;
    if (accepted.length > room) toast.error(`At most ${MAX_FILES} files`);
    if (accepted.length > 0) {
      setEntries(clearResults([...entries, ...accepted.slice(0, room)]));
      setExampleId(null);
      setFilter(null);
    }
  }

  function removeFile(key: string): void {
    setEntries(clearResults(entries.filter((entry) => entry.key !== key)));
    setExampleId(null);
    setFilter(null);
  }

  async function pickExample(example: ClassifierExample): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    try {
      const loaded = await Promise.all(
        example.documents.map(async ({ url, expected: answer }) => {
          const response = await fetch(url);
          if (!response.ok)
            throw new Error(`Failed to load ${fileNameOf(url)}`);
          const blob = await response.blob();
          const file = new File([blob], fileNameOf(url), {
            type: blob.type || "application/octet-stream",
          });
          return {
            key: keyOf(file),
            file,
            expected: answer,
            status: "waiting",
          } satisfies Entry;
        }),
      );
      setEntries(loaded);
      setClasses(example.classes);
      setExampleId(example.id);
      setFilter(null);
      setOpen(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to load the example",
      );
    } finally {
      setIsLoadingExample(false);
    }
  }

  function addClasses(): void {
    const added = parseClasses(classInput).filter(
      (name) => !classes.includes(name),
    );
    if (added.length === 0) {
      setClassInput("");
      return;
    }
    setClasses([...classes, ...added]);
    setClassInput("");
    setExampleId(null);
  }

  function removeClass(name: string): void {
    setClasses(classes.filter((entry) => entry !== name));
    setExampleId(null);
  }

  function update(key: string, patch: Partial<Entry>): void {
    setEntries((previous) =>
      previous.map((entry) =>
        entry.key === key ? { ...entry, ...patch } : entry,
      ),
    );
  }

  async function classifyOne(entry: Entry, signal: AbortSignal): Promise<void> {
    update(entry.key, { status: "running" });
    try {
      const formData = new FormData();
      formData.append("file", entry.file);
      formData.append("classes", classes.join(","));
      formData.append("parser", parserType);
      const response = await apiFetch("/api/classify", {
        method: "POST",
        body: formData,
        signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to classify the document");
      }
      const data = (await response.json()) as Classified;
      update(entry.key, {
        status: "done",
        result: { ...data, filename: entry.file.name },
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      update(entry.key, {
        status: "failed",
        error:
          error instanceof RateLimitError
            ? "Too many requests: wait a moment and try again"
            : error instanceof Error
              ? error.message
              : "An error occurred",
      });
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    if (entries.length === 0) {
      toast.error("Please add at least one document");
      return;
    }
    if (classes.length < 2) {
      toast.error("Please add at least 2 classes");
      return;
    }

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setEntries(clearResults(entries));
    setFilter(null);
    setOpen(null);
    setIsRunning(true);

    // A few documents at a time: the results arrive as each one finishes.
    const queue = [...entries];
    const worker = async (): Promise<void> => {
      for (
        let next = queue.shift();
        next && !controller.signal.aborted;
        next = queue.shift()
      )
        await classifyOne(next, controller.signal);
    };
    await Promise.all(Array.from({ length: WORKERS }, worker));
    setIsRunning(false);

    if (!controller.signal.aborted)
      posthog.capture("document_classified", {
        result_count: entries.length,
        classes_count: classes.length,
        parser: parserType,
        example: exampleId,
      });
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Tags}
        title="Classifier"
        description="Automatically sort documents into categories using AI"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Classifier"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from a ready-made set of documents
          </h2>
          <div
            role="radiogroup"
            aria-label="Ready-made sets"
            className="grid gap-3 sm:grid-cols-3"
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
                  <Badge variant="outline" className="font-normal">
                    {example.documents.length} documents
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {example.classes.length} classes
                  </Badge>
                </span>
              </button>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The documents</CardTitle>
              <CardDescription>
                Up to {MAX_FILES} files: PDF, DOCX, PNG or JPG, each up to{" "}
                {MAX_FILE_MB} MB.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <label
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (!busy && e.dataTransfer.files.length > 0)
                    addFiles(e.dataTransfer.files);
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
                  "flex min-h-[120px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 transition-all",
                  isDragging
                    ? "border-primary bg-primary/5"
                    : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50",
                  busy && "cursor-not-allowed opacity-50",
                )}
              >
                <Upload
                  className={cn(
                    "h-7 w-7",
                    isDragging ? "text-primary" : "text-muted-foreground",
                  )}
                />
                <p className="text-sm font-medium">
                  {isDragging
                    ? "Drop files here"
                    : "Drag & drop or click to add files"}
                </p>
                <input
                  type="file"
                  accept={ACCEPT_ATTR}
                  multiple
                  disabled={busy}
                  onChange={(e) => {
                    if (e.target.files) {
                      addFiles(e.target.files);
                      e.target.value = "";
                    }
                  }}
                  className="sr-only"
                />
              </label>

              {isLoadingExample && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading the documents…
                </p>
              )}

              {entries.length > 0 && (
                <ul className="max-h-72 space-y-1.5 overflow-auto">
                  {entries.map((entry) => (
                    <li
                      key={entry.key}
                      className="flex items-center gap-2 rounded-md border p-2"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {entry.file.name}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {formatFileSize(entry.file.size)}
                        </p>
                      </div>
                      {entry.status === "running" && (
                        <Loader2 className="text-primary h-4 w-4 animate-spin" />
                      )}
                      {entry.status === "done" && (
                        <Check className="h-4 w-4 text-emerald-600" />
                      )}
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        aria-label={`View ${entry.file.name}`}
                        onClick={() => setViewing(entry.file)}
                      >
                        <Eye />
                      </Button>
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        aria-label={`Remove ${entry.file.name}`}
                        onClick={() => removeFile(entry.key)}
                        disabled={busy}
                      >
                        <X />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. The classes</CardTitle>
              <CardDescription>
                Each document gets exactly one of them. Add at least two.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="class-input">Classes</Label>
                <div className="flex gap-2">
                  <Input
                    id="class-input"
                    value={classInput}
                    onChange={(e) => setClassInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addClasses();
                      }
                    }}
                    placeholder="Add a class, or several separated by commas"
                    disabled={busy}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={addClasses}
                    disabled={busy || !classInput.trim()}
                  >
                    Add
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {classes.map((name) => (
                    <Badge
                      key={name}
                      variant="secondary"
                      className="gap-1 py-1 pr-1 pl-2.5 text-sm"
                    >
                      {name}
                      <button
                        type="button"
                        aria-label={`Remove ${name}`}
                        disabled={busy}
                        onClick={() => removeClass(name)}
                        className="hover:bg-destructive hover:text-destructive-foreground rounded-full p-0.5"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                  <Badge variant="outline" className="py-1 text-sm font-normal">
                    unknown · added automatically
                  </Badge>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="classifier-parser">Parser</Label>
                <Select
                  value={parserType}
                  onValueChange={(value) =>
                    setParserType(value as ClassifierParser)
                  }
                  disabled={busy}
                >
                  <SelectTrigger id="classifier-parser">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CLASSIFIER_PARSERS.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-xs">{parser.hint}</p>
              </div>

              <Button
                onClick={() => void handleSubmit()}
                disabled={busy || entries.length === 0 || classes.length < 2}
                className="w-full"
                size="lg"
              >
                {isRunning ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Sorting {finished} of {entries.length}…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    {entries.length === 1
                      ? "Sort the document"
                      : entries.length > 1
                        ? `Sort ${entries.length} documents`
                        : "Sort"}
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isRunning && done.length === 0 && (
            <LoadingCard
              message="Analyzing documents…"
              subMessage={`${entries.length} documents, ${WORKERS} at a time`}
            />
          )}

          {started && (done.length > 0 || failed.length > 0) && (
            <Card>
              <CardHeader className="gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>Sorting result</CardTitle>
                  {match.checked > 0 && (
                    <Badge
                      variant="outline"
                      className={cn(
                        "font-normal",
                        match.matching === match.checked
                          ? "border-emerald-500 text-emerald-700"
                          : "border-amber-500 text-amber-700",
                      )}
                    >
                      {match.matching} of {match.checked} as expected
                    </Badge>
                  )}
                  <div className="ml-auto flex gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={done.length === 0}
                      onClick={() =>
                        download(
                          "classification.csv",
                          toCsv(done.map((entry) => entry.result)),
                          "text/csv;charset=utf-8",
                        )
                      }
                    >
                      <Download />
                      CSV
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={done.length === 0}
                      onClick={() =>
                        download(
                          "classification.json",
                          JSON.stringify(
                            done.map((entry) => entry.result),
                            null,
                            2,
                          ),
                          "application/json;charset=utf-8",
                        )
                      }
                    >
                      <Download />
                      JSON
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-muted-foreground text-sm">
                    Documents per class
                  </span>
                  <button
                    type="button"
                    aria-pressed={filter === null}
                    onClick={() => setFilter(null)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-sm transition-colors",
                      filter === null
                        ? "border-primary bg-primary/10 text-primary"
                        : "hover:border-primary/40",
                    )}
                  >
                    all
                    <span className="text-muted-foreground ml-1.5 text-xs">
                      {done.length}
                    </span>
                  </button>
                  {counts.map(([name, count]) => (
                    <button
                      key={name}
                      type="button"
                      aria-pressed={filter === name}
                      onClick={() => setFilter(filter === name ? null : name)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-sm transition-colors",
                        filter === name
                          ? "border-primary bg-primary/10 text-primary"
                          : "hover:border-primary/40",
                      )}
                    >
                      {name}
                      <span className="text-muted-foreground ml-1.5 text-xs">
                        {count}
                      </span>
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="bg-muted/50 text-xs tracking-wider uppercase">
                        <th className="px-3 py-2 font-medium">Document</th>
                        <th className="px-3 py-2 font-medium">Class</th>
                        <th className="px-3 py-2 font-medium">Confidence</th>
                        <th className="px-3 py-2 font-medium">Reasoning</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((entry) => {
                        const { result } = entry;
                        const answer = entry.expected;
                        const agrees =
                          answer === undefined
                            ? null
                            : answer.toLowerCase() ===
                              result.classification.toLowerCase();
                        const isOpen = open === entry.key;
                        return (
                          <tr
                            key={entry.key}
                            className="hover:bg-muted/30 border-t align-top"
                          >
                            <td className="px-3 py-2">
                              <button
                                type="button"
                                onClick={() => setViewing(entry.file)}
                                className="hover:text-primary text-left underline-offset-2 hover:underline"
                              >
                                {result.filename}
                              </button>
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <Badge
                                  variant={
                                    result.classification === "unknown"
                                      ? "outline"
                                      : "default"
                                  }
                                  className="px-2.5 py-0.5 text-sm"
                                >
                                  {result.classification}
                                </Badge>
                                {agrees === true && (
                                  <span
                                    title="As expected"
                                    className="text-emerald-600"
                                  >
                                    <Check className="h-4 w-4" />
                                  </span>
                                )}
                                {agrees === false && (
                                  <span className="text-xs text-amber-700">
                                    expected {answer}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2">
                              <ConfidenceMeter value={result.confidence} />
                            </td>
                            <td className="text-muted-foreground max-w-md px-3 py-2">
                              <button
                                type="button"
                                aria-expanded={isOpen}
                                onClick={() =>
                                  setOpen(isOpen ? null : entry.key)
                                }
                                className={cn(
                                  "text-left",
                                  !isOpen && "line-clamp-2",
                                )}
                              >
                                {result.reasoning || "No reasoning given"}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                      {failed.map((entry) => (
                        <tr key={entry.key} className="border-t align-top">
                          <td className="px-3 py-2">{entry.file.name}</td>
                          <td
                            colSpan={3}
                            className="text-destructive px-3 py-2 text-sm"
                          >
                            {entry.error}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {isRunning && (
                  <p className="text-muted-foreground text-sm">
                    {finished} of {entries.length} sorted…
                  </p>
                )}
                <FeedbackButton demoType="classifier" />
              </CardContent>
            </Card>
          )}

          {!started && !isRunning && (
            <EmptyStateCard
              icon={Tags}
              title="No classification yet"
              description="Add documents, check the classes, and click Sort. Each document gets one class, a confidence score and the reason."
              feedbackSlot={<FeedbackButton demoType="classifier" />}
            />
          )}
        </div>
      </div>

      <FileViewer file={viewing} onClose={() => setViewing(null)} />
    </PageTransition>
  );
}
