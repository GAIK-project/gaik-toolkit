"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
import {
  schemaTabs,
  type ExtraTab,
  type SchemaViewData,
} from "@/components/demo/schema-views";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { StepIndicator } from "@/components/demo/step-indicator";
import { TaskChangeNotice } from "@/components/demo/task-change-notice";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import {
  reusableSchemaId,
  savedSchemaKey,
  type MadeSchema,
} from "@/lib/schema-reuse";
import { processSSEStream, type SSEStep } from "@/lib/sse";
import { cn } from "@/lib/utils";
import {
  ClipboardList,
  Download,
  FileOutput,
  FileSearch,
  FileText,
  Loader2,
  ScanText,
  Sparkles,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { PARSERS, type ParserType } from "../extractor/extractor-data";
import { ResultView } from "../extractor/result-view";
import { ParsedPane } from "../parser/parsed-pane";
import {
  DEFAULT_OPTIONS,
  EXAMPLES,
  formFields,
  isPageLimited,
  parserAccepts,
  timingText,
  type DocumentExample,
  type DocumentOptions,
  type Timings,
} from "./document-data";

const STRUCTURE_TEXT: Record<string, string> = {
  flat: "One record: one set of fields for the document.",
  nested_list:
    "A list of records: the document holds several records of one kind.",
  parent_with_nested_list:
    "A header with a list inside: document fields plus repeated rows.",
};

type DocumentResult = SchemaViewData & {
  job_id: string;
  parsed_content: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  parser: string;
  parsed_html?: string | null;
  parse_metadata?: Record<string, unknown>;
  schema_source?: "saved" | "generated" | "reused";
  schema_id?: string | null;
  timings?: Timings;
};

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: FileText,
    title: "Add a document",
    text: "Upload a PDF, Word file or image, or start from a ready-made document with the parser and task that suit it.",
  },
  {
    icon: ScanText,
    title: "Choose the parser",
    text: "The parser turns the file into text. A text PDF needs a fast one; a scan or a photo needs a vision model.",
  },
  {
    icon: ClipboardList,
    title: "Say what to extract",
    text: "Describe the fields in plain words, including lists. The task decides the shape of the result.",
  },
  {
    icon: FileSearch,
    title: "Check the result",
    text: "Read the data, then the text it came from, and the schema that was made for it.",
  },
];
const GUIDE_NOTES = [
  "Three steps run in turn: the document is parsed to text, a schema is made from your task, and the data is extracted from the text. If the parser misses something, the data does too, so read the parsed text.",
  "Nothing you enter is saved. The examples come with a ready-made schema. A schema made for your own task, or for an edited example, lives in this session only and is used again while the task stays the same.",
];

const ACCEPT = ".pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp";

export default function DocumentStructuredPage() {
  const [file, setFile] = useState<File | null>(null);
  const [example, setExample] = useState<DocumentExample | null>(EXAMPLES[0]);
  const [task, setTask] = useState(EXAMPLES[0].task);
  const [options, setOptions] = useState<DocumentOptions>({
    ...DEFAULT_OPTIONS,
    ...EXAMPLES[0].options,
  });
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<SSEStep[]>([]);
  const [result, setResult] = useState<DocumentResult | null>(null);
  const [resultName, setResultName] = useState("");
  const [seconds, setSeconds] = useState<number | null>(null);
  // The schema of the last run: while the task is unchanged it is used again.
  const [madeSchema, setMadeSchema] = useState<MadeSchema | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isLoading || isLoadingExample;
  const set = (patch: Partial<DocumentOptions>) =>
    setOptions((previous) => ({ ...previous, ...patch }));
  const parser =
    PARSERS.find((entry) => entry.id === options.parser) ?? PARSERS[0];
  const wrongType = file !== null && !parserAccepts(options.parser, file.name);
  const reusable = reusableSchemaId(madeSchema, task) !== null;
  // The text differs from the one the schema in hand was made from: the example's own
  // (ready-made) task, or the task of the last run. A new schema is made for it.
  const changed =
    !reusable &&
    (example ? task.trim() !== example.task.trim() : madeSchema !== null);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  // The first example is loaded and selected when the page opens.
  useEffect(() => {
    void pickExample(EXAMPLES[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clearResult(): void {
    setResult(null);
    setSteps([]);
    setSeconds(null);
  }

  async function pickExample(next: DocumentExample): Promise<void> {
    if (isLoading) return;
    setIsLoadingExample(true);
    try {
      const response = await fetch(next.url);
      if (!response.ok) throw new Error("Could not load the document");
      const blob = await response.blob();
      setFile(
        new File([blob], next.fileName, {
          type: blob.type || "application/octet-stream",
        }),
      );
      setExample(next);
      setTask(next.task);
      setOptions({ ...DEFAULT_OPTIONS, ...next.options });
      setMadeSchema(null);
      clearResult();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy || !file) return;
    if (!task.trim()) {
      toast.error("Describe what to extract");
      return;
    }
    if (wrongType) {
      toast.error(
        `The ${parser.label.split(" (")[0]} parser cannot read this type of file`,
      );
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    clearResult();
    const started = performance.now();

    try {
      const formData = new FormData();
      formData.append("file", file);
      for (const [key, value] of formFields(
        options,
        task,
        savedSchemaKey(example, task),
        reusableSchemaId(madeSchema, task),
      ))
        formData.append(key, value);

      const response = await apiFetch("/api/pipeline/document/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) throw new Error("Failed to process the document");

      let streamError: Error | null = null;
      await processSSEStream<DocumentResult>(response, {
        onSteps: (next) => setSteps(next),
        onStepUpdate: (update) =>
          setSteps((previous) =>
            previous.map((step) => (step.step === update.step ? update : step)),
          ),
        onResult: (data) => {
          setResultName(file.name);
          setResult(data);
          setSeconds((performance.now() - started) / 1000);
          setMadeSchema(data.schema_id ? { id: data.schema_id, task } : null);
          posthog.capture("document_structured_executed", {
            parser_type: options.parser,
            generate_pdf: options.generatePdf,
            items: data.extracted_data?.length ?? 0,
            schema_source: data.schema_source,
            example: example?.id ?? null,
          });
          toast.success("Document processed");
        },
        onError: (message) => {
          streamError = new Error(message);
        },
      });
      if (streamError) throw streamError;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      setSteps((previous) =>
        previous.map((step) =>
          step.status === "in_progress"
            ? {
                ...step,
                status: "error" as const,
                message:
                  error instanceof Error ? error.message : "Processing failed",
              }
            : step,
        ),
      );
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDownloadPdf(): Promise<void> {
    if (!result?.job_id) return;
    try {
      const response = await apiFetch(`/api/pipeline/pdf/${result.job_id}`);
      if (!response.ok) throw new Error("Failed to download PDF");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `document_structured_${result.job_id.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download PDF");
    }
  }

  // After Readable and JSON: the schema in three forms, then the text the data came from.
  const extraTabs: ExtraTab[] = result
    ? [
        ...schemaTabs(result, STRUCTURE_TEXT[result.structure_type]),
        ...(result.parsed_content
          ? [
              {
                value: "parsed",
                label: "Parsed document",
                content: (
                  <ParsedPane
                    key={result.job_id}
                    idPrefix="doc-"
                    run={{
                      id: result.parser,
                      parser: result.parser,
                      text: result.parsed_content,
                      metadata: result.parse_metadata ?? {},
                      seconds: result.timings?.parse_s ?? 0,
                      filename: resultName,
                      html: result.parsed_html ?? undefined,
                    }}
                  />
                ),
              },
            ]
          : []),
      ]
    : [];

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FileOutput}
        title="Document → Structured Data"
        description="Turn a document or an image into structured data: it is parsed to text, and the fields you describe are extracted from it"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use Document → Structured Data"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from a ready-made document
          </h2>
          <div
            role="radiogroup"
            aria-label="Ready-made documents"
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
          >
            {EXAMPLES.map((entry) => (
              <div
                key={entry.id}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border-2 p-3 transition-all",
                  example?.id === entry.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={example?.id === entry.id}
                  disabled={busy}
                  onClick={() => void pickExample(entry)}
                  className="flex flex-1 flex-col gap-1.5 text-left"
                >
                  <span className="font-semibold">{entry.title}</span>
                  <span className="text-primary text-xs font-medium">
                    {entry.shape}
                  </span>
                  <span className="text-muted-foreground text-sm">
                    {entry.summary}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {entry.tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="outline"
                        className="font-normal"
                      >
                        {tag}
                      </Badge>
                    ))}
                  </span>
                </button>
                <ExamplePreviewDialog
                  exampleUrl={entry.url}
                  exampleName={entry.fileName}
                  onUseExample={() => void pickExample(entry)}
                  disabled={busy}
                  label="View document"
                  buttonSize="xs"
                />
              </div>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>1. The document</CardTitle>
                <CardDescription>
                  A PDF, Word file or image, up to 20 MB.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FileUpload
                  compact
                  file={file}
                  accept={ACCEPT}
                  maxSize={20}
                  onFileSelect={(next) => {
                    setFile(next);
                    setExample(null);
                    clearResult();
                  }}
                  onFileRemove={() => {
                    setFile(null);
                    setExample(null);
                    clearResult();
                  }}
                  disabled={busy}
                />
                {isLoadingExample && (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading the document…
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>2. The parser</CardTitle>
                <CardDescription>
                  How the file is turned into text. The ready-made documents set
                  the one that suits them.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Label htmlFor="parser-type">Parser</Label>
                <Select
                  value={options.parser}
                  onValueChange={(value) =>
                    set({ parser: value as ParserType })
                  }
                  disabled={busy}
                >
                  <SelectTrigger id="parser-type">
                    <SelectValue placeholder="Select parser" />
                  </SelectTrigger>
                  <SelectContent>
                    {PARSERS.map((entry) => (
                      <SelectItem key={entry.id} value={entry.id}>
                        {entry.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-xs">{parser.hint}</p>
                {isPageLimited(options.parser) && (
                  <p className="text-xs text-amber-700">
                    This parser reads at most 10 pages of a document.
                  </p>
                )}
                {wrongType && (
                  <p className="text-destructive text-xs">
                    This parser cannot read the type of the file you added.
                    Choose another one.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>3. What to extract</CardTitle>
              <CardDescription>
                Describe the fields in plain words. Ask for a list, and you get
                one row for each item.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                aria-label="What to extract"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Describe what data to extract…"
                disabled={busy}
                rows={12}
              />
              {changed ? (
                <TaskChangeNotice />
              ) : (
                <p className="text-muted-foreground text-xs">
                  {reusable
                    ? "The schema of the last run is used again, so only the parsing and the extraction run. Change the text and a new schema is generated."
                    : example
                      ? "This task has a ready-made schema, so no time goes on making one. Change the text and a new schema is generated."
                      : "A schema is generated from this text the first time you run it, and used again while the text stays the same. Name the type of a field (number, yes or no, date) and the allowed values to get them exactly."}
                </p>
              )}

              <div className="flex items-start justify-between gap-4">
                <div className="space-y-0.5">
                  <Label htmlFor="generate-pdf">Make a PDF report</Label>
                  <p className="text-muted-foreground text-xs">
                    A PDF with the extracted data, to download after the run.
                  </p>
                </div>
                <Switch
                  id="generate-pdf"
                  checked={options.generatePdf}
                  onCheckedChange={(value) => set({ generatePdf: value })}
                  disabled={busy}
                />
              </div>

              <Button
                onClick={() => void handleSubmit()}
                disabled={!file || busy || wrongType}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Extract data
                  </>
                )}
              </Button>
              {!file && (
                <p className="text-muted-foreground text-center text-xs">
                  Add a document first.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <Card>
              <CardHeader>
                <CardTitle>Processing</CardTitle>
                <CardDescription>
                  Parsing, making the schema, then extracting. A scan read by a
                  vision model takes the longest.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {steps.length > 0 ? (
                  <StepIndicator steps={steps} />
                ) : (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting…
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {!isLoading && !result && steps.some((s) => s.status === "error") && (
            <Card>
              <CardHeader>
                <CardTitle>Processing stopped</CardTitle>
              </CardHeader>
              <CardContent>
                <StepIndicator steps={steps} />
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <ResultView
              results={result.extracted_data ?? []}
              documentCount={1}
              noun="document"
              seconds={seconds}
              detail={timingText(result.timings)}
              extraTabs={extraTabs}
            >
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="outline" className="font-normal">
                  {resultName}
                </Badge>
                {result.parser && (
                  <Badge variant="outline" className="font-normal">
                    {PARSERS.find(
                      (entry) => entry.id === result.parser,
                    )?.label.split(" (")[0] ?? result.parser}
                  </Badge>
                )}
                {result.schema_source === "saved" && (
                  <Badge variant="outline" className="font-normal">
                    ready-made schema
                  </Badge>
                )}
                {result.schema_source === "reused" && (
                  <Badge variant="outline" className="font-normal">
                    schema from the last run
                  </Badge>
                )}
                {result.pdf_available && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void handleDownloadPdf()}
                  >
                    <Download />
                    Download PDF report
                  </Button>
                )}
                <FeedbackButton demoType="document-structured" />
              </div>
              {(result.extracted_data?.length ?? 0) === 0 && (
                <p className="text-muted-foreground text-sm">
                  Nothing was extracted. Open the parsed document: the parser
                  may have missed the text, or the document may not say what the
                  task asks for.
                </p>
              )}
            </ResultView>
          )}

          {!result &&
            !isLoading &&
            !steps.some((s) => s.status === "error") && (
              <EmptyStateCard
                icon={Wand2}
                title="No structured data yet"
                description="Add a document and click Extract data. The data appears here, with the text it came from."
                feedbackSlot={<FeedbackButton demoType="document-structured" />}
              />
            )}
        </div>
      </div>
    </PageTransition>
  );
}
