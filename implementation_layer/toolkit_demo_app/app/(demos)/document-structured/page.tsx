"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
import {
  EmptyStateCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { StepIndicator } from "@/components/demo/step-indicator";
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
import { processSSEStream, type SSEStep } from "@/lib/sse";
import {
  ChevronDown,
  ChevronUp,
  Download,
  FileOutput,
  Loader2,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { formatFieldName } from "@/lib/utils";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const DEFAULT_REQUIREMENTS = `Extract the following from the document:
- Document title or heading
- Important dates
- Names of people or organizations
- Key numerical values or amounts
- Any action items or requirements`;

interface DocumentStructuredResult {
  job_id: string;
  parsed_content: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function DocumentStructuredPage() {
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [userRequirements, setUserRequirements] = useState(DEFAULT_REQUIREMENTS);
  const [parserType, setParserType] = useState<"auto" | "pymupdf" | "docx" | "vision" | "vision_plus">("auto");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [generatePdf, setGeneratePdf] = useState(false);

  const [result, setResult] = useState<DocumentStructuredResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const hasInput = !!documentFile;

  function handleUseExample(exampleFile: File): void {
    setDocumentFile(exampleFile);
    setResult(null);
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);

    try {
      const formData = new FormData();
      formData.append("file", documentFile!);
      formData.append("user_requirements", userRequirements);
      formData.append("parser_type", parserType);
      formData.append("generate_pdf", String(generatePdf));
      formData.append("pdf_title", "Document Structured Data");

      const response = await apiFetch("/api/pipeline/document/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error("Failed to process document");
      }

      let streamError: Error | null = null;

      await processSSEStream<DocumentStructuredResult>(response, {
        onSteps: (steps) => setPipelineSteps(steps),
        onStepUpdate: (update) => {
          setPipelineSteps((prev) =>
            prev.map((s) => (s.step === update.step ? update : s))
          );
        },
        onResult: (data) => {
          setResult(data);
          posthog.capture("document_structured_executed", {
            parser_type: parserType,
            generate_pdf: generatePdf,
          });
          toast.success("Document processed successfully!");
        },
        onError: (message) => {
          streamError = new Error(message);
        },
      });

      if (streamError) throw streamError;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;

      // Mark current step as error
      setPipelineSteps((prev) =>
        prev.map((step) =>
          step.status === "in_progress"
            ? { ...step, status: "error" as const, message: error instanceof Error ? error.message : "Processing failed" }
            : step
        )
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

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `document_structured_${result.job_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success("PDF downloaded!");
    } catch (error) {
      toast.error("Failed to download PDF");
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <FileOutput className="h-8 w-8" />
          Document → Structured Data
        </h1>
        <p className="text-muted-foreground mt-2">
          Parse documents and images to extract structured data automatically
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Document Input</CardTitle>
                  <CardDescription>
                    Upload a document or image to parse and extract data from
                  </CardDescription>
                </div>
                <ExamplePreviewDialog
                  exampleUrl="/GAIK_Test_Document_Demo.pdf"
                  exampleName="GAIK_Test_Document_Demo.pdf"
                  onUseExample={handleUseExample}
                  disabled={isLoading}
                />
              </div>
            </CardHeader>
            <CardContent>
              <FileUpload
                accept=".pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp"
                maxSize={10}
                file={documentFile}
                onFileSelect={setDocumentFile}
                onFileRemove={() => setDocumentFile(null)}
                disabled={isLoading}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Extraction Requirements</CardTitle>
              <CardDescription>
                Describe what data you want to extract from the document
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={userRequirements}
                onChange={(e) => setUserRequirements(e.target.value)}
                placeholder="Describe what data to extract..."
                disabled={isLoading}
                rows={6}
              />
            </CardContent>
          </Card>

          {/* Advanced Settings */}
          <Card>
            <CardHeader className="cursor-pointer py-3 px-4" onClick={() => setShowAdvanced(!showAdvanced)}>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">Advanced Settings</CardTitle>
                {showAdvanced ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </CardHeader>
            <AnimatePresence>
              {showAdvanced && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <CardContent className="space-y-4 px-4 pt-0 pb-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="parser-type" className="text-sm">Parser Type</Label>
                      <Select
                        value={parserType}
                        onValueChange={(value: typeof parserType) => setParserType(value)}
                        disabled={isLoading}
                      >
                        <SelectTrigger id="parser-type">
                          <SelectValue placeholder="Select parser" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Auto-detect</SelectItem>
                          <SelectItem value="pymupdf">PyMuPDF (Fast, text-based)</SelectItem>
                          <SelectItem value="vision">Vision (AI-powered, handles images)</SelectItem>
                          <SelectItem value="vision_plus">Vision+ (Enhanced RAG parsing)</SelectItem>
                          <SelectItem value="docx">DOCX (Word documents)</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-muted-foreground text-xs">
                        Choose how to parse your document
                      </p>
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="generate-pdf" className="text-sm">Generate PDF Report</Label>
                        <p className="text-muted-foreground text-xs">
                          Create a downloadable PDF with extracted data
                        </p>
                      </div>
                      <Switch
                        id="generate-pdf"
                        checked={generatePdf}
                        onCheckedChange={setGeneratePdf}
                        disabled={isLoading}
                      />
                    </div>
                  </CardContent>
                </motion.div>
              )}
            </AnimatePresence>
          </Card>

          <Button
            onClick={handleSubmit}
            disabled={isLoading || !hasInput}
            className="w-full"
            size="lg"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Process Document
              </>
            )}
          </Button>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && pipelineSteps.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Processing</CardTitle>
                <CardDescription>Running document to structured data pipeline</CardDescription>
              </CardHeader>
              <CardContent>
                <StepIndicator steps={pipelineSteps} />
              </CardContent>
            </Card>
          )}

          {isLoading && pipelineSteps.length === 0 && (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="text-primary mx-auto h-8 w-8 animate-spin" />
                  <p className="text-muted-foreground mt-2">Starting document processing...</p>
                </div>
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <>
              {/* Parsed Content */}
              {result.parsed_content && (
                <ResultCard
                  title="Parsed Content"
                  description="Document text extracted from file"
                  copyContent={result.parsed_content}
                  delay={0}
                >
                  <ResultText
                    content={
                      result.parsed_content.length > 500
                        ? result.parsed_content.slice(0, 500) + "..."
                        : result.parsed_content
                    }
                  />
                </ResultCard>
              )}

              {/* Extracted Data */}
              {result.extracted_data && result.extracted_data.length > 0 && (
                <ResultCard
                  title="Extracted Data"
                  description="Structured data from document"
                  copyContent={JSON.stringify(result.extracted_data, null, 2)}
                  feedbackSlot={<FeedbackButton demoType="document-structured" />}
                  delay={0.1}
                >
                  <div className="space-y-4">
                    {result.extracted_data.map((item, index) => (
                      <div key={index} className="space-y-2">
                        {result.extracted_data!.length > 1 && (
                          <p className="text-muted-foreground text-sm font-medium">
                            Item {index + 1}
                          </p>
                        )}
                        <div className="divide-y rounded-md border">
                          {Object.entries(item).map(([key, value]) => (
                            <div key={key} className="grid grid-cols-[180px_1fr] gap-4 p-3">
                              <span className="text-sm font-medium text-amber-700 dark:text-amber-500">
                                {formatFieldName(key)}
                              </span>
                              <div className="text-muted-foreground text-sm">
                                {value === null || value === undefined ? (
                                  "-"
                                ) : Array.isArray(value) ? (
                                  <ul className="list-disc list-inside space-y-1">
                                    {value.map((item, i) => (
                                      <li key={i}>{String(item)}</li>
                                    ))}
                                  </ul>
                                ) : typeof value === "object" ? (
                                  <pre className="whitespace-pre-wrap text-xs bg-muted/50 p-2 rounded">
                                    {JSON.stringify(value, null, 2)}
                                  </pre>
                                ) : (
                                  <span className="wrap-break-word">{String(value)}</span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </ResultCard>
              )}

              {/* PDF Download */}
              {result.pdf_available && (
                <Card>
                  <CardContent className="pt-6">
                    <Button
                      onClick={handleDownloadPdf}
                      variant="outline"
                      className="w-full"
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Download PDF Report
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {!result && !isLoading && (
            <EmptyStateCard message="Upload a document and click process to see results" />
          )}
        </div>
      </div>
    </motion.div>
  );
}
