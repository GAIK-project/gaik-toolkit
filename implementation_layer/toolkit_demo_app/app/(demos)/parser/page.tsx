"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import { FileUpload } from "@/components/demo/file-upload";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
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
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ArrowLeft, ChevronDown, Download, FileText } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface ParseResult {
  filename: string;
  parser: string;
  text_content: string;
  metadata: Record<string, unknown>;
}

// Helper function to format parser names
function formatParserName(parser: string): string {
  const parserNames: Record<string, string> = {
    auto: "Auto-detect",
    pymupdf: "PyMuPDF",
    docx: "DOCX",
    vision: "Vision",
    vision_plus: "Vision+",
    docling_api: "HH Parser",
  };
  return parserNames[parser] || parser;
}

export default function ParserPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [parserType, setParserType] = useState<"auto" | "pymupdf" | "docx" | "vision" | "vision_plus" | "docling_api">("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const [result, setResult] = useState<ParseResult | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  function handleUseExample(exampleFile: File): void {
    setFile(exampleFile);
    setResult(null);
  }

  function handleDownloadMarkdown(): void {
    if (!result) return;
    const blob = new Blob([result.text_content || ""], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${result.filename.replace(/\.[^.]+$/, "") || "parsed-document"}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading) return;

    if (!file) {
      toast.error("Please select a file first");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);

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
      setResult(data);

      posthog.capture("document_parsed", {
        file_type: file.type,
        file_size: file.size,
        parser_used: data.parser,
      });

      toast.success("Document parsed successfully!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }
      if (error instanceof RateLimitError) {
        return; // Toast already shown by apiFetch
      }
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <Button
          variant="ghost"
          className="mb-4 -ml-3 gap-2"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <FileText className="h-8 w-8" />
          Parser
        </h1>
        <p className="text-muted-foreground mt-2">
          Read text and layout from PDF, Word files, and images accurately
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Upload Document</CardTitle>
                  <CardDescription>
                    Select a PDF, DOCX, or image file to read
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
            <CardContent className="space-y-6">
              <FileUpload
                accept=".pdf,.docx,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp"
                maxSize={10}
                file={file}
                onFileSelect={setFile}
                onFileRemove={() => {
                  setFile(null);
                  setResult(null);
                }}
                disabled={isLoading}
              />

              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="settings" className="border-none">
                  <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-sm font-medium">
                    Document Settings
                  </AccordionTrigger>
                  <AccordionContent className="pt-4">
                    <div className="space-y-2">
                      <Label>Parser Type</Label>
                      <Select
                        value={parserType}
                        onValueChange={(value: typeof parserType) => setParserType(value)}
                        disabled={isLoading}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Auto-detect</SelectItem>
                          <SelectItem value="pymupdf">PyMuPDF (Fast, text-based)</SelectItem>
                          <SelectItem value="docx">DOCX (Word documents)</SelectItem>
                          <SelectItem value="vision">Vision (AI-powered, handles images)</SelectItem>
                          <SelectItem value="vision_plus">Vision+ (Text+Image Parsing)</SelectItem>
                          <SelectItem value="docling_api">HH Parser (HH's fast Docling Parser)</SelectItem>
                        </SelectContent>
                      </Select>
                      {(parserType === "vision" || parserType === "vision_plus") && (
                        <p className="text-muted-foreground text-xs">
                          Vision and Vision+ parsers are limited to a maximum of 20 pages per document.
                        </p>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <Button
                onClick={handleSubmit}
                disabled={!file || isLoading}
                className="w-full"
                size="lg"
              >
                {isLoading ? "Parsing..." : "Read Document"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <button
              type="button"
              className="flex w-full items-center justify-between px-6 py-5 text-left"
              onClick={() => setHowItWorksOpen((current) => !current)}
            >
              <div>
                <CardTitle>How It Works</CardTitle>
                <CardDescription className="mt-1">
                  Parse document text with a selected parser and export the result as markdown.
                </CardDescription>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
                {howItWorksOpen ? "Hide" : "Show"}
                <ChevronDown className={`h-4 w-4 transition-transform ${howItWorksOpen ? "rotate-180" : ""}`} />
              </div>
            </button>
            {howItWorksOpen ? (
              <CardContent className="text-muted-foreground space-y-3 text-sm leading-6">
                <p>
                  <strong>1. Upload a document:</strong> Select a PDF, DOCX, or image file. The parser demo supports both text-first and vision-based parsing strategies.
                </p>
                <p>
                  <strong>2. Choose the parser type:</strong> Use auto-detect for convenience, or pick a specific parser when you want a text-based, OCR, or combined text+image parsing workflow.
                </p>
                <p>
                  <strong>3. Choose the parser for the document type:</strong> Use PyMuPDF for text-based PDFs, DOCX for Word files, Vision for scanned PDFs or image-heavy documents, Vision+ when both text and images matter in the same document, and Haaga-Helia's parser when you want a remote high-quality parsing option.
                </p>
                <p>
                  <strong>4. Review the output:</strong> The result panel shows the parsed text, lets you copy it, and also lets you download the parsed content as a markdown file.
                </p>
              </CardContent>
            ) : null}
          </Card>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && <LoadingCard message="Parsing document..." />}

          {result && !isLoading && (
            <>
              <div className="mb-4 flex justify-end">
                <Button variant="outline" onClick={handleDownloadMarkdown} className="gap-2">
                  <Download className="h-4 w-4" />
                  Download Markdown
                </Button>
              </div>
              <ResultCard
                title="Document Content"
                description={`Parsed using ${formatParserName(result.parser)} parser • ${result.filename}`}
                copyContent={result.text_content}
                feedbackSlot={<FeedbackButton demoType="parser" />}
                delay={0}
              >
                <ResultText
                  content={result.text_content || "No text content extracted"}
                  maxHeight="400px"
                />
              </ResultCard>
            </>
          )}

          {!result && !isLoading && (
            <EmptyStateCard message="Upload a document to see parsed results here" />
          )}
        </div>
      </div>
    </motion.div>
  );
}
