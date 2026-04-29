"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import {
  Database,
  FileCode2,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { formatFieldName } from "@/lib/utils";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { PageTransition } from "@/components/demo/page-transition";

interface Field {
  name: string;
  description: string;
}

interface ExtractResult {
  results: Record<string, unknown>[];
  document_count: number;
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
}

const CURRENCY_FIELD_HINTS = [
  "amount",
  "total",
  "subtotal",
  "discount",
  "tax",
  "price",
  "cost",
  "fee",
  "balance",
  "revenue",
  "income",
];

function formatExtractorValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";

  const normalizedKey = key.toLowerCase();
  const isCurrencyField = CURRENCY_FIELD_HINTS.some((hint) =>
    normalizedKey.includes(hint),
  );
  if (isCurrencyField && typeof value === "number") {
    return `EUR ${value.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  if (isCurrencyField && typeof value === "string") {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return `EUR ${numeric.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
    }
  }

  return String(value);
}

const DEFAULT_FIELDS: Field[] = [
  { name: "company_name", description: "Name of the company or organization" },
  { name: "total_amount", description: "Total amount or price" },
  { name: "date", description: "Date of the document" },
];

export default function ExtractorPage() {
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [extractionMode, setExtractionMode] = useState<
    "fields" | "plain-language"
  >("plain-language");
  const [documentText, setDocumentText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [userRequirements, setUserRequirements] = useState(
    "Extract key information from this document",
  );
  const [plainLanguageRequirements, setPlainLanguageRequirements] = useState(
    "Extract invoice number, sender name, receiver name, purchase order number, date of invoice, subtotal, discount, tax, and grand total from the invoice.",
  );

  // Clear generated schema when requirements change
  function handleRequirementsChange(value: string): void {
    setPlainLanguageRequirements(value);
    setGeneratedSchema(null);
  }
  const [fields, setFields] = useState<Field[]>(DEFAULT_FIELDS);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDesc, setNewFieldDesc] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);
  const [generatedSchema, setGeneratedSchema] =
    useState<GeneratedSchema | null>(null);
  const [result, setResult] = useState<ExtractResult | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  function handleUseExample(exampleFile: File): void {
    setFile(exampleFile);
    setInputMode("file");
    setResult(null);
  }

  const hasInput =
    inputMode === "text" ? documentText.trim().length > 0 : Boolean(file);

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

  function handleRemoveField(name: string): void {
    setFields(fields.filter((f) => f.name !== name));
  }

  async function generateSchemaForRequirements(): Promise<GeneratedSchema> {
    const response = await apiFetch("/api/extract/generate-schema", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_requirements: plainLanguageRequirements,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail ?? "Failed to generate schema");
    }

    const data = (await response.json()) as GeneratedSchema;
    setGeneratedSchema(data);

    posthog.capture("schema_generated", {
      structure_type: data.structure_type,
      fields_count: data.fields?.length || 0,
    });

    return data;
  }

  async function handleGenerateSchema(): Promise<void> {
    if (!plainLanguageRequirements.trim()) {
      toast.error("Please provide extraction requirements");
      return;
    }

    setIsGeneratingSchema(true);
    setGeneratedSchema(null);

    try {
      await generateSchemaForRequirements();
      toast.success("Schema generated successfully!");
    } catch (error) {
      if (error instanceof RateLimitError) return;
      toast.error(
        error instanceof Error ? error.message : "Failed to generate schema",
      );
    } finally {
      setIsGeneratingSchema(false);
    }
  }

  async function parseFile(): Promise<string | null> {
    if (!file) return null;

    setIsParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", "auto");

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
      return data.text_content || "";
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return null;
      }
      if (error instanceof RateLimitError) {
        return null; // Toast already shown by apiFetch
      }
      toast.error(
        error instanceof Error ? error.message : "Failed to parse file",
      );
      return null;
    } finally {
      setIsParsing(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading || isParsing) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    let textToProcess = documentText;

    if (inputMode === "file") {
      if (!file) {
        toast.error("Please select a file first");
        return;
      }
      const parsedText = await parseFile();
      if (!parsedText) return;
      textToProcess = parsedText;
    }

    if (!textToProcess.trim()) {
      toast.error("Please provide document text");
      return;
    }

    // Validate requirements based on extraction mode
    if (extractionMode === "fields") {
      if (!userRequirements.trim()) {
        toast.error("Please provide extraction requirements");
        return;
      }

      if (fields.length === 0) {
        toast.error("Please add at least one field to extract");
        return;
      }
    } else {
      // Plain language mode
      if (!plainLanguageRequirements.trim()) {
        toast.error("Please provide extraction requirements");
        return;
      }
    }

    setIsLoading(true);
    setResult(null);

    try {
      let response: Response;

      if (extractionMode === "fields") {
        // Fields mode - use original endpoint
        const fieldsMap = Object.fromEntries(
          fields.map((field) => [field.name, field.description]),
        );

        response = await apiFetch("/api/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: [textToProcess],
            user_requirements: userRequirements,
            fields: fieldsMap,
          }),
          signal: abortControllerRef.current.signal,
        });
      } else {
        // Plain language mode - use persisted baseline schema unless the user
        // explicitly generated a temporary schema for testing.
        response = await apiFetch("/api/extract/plain-language", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            documents: [textToProcess],
            user_requirements: plainLanguageRequirements,
            schema_id: generatedSchema?.schema_id || null,
          }),
          signal: abortControllerRef.current.signal,
        });
      }

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to extract data");
      }

      const data = await response.json();
      setResult(data);

      posthog.capture("data_extracted", {
        input_mode: inputMode,
        extraction_mode: extractionMode,
        file_type: file?.type || "text",
        file_size: file?.size || textToProcess.length,
        fields_count:
          extractionMode === "fields"
            ? fields.length
            : generatedSchema?.fields.length || 0,
        results_count: data.results?.length || 0,
      });

      toast.success("Data extracted successfully!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return; // Toast already shown
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Database}
        title="Extractor"
        description="Automatically find and list important details from any document"
        className="mb-8"
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Document Input</CardTitle>
                  <CardDescription>
                    Provide the document text to extract data from
                  </CardDescription>
                </div>
                <ExamplePreviewDialog
                  exampleUrl="/invoice.pdf"
                  exampleName="invoice.pdf"
                  onUseExample={handleUseExample}
                  disabled={isLoading || isParsing}
                />
              </div>
            </CardHeader>
            <CardContent>
              <Tabs
                value={inputMode}
                onValueChange={(v) => setInputMode(v as "text" | "file")}
              >
                <TabsList className="mb-4 grid w-full grid-cols-2">
                  <TabsTrigger value="text">Paste Text</TabsTrigger>
                  <TabsTrigger value="file">Upload File</TabsTrigger>
                </TabsList>
                <TabsContent value="text">
                  <Textarea
                    value={documentText}
                    onChange={(e) => setDocumentText(e.target.value)}
                    placeholder="Paste your document text here..."
                    disabled={isLoading}
                    rows={8}
                  />
                </TabsContent>
                <TabsContent value="file">
                  <FileUpload
                    accept=".pdf,.docx"
                    maxSize={20}
                    file={file}
                    onFileSelect={setFile}
                    onFileRemove={() => setFile(null)}
                    disabled={isLoading}
                  />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="settings" className="border-none">
                <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-sm font-medium">
                  Extraction Settings
                </AccordionTrigger>
                <AccordionContent className="pt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>Configuration</CardTitle>
                      <CardDescription>
                        Define what data to extract
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Extraction Mode Selector */}
                      <div className="space-y-2">
                        <Label>Extraction Mode</Label>
                        <Tabs
                          value={extractionMode}
                          onValueChange={(v) =>
                            setExtractionMode(v as "fields" | "plain-language")
                          }
                        >
                          <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="fields">Fields</TabsTrigger>
                            <TabsTrigger value="plain-language">
                              Plain Language
                            </TabsTrigger>
                          </TabsList>
                        </Tabs>
                        <p className="text-muted-foreground text-xs">
                          {extractionMode === "fields"
                            ? "Define specific fields to extract from documents"
                            : "Describe extraction requirements in natural language"}
                        </p>
                        {extractionMode === "plain-language" ? (
                          <p className="text-muted-foreground text-xs leading-relaxed">
                            If you modify the extraction task, click "Generate
                            Schema" and then "Extract Data" with the new schema.
                            Your generated schema will not be persisted.
                          </p>
                        ) : null}
                      </div>

                      {/* Fields Mode */}
                      {extractionMode === "fields" && (
                        <>
                          <div className="space-y-2">
                            <Label htmlFor="requirements">Requirements</Label>
                            <Textarea
                              id="requirements"
                              value={userRequirements}
                              onChange={(e) =>
                                setUserRequirements(e.target.value)
                              }
                              placeholder="Describe what data to extract..."
                              disabled={isLoading}
                              rows={2}
                            />
                          </div>

                          <div className="space-y-2">
                            <Label>Fields to Extract</Label>
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
                                    onClick={() =>
                                      handleRemoveField(field.name)
                                    }
                                    disabled={isLoading}
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                </div>
                              ))}
                            </div>

                            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                              <Input
                                value={newFieldName}
                                onChange={(e) =>
                                  setNewFieldName(e.target.value)
                                }
                                placeholder="Field name"
                                disabled={isLoading}
                                className="w-full sm:flex-1"
                              />
                              <Input
                                value={newFieldDesc}
                                onChange={(e) =>
                                  setNewFieldDesc(e.target.value)
                                }
                                placeholder="Description"
                                disabled={isLoading}
                                className="w-full sm:flex-1"
                              />
                              <Button
                                variant="secondary"
                                size="icon"
                                onClick={handleAddField}
                                disabled={
                                  isLoading ||
                                  !newFieldName.trim() ||
                                  !newFieldDesc.trim()
                                }
                                className="self-end sm:self-auto"
                              >
                                <Plus className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        </>
                      )}

                      {/* Plain Language Mode */}
                      {extractionMode === "plain-language" && (
                        <>
                          <div className="space-y-2">
                            <Label htmlFor="plain-requirements">
                              Extraction Requirements
                            </Label>
                            <Textarea
                              id="plain-requirements"
                              value={plainLanguageRequirements}
                              onChange={(e) =>
                                handleRequirementsChange(e.target.value)
                              }
                              placeholder="Describe in natural language what data to extract and the structure..."
                              disabled={isLoading || isGeneratingSchema}
                              rows={8}
                            />
                          </div>

                          <Button
                            onClick={handleGenerateSchema}
                            disabled={
                              isLoading ||
                              isGeneratingSchema ||
                              !plainLanguageRequirements.trim()
                            }
                            variant="secondary"
                            className="w-full"
                          >
                            {isGeneratingSchema ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Generating Schema...
                              </>
                            ) : (
                              <>
                                <FileCode2 className="mr-2 h-4 w-4" />
                                Generate Schema
                              </>
                            )}
                          </Button>

                          {/* Display Generated Schema */}
                          {generatedSchema && (
                            <div className="space-y-2">
                              <div className="flex items-center justify-between">
                                <Label>Generated Schema</Label>
                                <span className="text-muted-foreground text-xs">
                                  This schema will be reused for extraction
                                </span>
                              </div>
                              <div className="bg-muted/50 rounded-md border p-4">
                                <div className="mb-2 flex items-center justify-between">
                                  <span className="text-sm font-medium">
                                    {generatedSchema.schema_name}
                                  </span>
                                  <span className="text-muted-foreground text-xs">
                                    {generatedSchema.structure_type}
                                  </span>
                                </div>
                                <pre className="bg-background max-h-64 overflow-auto rounded p-3 text-xs">
                                  <code>{generatedSchema.schema_code}</code>
                                </pre>
                                <div className="mt-3 space-y-1">
                                  <p className="text-xs font-medium">Fields:</p>
                                  <div className="space-y-1">
                                    {generatedSchema.fields.map(
                                      (field, idx) => (
                                        <div
                                          key={idx}
                                          className="text-muted-foreground text-xs"
                                        >
                                          <span className="font-mono">
                                            {field.name}
                                          </span>
                                          <span className="mx-1">:</span>
                                          <span>{field.type}</span>
                                          {field.required && (
                                            <span className="ml-1 text-orange-500">
                                              *
                                            </span>
                                          )}
                                        </div>
                                      ),
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </>
                      )}
                    </CardContent>
                  </Card>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>

          <Button
            onClick={handleSubmit}
            disabled={
              isLoading ||
              isParsing ||
              isGeneratingSchema ||
              (extractionMode === "fields" && fields.length === 0) ||
              (inputMode === "text" && !documentText.trim()) ||
              (inputMode === "file" && !file)
            }
            className="w-full"
            size="lg"
          >
            <Sparkles className="mr-2 h-4 w-4" />
            {isLoading || isParsing
              ? isParsing
                ? "Parsing document..."
                : "Extracting..."
              : "Extract Data"}
          </Button>

          <HowItWorksCard description="Parse a document, define the target fields, and return structured extracted data.">
            <p>
              <strong>1. Provide the input:</strong> Paste document text
              directly or upload a PDF or DOCX file. Uploaded files are parsed
              before extraction.
            </p>
            <p>
              <strong>2. Choose the extraction mode:</strong> Use{" "}
              <em>Fields</em> when you already know the exact fields to extract,
              or <em>Plain Language</em> when you want the system to first
              generate a schema from natural-language requirements.
            </p>
            <p>
              <strong>3. Define the extraction target:</strong> In field mode,
              add field names and descriptions. In plain-language mode, describe
              the output structure and generate the schema before extraction.
            </p>
            <p>
              <strong>4. Run extraction:</strong> The extractor sends the parsed
              text and the configured requirements to the backend and returns
              structured results for each document.
            </p>
            <p>
              <strong>5. Review the output:</strong> The result panel shows the
              extracted fields in a readable layout and also lets you copy the
              raw JSON response.
            </p>
          </HowItWorksCard>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {(isLoading || isParsing) && (
            <LoadingCard
              message={isParsing ? "Parsing document..." : "Extracting data..."}
              subMessage="This may take a few seconds"
            />
          )}

          {result && !isLoading && !isParsing && (
            <ResultCard
              title="Extracted Data"
              description={`Processed ${result.document_count} document(s)`}
              copyContent={JSON.stringify(result.results, null, 2)}
              feedbackSlot={<FeedbackButton demoType="extractor" />}
              delay={0}
            >
              {result.results.length > 0 ? (
                <div className="space-y-4">
                  {result.results.map((item, index) => (
                    <div key={index} className="space-y-2">
                      {result.results.length > 1 && (
                        <p className="text-muted-foreground text-sm font-medium">
                          Document {index + 1}
                        </p>
                      )}
                      <div className="divide-y rounded-md border">
                        {Object.entries(item).map(([key, value]) => (
                          <div key={key} className="flex items-start gap-4 p-3">
                            <span className="min-w-32 text-sm font-medium">
                              {formatFieldName(key)}
                            </span>
                            <span className="text-muted-foreground text-sm">
                              {formatExtractorValue(key, value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted-foreground">No data extracted</p>
              )}
            </ResultCard>
          )}

          {!result && !isLoading && !isParsing && (
            <EmptyStateCard
              icon={Database}
              title="No extraction yet"
              description="Provide document text or upload a file and click Extract."
              feedbackSlot={<FeedbackButton demoType="extractor" />}
            />
          )}
        </div>
      </div>
  </PageTransition>
);
}
