"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import type { SchemaField } from "@/components/demo/schema-fields-table";
import { schemaTabs, SchemaTabsView } from "@/components/demo/schema-views";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
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
import { useModelSettings } from "@/lib/model-settings-store";
import { useActiveServerModel } from "@/lib/server-model-store";
import { cn } from "@/lib/utils";
import {
  Database,
  FileText,
  ListChecks,
  Loader2,
  Plus,
  ScanText,
  Sparkles,
  Table2,
  Trash2,
  Upload,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { DocumentUpload } from "./document-upload";
import {
  DEFAULT_PARSER,
  combineDocuments,
  type ReadMode,
  EXAMPLES,
  PARSERS,
  type ExtractorExample,
  type ParserType,
} from "./extractor-data";
import {
  SourcesView,
  TraceSourcesSwitch,
  type SourcesResult,
} from "../vision-extractor/sources-view";
import { ResultView } from "./result-view";

interface Field {
  name: string;
  description: string;
}

interface ExtractResult {
  results: Record<string, unknown>[];
  document_count: number;
  /** With Trace sources: each quote checked, and located in the PDF when there is one. */
  sources?: SourcesResult | null;
  raw_sources?: unknown[] | null;
  /** With several documents: the checked quotes of each, in the order of the documents. */
  document_sources?: (SourcesResult | null)[] | null;
}

interface GeneratedSchema {
  schema_code: string;
  schema_name: string;
  structure_type: string;
  schema_id: string;
  fields: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
  }>;
  /** Newer servers: every field with its plain type, rule and nested records. */
  field_table?: SchemaField[];
  /** The requirements the schema was built from, as JSON. */
  requirements_json?: string;
  /** saved: the ready-made schema of an example. reused: made earlier in this session. */
  schema_source?: "saved" | "reused" | "generated";
}

type Phase = "schema" | "extracting" | null;

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Add the documents",
    text: "Upload one or several PDF, Word or image files, paste text, or start from a ready-made document.",
  },
  {
    icon: ScanText,
    title: "Choose how it is read",
    text: "For uploaded files, pick the parser that reads them. Auto-detect chooses by file type, for each file.",
  },
  {
    icon: ListChecks,
    title: "Say what to extract",
    text: "Describe it in words and generate the schema, or list the fields yourself.",
  },
  {
    icon: Table2,
    title: "Review the result",
    text: "Every field is shown, also those with no value, with one result for each document. Copy or download the JSON.",
  },
];
const GUIDE_NOTES = [
  "Trace sources asks the model for the exact text each value came from. The quote is checked against the text and, for a PDF, located and highlighted on its page, so a value can be checked at a glance.",
  "Auto-detect reads a PDF with PyMuPDF, a Word file with DOCX and an image with Vision. A scanned PDF has no text layer: choose Vision, Vision+, Multimodal or the HH Parser.",
  "Nothing you enter is saved. The examples come with a ready-made schema. A schema generated for your own task, or for an edited example, lives in this session only and is used again while the task stays the same.",
];

const STRUCTURE_TEXT: Record<string, string> = {
  flat: "One record: one set of fields for each document.",
  nested_list:
    "A list of records: the document holds several records of one kind.",
  parent_with_nested_list:
    "A header with a list inside: document fields plus repeated rows.",
};

const DEFAULT_FIELDS: Field[] = [
  { name: "company_name", description: "Name of the company or organization" },
  { name: "total_amount", description: "Total amount or price" },
  { name: "date", description: "Date of the document" },
];

const DEFAULT_TASK = EXAMPLES[0].task;

/** The checked quotes of the results: one document at a time when there are several. */
function DocumentSources({
  names,
  sources,
}: {
  names: string[];
  sources: (SourcesResult | null)[];
}) {
  const [selected, setSelected] = useState(0);
  const index = Math.min(selected, sources.length - 1);
  const current = sources[index];
  return (
    <div className="space-y-3">
      {sources.length > 1 && (
        <div className="max-w-sm space-y-1">
          <Label htmlFor="sources-document">Document</Label>
          <Select
            value={String(index)}
            onValueChange={(value) => setSelected(Number(value))}
          >
            <SelectTrigger id="sources-document">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sources.map((_, position) => (
                <SelectItem key={position} value={String(position)}>
                  {names[position] ?? `Document ${position + 1}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      {current ? (
        <SourcesView key={index} result={current} />
      ) : (
        <p className="text-muted-foreground text-sm">
          The model returned no sources for this document.
        </p>
      )}
    </div>
  );
}

export default function ExtractorPage() {
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [documentText, setDocumentText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [includeSources, setIncludeSources] = useState(true);
  const [parserType, setParserType] = useState<ParserType>(DEFAULT_PARSER);
  const [isParsing, setIsParsing] = useState(false);
  // Several files: one result for each, or one result from all of them read together.
  const [readMode, setReadMode] = useState<ReadMode>("separate");
  // With combined files, how many files the one result was read from.
  const [combinedCount, setCombinedCount] = useState<number | null>(null);
  // Which uploaded file is being read, and of how many (1-based), while several are.
  const [reading, setReading] = useState<{ index: number; total: number }>({
    index: 1,
    total: 1,
  });

  const [mode, setMode] = useState<"plain-language" | "fields">(
    "plain-language",
  );
  const [task, setTask] = useState(DEFAULT_TASK);
  const [userRequirements, setUserRequirements] = useState(
    "Extract key information from this document",
  );
  const [fields, setFields] = useState<Field[]>(DEFAULT_FIELDS);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDesc, setNewFieldDesc] = useState("");
  const [schema, setSchema] = useState<
    (GeneratedSchema & { task: string }) | null
  >(null);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);

  const [exampleId, setExampleId] = useState<string | null>(null);
  // The task of the example that was picked: editing the text does not change it.
  const [exampleTask, setExampleTask] = useState<string | null>(DEFAULT_TASK);
  const [isLoading, setIsLoading] = useState(false);
  const [phase, setPhase] = useState<Phase>(null);
  const [result, setResult] = useState<ExtractResult | null>(null);
  // The schema the result was extracted with: it stays with the result when the task changes.
  const [resultSchema, setResultSchema] = useState<GeneratedSchema | null>(
    null,
  );
  // What each result was read from: file names, or "Pasted text".
  const [resultNames, setResultNames] = useState<string[]>([]);
  const [seconds, setSeconds] = useState<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const ownModel = useModelSettings();
  const serverModel = useActiveServerModel();

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  const schemaCurrent = schema !== null && schema.task === task.trim();
  // The text no longer matches the schema in hand (or, before any schema, the picked
  // example): a new schema is generated at the next run.
  // The text is exactly the task of an example, which has a committed schema (also after
  // the text was edited and put back).
  const readyMade = EXAMPLES.some((e) => e.task.trim() === task.trim());
  const taskChanged = schema
    ? !schemaCurrent
    : exampleTask !== null && task.trim() !== exampleTask.trim();
  const busy = isLoading || isParsing || isGeneratingSchema;
  const hasInput =
    inputMode === "text" ? documentText.trim().length > 0 : files.length > 0;
  const parser = PARSERS.find((p) => p.id === parserType) ?? PARSERS[0];
  const readingMessage =
    reading.total > 1
      ? `Reading document ${reading.index} of ${reading.total}…`
      : "Reading the document…";

  async function pickExample(example: ExtractorExample): Promise<void> {
    setExampleId(example.id);
    setMode("plain-language");
    setTask(example.task);
    setExampleTask(example.task);
    setSchema(null);
    setResult(null);
    try {
      const response = await fetch(example.url);
      if (!response.ok) throw new Error("Could not load the example");
      const blob = await response.blob();
      setFiles([
        new File([blob], example.fileName, {
          type: blob.type || "application/pdf",
        }),
      ]);
      setInputMode("file");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed");
    }
  }

  function handleAddField(): void {
    if (!newFieldName.trim() || !newFieldDesc.trim()) return;
    const fieldKey = newFieldName.trim().toLowerCase().replace(/\s+/g, "_");
    if (fields.some((f) => f.name === fieldKey)) {
      toast.error("Field already exists");
      return;
    }
    setFields([
      ...fields,
      { name: fieldKey, description: newFieldDesc.trim() },
    ]);
    setNewFieldName("");
    setNewFieldDesc("");
  }

  /** Reads a file with the chosen parser; null if it failed. */
  async function parseFile(file: File): Promise<string | null> {
    setIsParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", parserType);
      const response = await apiFetch("/api/parse", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current?.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to parse document");
      }
      const data = await response.json();
      return String(data.text_content ?? "");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return null;
      if (error instanceof RateLimitError) return null;
      toast.error(
        error instanceof Error ? error.message : "Failed to parse file",
      );
      return null;
    } finally {
      setIsParsing(false);
    }
  }

  async function generateSchema(): Promise<
    (GeneratedSchema & { task: string }) | null
  > {
    if (!task.trim()) {
      toast.error("Please provide extraction requirements");
      return null;
    }
    setIsGeneratingSchema(true);
    try {
      const response = await apiFetch("/api/extract/generate-schema", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: task }),
        signal: abortControllerRef.current?.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }
      const data = (await response.json()) as GeneratedSchema;
      const next = { ...data, task: task.trim() };
      setSchema(next);
      posthog.capture("schema_generated", {
        structure_type: data.structure_type,
        fields_count: data.fields?.length || 0,
      });
      return next;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return null;
      if (error instanceof RateLimitError) return null;
      toast.error(
        error instanceof Error ? error.message : "Failed to generate schema",
      );
      return null;
    } finally {
      setIsGeneratingSchema(false);
    }
  }

  async function handleGenerateSchema(): Promise<void> {
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    const next = await generateSchema();
    if (next) toast.success("Schema generated");
  }

  /** The quotes of one extraction, located in the PDF or PDFs the text was read from. */
  async function traceInPdf(
    pdfs: File[],
    rawSources: unknown,
    record: Record<string, unknown>,
  ): Promise<SourcesResult | null> {
    const formData = new FormData();
    for (const pdf of pdfs) formData.append("file", pdf);
    formData.append("sources", JSON.stringify(rawSources ?? null));
    formData.append("data", JSON.stringify(record ?? {}));
    try {
      const response = await apiFetch("/api/extract/trace", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current?.signal,
      });
      return response.ok ? ((await response.json()) as SourcesResult) : null;
    } catch {
      return null;
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    if (mode === "fields") {
      if (!userRequirements.trim()) {
        toast.error("Please provide extraction requirements");
        return;
      }
      if (fields.length === 0) {
        toast.error("Please add at least one field to extract");
        return;
      }
    } else if (!task.trim()) {
      toast.error("Please provide extraction requirements");
      return;
    }

    // The texts to extract from: the pasted text, or each file read by the parser.
    const texts: string[] = [];
    const names: string[] = [];
    const combined =
      inputMode === "file" && files.length > 1 && readMode === "combined";
    if (inputMode === "file") {
      if (files.length === 0) {
        toast.error("Please select a file first");
        return;
      }
      for (const [index, file] of files.entries()) {
        setReading({ index: index + 1, total: files.length });
        const readable = await parseFile(file);
        if (readable === null) return;
        if (!readable.trim()) {
          toast.error(
            `The parser found no text in ${file.name}. Try another parser.`,
          );
          return;
        }
        texts.push(readable);
        names.push(file.name);
      }
      if (combined) {
        const joined = combineDocuments(
          texts.map((text, index) => ({ name: names[index], text })),
        );
        texts.splice(0, texts.length, joined);
        names.splice(0, names.length, `${names.length} files combined`);
      }
    } else {
      if (!documentText.trim()) {
        toast.error("Please provide document text");
        return;
      }
      texts.push(documentText);
      names.push("Pasted text");
    }

    setIsLoading(true);
    setResult(null);
    setSeconds(null);
    const started = performance.now();

    let usedSchema: GeneratedSchema | null = null;
    try {
      let response: Response;
      if (mode === "fields") {
        setPhase("extracting");
        response = await apiFetch("/api/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: texts,
            user_requirements: userRequirements,
            include_sources: includeSources,
            fields: Object.fromEntries(
              fields.map((field) => [field.name, field.description]),
            ),
          }),
          signal: abortControllerRef.current.signal,
        });
      } else {
        // The schema is generated first when there is none for this task. It is kept in
        // memory only: nothing is saved by this demo.
        let current = schemaCurrent ? schema : null;
        if (!current) {
          setPhase("schema");
          current = await generateSchema();
          if (!current) return;
        }
        usedSchema = current;
        setPhase("extracting");
        response = await apiFetch("/api/extract/plain-language", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: texts,
            user_requirements: task,
            schema_id: current.schema_id,
            include_sources: includeSources,
          }),
          signal: abortControllerRef.current.signal,
        });
      }

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to extract data");
      }
      const data = (await response.json()) as ExtractResult;
      // A PDF can show where each quote is: each document's quotes are located in it.
      if (data.sources || data.document_sources) {
        const perDocument = data.document_sources ?? [data.sources ?? null];
        data.document_sources = await Promise.all(
          perDocument.map(async (checked, index) => {
            // Combined: the quotes are of the joined text, so they are looked up in all the
            // files, when all of them are PDFs (a Word file has no pages to point at).
            const isPdf = (file: File) =>
              file.name.toLowerCase().endsWith(".pdf");
            const pdfs =
              inputMode !== "file"
                ? []
                : combined
                  ? files
                  : files[index]
                    ? [files[index]]
                    : [];
            const raw = data.raw_sources?.[index];
            if (pdfs.length === 0 || !pdfs.every(isPdf) || !raw) {
              return checked;
            }
            const located = await traceInPdf(
              pdfs,
              raw,
              data.results[index] ?? {},
            );
            return located ?? checked;
          }),
        );
        data.sources = data.document_sources[0] ?? data.sources;
      }
      setResult(data);
      setResultNames(names);
      setCombinedCount(combined ? files.length : null);
      setResultSchema(usedSchema);
      setSeconds((performance.now() - started) / 1000);
      posthog.capture("data_extracted", {
        input_mode: inputMode,
        extraction_mode: mode,
        parser: inputMode === "file" ? parserType : null,
        documents_count: combined ? files.length : texts.length,
        read_mode: combined ? "combined" : "separate",
        example: exampleId,
        results_count: data.results?.length || 0,
      });
      toast.success("Data extracted");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
      setPhase(null);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Database}
        title="Extractor"
        description="Automatically find and list important details from any document"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Extractor"
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
                      {example.shape}
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

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The documents</CardTitle>
              <CardDescription>
                Upload one or several files and choose how they are read, or
                paste the text of one document.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs
                value={inputMode}
                onValueChange={(v) => setInputMode(v as "text" | "file")}
              >
                <TabsList className="mb-4 grid w-full grid-cols-2">
                  <TabsTrigger value="text">Paste text</TabsTrigger>
                  <TabsTrigger value="file">Upload file</TabsTrigger>
                </TabsList>
                <TabsContent value="text">
                  <Textarea
                    value={documentText}
                    onChange={(e) => {
                      setDocumentText(e.target.value);
                      setExampleId(null);
                    }}
                    placeholder="Paste your document text here..."
                    disabled={busy}
                    rows={10}
                  />
                </TabsContent>
                <TabsContent value="file" className="space-y-4">
                  <DocumentUpload
                    files={files}
                    onChange={(next) => {
                      setFiles(next);
                      setExampleId(null);
                    }}
                    disabled={busy}
                  />

                  {files.length > 1 && (
                    <div className="space-y-2">
                      <Label>Several files</Label>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {(
                          [
                            [
                              "separate",
                              "Process each file individually",
                              "One result for each file, shown in a table. For many documents of the same type, such as invoices.",
                            ],
                            [
                              "combined",
                              "Combine the files",
                              "One result from all files read together, each marked with its name. For documents that refer to each other, such as an order and its parts lists.",
                            ],
                          ] as const
                        ).map(([value, title, text]) => (
                          <button
                            key={value}
                            type="button"
                            disabled={busy}
                            aria-pressed={readMode === value}
                            onClick={() => setReadMode(value)}
                            className={cn(
                              "rounded-lg border p-3 text-left text-sm transition-colors",
                              readMode === value
                                ? "border-primary bg-primary/5"
                                : "hover:bg-muted/40",
                            )}
                          >
                            <span className="font-medium">{title}</span>
                            <span className="text-muted-foreground mt-1 block text-xs">
                              {text}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label htmlFor="extractor-parser">Parser</Label>
                    <Select
                      value={parserType}
                      onValueChange={(value) =>
                        setParserType(value as ParserType)
                      }
                      disabled={busy}
                    >
                      <SelectTrigger id="extractor-parser">
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
                    <p className="text-muted-foreground text-xs">
                      {parser.hint}
                    </p>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. What to extract</CardTitle>
              <CardDescription>
                Describe the data in words, or list the fields yourself.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs
                value={mode}
                onValueChange={(v) => setMode(v as "plain-language" | "fields")}
              >
                <TabsList className="mb-4 grid w-full grid-cols-2">
                  <TabsTrigger value="plain-language">
                    Plain language
                  </TabsTrigger>
                  <TabsTrigger value="fields">Fields</TabsTrigger>
                </TabsList>

                <TabsContent value="plain-language" className="space-y-3">
                  <Label htmlFor="plain-requirements">
                    Extraction requirements
                  </Label>
                  <Textarea
                    id="plain-requirements"
                    value={task}
                    onChange={(e) => {
                      setTask(e.target.value);
                      setExampleId(null);
                    }}
                    placeholder="Describe in natural language what data to extract and the structure..."
                    disabled={busy}
                    rows={8}
                  />
                  <Button
                    onClick={() => void handleGenerateSchema()}
                    disabled={busy || !task.trim()}
                    variant="secondary"
                    className="w-full"
                  >
                    {isGeneratingSchema ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generating schema…
                      </>
                    ) : (
                      <>
                        <ListChecks className="mr-2 h-4 w-4" />
                        {schema
                          ? "Generate the schema again"
                          : "Generate schema"}
                      </>
                    )}
                  </Button>
                  {taskChanged ? (
                    <TaskChangeNotice />
                  ) : (
                    <p className="text-muted-foreground text-xs">
                      {schema?.schema_source === "saved" ||
                      (!schema && readyMade)
                        ? "This task has a ready-made schema, so only the extraction runs. Change the text and a new schema is generated."
                        : schemaCurrent
                          ? "The schema for this task is ready, so only the extraction runs. Change the text and a new schema is generated."
                          : "The schema is generated once for a task, when you extract (or earlier, with the button), and used again while the text stays the same. It is not saved."}
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="fields" className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="requirements">Requirements</Label>
                    <Textarea
                      id="requirements"
                      value={userRequirements}
                      onChange={(e) => setUserRequirements(e.target.value)}
                      placeholder="Describe what data to extract..."
                      disabled={busy}
                      rows={2}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Fields to extract</Label>
                    <div className="max-h-48 space-y-2 overflow-auto">
                      {fields.map((field) => (
                        <div
                          key={field.name}
                          className="flex items-center gap-2 rounded-md border p-2 text-sm"
                        >
                          <div className="min-w-0 flex-1">
                            <span className="font-mono font-medium">
                              {field.name}
                            </span>
                            <span className="text-muted-foreground ml-2">
                              - {field.description}
                            </span>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0"
                            aria-label={`Remove ${field.name}`}
                            onClick={() =>
                              setFields(
                                fields.filter((f) => f.name !== field.name),
                              )
                            }
                            disabled={busy}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                      <Input
                        value={newFieldName}
                        onChange={(e) => setNewFieldName(e.target.value)}
                        placeholder="Field name"
                        disabled={busy}
                        className="w-full sm:flex-1"
                      />
                      <Input
                        value={newFieldDesc}
                        onChange={(e) => setNewFieldDesc(e.target.value)}
                        placeholder="Description"
                        disabled={busy}
                        className="w-full sm:flex-1"
                      />
                      <Button
                        variant="secondary"
                        size="icon"
                        aria-label="Add field"
                        onClick={handleAddField}
                        disabled={
                          busy || !newFieldName.trim() || !newFieldDesc.trim()
                        }
                        className="self-end sm:self-auto"
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </TabsContent>
              </Tabs>

              <TraceSourcesSwitch
                checked={includeSources}
                onCheckedChange={setIncludeSources}
                disabled={busy}
              />

              <Button
                onClick={() => void handleSubmit()}
                disabled={
                  busy ||
                  !hasInput ||
                  (mode === "fields" && fields.length === 0) ||
                  (mode === "plain-language" && !task.trim())
                }
                className="w-full"
                size="lg"
              >
                {isLoading || isParsing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {isParsing
                  ? readingMessage
                  : isLoading
                    ? phase === "schema"
                      ? "Generating schema…"
                      : "Extracting…"
                    : "Extract data"}
              </Button>
              <p className="text-muted-foreground text-center text-xs">
                Model:{" "}
                {ownModel
                  ? `your own (${ownModel.model})`
                  : (serverModel?.label ?? "the server's model")}
              </p>
            </CardContent>
          </Card>
        </div>

        {mode === "plain-language" &&
          schema &&
          !isLoading &&
          (!result || schema.schema_id !== resultSchema?.schema_id) && (
            <Card>
              <CardContent className="space-y-3 pt-6">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">
                    The extraction schema
                  </CardTitle>
                  {schema.schema_source === "saved" && (
                    <Badge variant="outline" className="font-normal">
                      ready-made schema
                    </Badge>
                  )}
                  {!schemaCurrent && (
                    <Badge
                      variant="outline"
                      className="border-amber-500 text-amber-700"
                    >
                      The task changed: a new schema will be generated
                    </Badge>
                  )}
                </div>
                <SchemaTabsView
                  tabs={schemaTabs(
                    schema,
                    STRUCTURE_TEXT[schema.structure_type],
                  )}
                />
              </CardContent>
            </Card>
          )}

        <div className="space-y-6" aria-live="polite">
          {(isLoading || isParsing) && (
            <LoadingCard
              message={
                isParsing
                  ? readingMessage
                  : phase === "schema"
                    ? "Designing the extraction schema…"
                    : "Extracting data…"
              }
              subMessage={
                isParsing
                  ? `With the ${parser.label.split(" (")[0]} parser`
                  : "This may take a few seconds"
              }
            />
          )}

          {result && !isLoading && !isParsing && (
            <ResultView
              results={result.results}
              documentCount={combinedCount ?? result.document_count}
              seconds={seconds}
              labels={resultNames.length > 1 ? resultNames : undefined}
              defaultTab={
                result.results.length > 1
                  ? "table"
                  : result.sources
                    ? "sources"
                    : "readable"
              }
              extraTabs={[
                ...(result.document_sources || result.sources
                  ? [
                      {
                        value: "sources",
                        label: "Sources",
                        content: (
                          <DocumentSources
                            names={resultNames}
                            sources={
                              result.document_sources ?? [
                                result.sources ?? null,
                              ]
                            }
                          />
                        ),
                      },
                    ]
                  : []),
                ...(resultSchema
                  ? schemaTabs(
                      resultSchema,
                      STRUCTURE_TEXT[resultSchema.structure_type],
                    )
                  : []),
              ]}
            />
          )}

          {!result && !isLoading && !isParsing && (
            <EmptyStateCard
              icon={FileText}
              title="No extraction yet"
              description="Add a document and press Extract data. Every field of the result is shown here, also those with no value."
              feedbackSlot={<FeedbackButton demoType="extractor" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
