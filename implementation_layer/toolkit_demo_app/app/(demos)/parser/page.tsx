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
import { FileText } from "lucide-react";
import { motion } from "motion/react";
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
  };
  return parserNames[parser] || parser;
}

export default function ParserPage() {
  const [file, setFile] = useState<File | null>(null);
  const [parserType, setParserType] = useState<"auto" | "pymupdf" | "docx" | "vision" | "vision_plus">("auto");
  const [isLoading, setIsLoading] = useState(false);
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
                          <SelectItem value="vision_plus">Vision+ (Enhanced RAG parsing)</SelectItem>
                        </SelectContent>
                      </Select>
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
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && <LoadingCard message="Parsing document..." />}

          {result && !isLoading && (
            <>
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
