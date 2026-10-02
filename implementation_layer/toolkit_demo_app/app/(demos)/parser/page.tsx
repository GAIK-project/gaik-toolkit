"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  Columns2,
  FileSearch,
  FileText,
  Loader2,
  ScanText,
  Search,
  Upload,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  ACCEPTED_FILES,
  PARSERS,
  type ParserType,
} from "../extractor/extractor-data";
import { ParsedPane, parserLabel, type ParseRun } from "./parsed-pane";
import { EXAMPLES, type ParserExample } from "./parser-data";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add a document",
    text: "Upload a PDF, Word file or image, or start from a ready-made document.",
  },
  {
    icon: ScanText,
    title: "Choose the parser",
    text: "Each parser reads in its own way. Pick one that fits the document, then read it.",
  },
  {
    icon: Search,
    title: "Explore the output",
    text: "See it rendered, as markdown or as plain text. Search it, jump by outline, copy or download it.",
  },
  {
    icon: Columns2,
    title: "Compare parsers",
    text: "Read the same document with another parser and compare the two outputs side by side.",
  },
];
const GUIDE_NOTES = [
  "Vision and Vision+ read at most 10 pages. Multimodal reads PDF files only.",
  "Nothing is saved: the document and its parsed output stay in this session.",
];

const VIEWABLE_IMAGE = /\.(png|jpe?g|gif|webp|bmp)$/i;

/** The uploaded document as it looks, next to what the parser made of it. */
function OriginalPreview({ file }: { file: File }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const next = URL.createObjectURL(file);
    // The object URL is made here, and revoked below, so it belongs in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);

  const isPdf = /\.pdf$/i.test(file.name);
  const isImage = VIEWABLE_IMAGE.test(file.name);

  return (
    <div className="bg-card min-w-0 space-y-3 rounded-xl border p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">Original document</h3>
        <Badge variant="outline" className="font-normal">
          {file.name}
        </Badge>
      </div>
      <div className="bg-muted/30 max-h-[40rem] overflow-auto rounded-md border">
        {url && isPdf && (
          <iframe
            src={url}
            title="The original document"
            className="h-[40rem] w-full"
          />
        )}
        {url && isImage && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={file.name}
            className="mx-auto h-auto max-w-full"
          />
        )}
        {!isPdf && !isImage && (
          <p className="text-muted-foreground p-6 text-center text-sm">
            A preview is not available for this file type.
          </p>
        )}
      </div>
    </div>
  );
}

export default function ParserPage() {
  const [file, setFile] = useState<File | null>(null);
  const [parserType, setParserType] = useState<ParserType>("docling_api");
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [runs, setRuns] = useState<ParseRun[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const [otherId, setOtherId] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isLoading || isLoadingExample;
  const parser =
    PARSERS.find((option) => option.id === parserType) ?? PARSERS[0];
  const active = runs.find((run) => run.id === activeId) ?? runs[0] ?? null;
  const other =
    runs.find((run) => run.id === otherId && run.id !== active?.id) ??
    runs.find((run) => run.id !== active?.id) ??
    null;
  const comparing = compare && active !== null && other !== null;

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  function resetRuns(): void {
    setRuns([]);
    setActiveId(null);
    setOtherId(null);
    setCompare(false);
  }

  function handleFile(next: File): void {
    setFile(next);
    setExampleId(null);
    resetRuns();
  }

  async function pickExample(example: ParserExample): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    try {
      const response = await fetch(example.url);
      if (!response.ok) throw new Error("Could not load the example");
      const blob = await response.blob();
      setFile(
        new File([blob], example.fileName, {
          type: blob.type || "application/octet-stream",
        }),
      );
      setParserType(example.parser);
      setExampleId(example.id);
      resetRuns();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    if (!file) {
      toast.error("Please select a file first");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    const started = performance.now();

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", parserType);

      const response = await apiFetch("/api/parse", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to parse document");
      }

      const data = await response.json();
      const run: ParseRun = {
        id: parserType,
        // The HH Parser can fall back to PyMuPDF: the metadata says which one read it.
        parser: String(data.metadata?.parser ?? data.parser ?? parserType),
        text: String(data.text_content ?? ""),
        metadata: data.metadata ?? {},
        seconds: (performance.now() - started) / 1000,
        filename: String(data.filename ?? file.name),
        html: typeof data.html === "string" ? data.html : undefined,
      };
      // One run is kept for each parser: reading again replaces it.
      setRuns((previous) => [
        ...previous.filter((entry) => entry.id !== run.id),
        run,
      ]);
      setActiveId(run.id);

      posthog.capture("document_parsed", {
        file_type: file.type,
        file_size: file.size,
        parser_used: run.parser,
        example: exampleId,
      });
      toast.success("Document parsed successfully!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FileText}
        title="Parser"
        description="Read text and layout from PDF, Word files, and images accurately"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Parser"
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
            {EXAMPLES.map((example) => (
              <div
                key={example.id}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 transition-all",
                  exampleId === example.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={exampleId === example.id}
                  disabled={busy}
                  onClick={() => void pickExample(example)}
                  className="flex flex-1 flex-col gap-1.5 text-left"
                >
                  <span className="font-semibold">{example.title}</span>
                  <span className="text-muted-foreground text-sm">
                    {example.summary}
                  </span>
                  <span>
                    <Badge variant="outline" className="font-normal">
                      {example.why}
                    </Badge>
                  </span>
                </button>
                <ExamplePreviewDialog
                  exampleUrl={example.url}
                  exampleName={example.fileName}
                  onUseExample={() => void pickExample(example)}
                  disabled={busy}
                  label="View document"
                  buttonSize="xs"
                />
              </div>
            ))}
          </div>
        </section>

        <Card>
          <CardHeader>
            <CardTitle>The document and the parser</CardTitle>
            <CardDescription>
              Upload a file, choose how it is read, and read it. Reading it
              again with another parser adds a second output to compare.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid items-start gap-6 lg:grid-cols-2">
            <FileUpload
              accept={ACCEPTED_FILES}
              maxSize={20}
              file={file}
              onFileSelect={handleFile}
              onFileRemove={() => {
                setFile(null);
                setExampleId(null);
                resetRuns();
              }}
              disabled={busy}
            />
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="parser-type">Parser</Label>
                <Select
                  value={parserType}
                  onValueChange={(value) => setParserType(value as ParserType)}
                  disabled={busy}
                >
                  <SelectTrigger id="parser-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PARSERS.map((option) => (
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
                disabled={!file || busy}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Parsing…
                  </>
                ) : (
                  <>
                    <FileSearch className="mr-2 h-4 w-4" />
                    {runs.some((run) => run.id === parserType)
                      ? "Read it again"
                      : "Read document"}
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4" aria-live="polite">
          {runs.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">Outputs</span>
              {runs.map((run) => (
                <button
                  key={run.id}
                  type="button"
                  onClick={() => setActiveId(run.id)}
                  aria-pressed={active?.id === run.id}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm transition-colors",
                    active?.id === run.id
                      ? "border-primary bg-primary/10 text-primary"
                      : "hover:border-primary/40",
                  )}
                >
                  {parserLabel(run.parser)}
                  <span className="text-muted-foreground ml-1.5 text-xs">
                    {run.text.length.toLocaleString()} chars
                  </span>
                </button>
              ))}
              {runs.length > 1 && (
                <Button
                  size="sm"
                  variant={compare ? "secondary" : "outline"}
                  onClick={() => setCompare(!compare)}
                  aria-pressed={compare}
                  className="ml-auto"
                >
                  <Columns2 />
                  Compare
                </Button>
              )}
            </div>
          )}

          {isLoading && (
            <LoadingCard
              message="Parsing document…"
              subMessage={`With the ${parser.label.split(" (")[0]} parser`}
            />
          )}

          {active && !isLoading && comparing && other && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">Compare with</span>
                <Select
                  value={other.id}
                  onValueChange={(value) => setOtherId(value)}
                >
                  <SelectTrigger className="w-56" aria-label="Compare with">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {runs
                      .filter((run) => run.id !== active.id)
                      .map((run) => (
                        <SelectItem key={run.id} value={run.id}>
                          {parserLabel(run.parser)}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid items-start gap-4 lg:grid-cols-2">
                <ParsedPane key={`a-${active.id}`} run={active} idPrefix="a-" />
                <ParsedPane key={`b-${other.id}`} run={other} idPrefix="b-" />
              </div>
            </div>
          )}

          {active && !isLoading && !comparing && file && (
            <div className="grid items-start gap-4 lg:grid-cols-2">
              <OriginalPreview file={file} />
              <ParsedPane key={active.id} run={active} idPrefix="a-" />
            </div>
          )}

          {runs.length === 0 && !isLoading && (
            <EmptyStateCard
              icon={Wand2}
              title="No parsed output yet"
              description="Upload a document and click Read document. The output appears here next to the original, with search, outline and downloads."
              feedbackSlot={<FeedbackButton demoType="parser" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
