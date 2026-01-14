"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import { FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FileUpload } from "@/components/demo/file-upload";
import { DemoStepper } from "@/components/demo/demo-stepper";
import {
  ResultCard,
  ResultText,
  ResultJson,
} from "@/components/demo/result-card";
import { Step } from "@/components/demo/step-indicator";
import { toast } from "sonner";

interface ParseResult {
  filename: string;
  parser: string;
  text_content: string;
  metadata: Record<string, unknown>;
}

export default function ParserPage() {
  const [file, setFile] = useState<File | null>(null);
  const [parserType, setParserType] = useState<string>("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ParseResult | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const flowSteps: Step[] = [
    {
      id: "upload",
      name: "Upload",
      status: file ? "completed" : "pending",
    },
    {
      id: "parse",
      name: "Parse",
      status: result ? "completed" : "pending",
    },
    {
      id: "review",
      name: "Review",
      status: result ? "completed" : "pending",
    },
  ];

  const handleSubmit = async () => {
    if (isLoading) return; // Prevent double-click

    if (!file) {
      toast.error("Please select a file first");
      return;
    }

    // Abort previous request if any
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", parserType);

      const response = await fetch("/api/parse/", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        let errorMessage = "Failed to parse document";
        try {
          const error = await response.json();
          errorMessage = error.detail || errorMessage;
        } catch {
          // JSON parsing failed, use default message
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setResult(data);
      toast.success("Document parsed successfully!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return; // Request was aborted, don't show error
      }
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <FileText className="h-8 w-8" />
          Document Parser
        </h1>
        <p className="text-muted-foreground mt-2">
          Parse PDFs and Word documents with PyMuPDF or DOCX parsers
        </p>
      </header>

      <DemoStepper steps={flowSteps} className="mb-8" />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <Card>
          <CardHeader>
            <CardTitle>Upload Document</CardTitle>
            <CardDescription>
              Select a PDF or DOCX file to parse
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <FileUpload
              accept=".pdf,.docx"
              maxSize={10}
              onFileSelect={setFile}
              onFileRemove={() => {
                setFile(null);
                setResult(null);
              }}
              disabled={isLoading}
            />

            <div className="space-y-2">
              <label className="text-sm font-medium">Parser Type</label>
              <Select
                value={parserType}
                onValueChange={setParserType}
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect</SelectItem>
                  <SelectItem value="pymupdf">PyMuPDF (PDF)</SelectItem>
                  <SelectItem value="docx">DOCX Parser</SelectItem>
                  <SelectItem value="vision" disabled>
                    Vision (requires API key)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!file || isLoading}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Parsing...
                </>
              ) : (
                "Parse Document"
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="text-primary mx-auto h-8 w-8 animate-spin" />
                  <p className="text-muted-foreground mt-2">
                    Parsing document...
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <>
              <ResultCard
                title="Parsed Content"
                description={`Parsed with ${result.parser} parser`}
                copyContent={result.text_content}
                delay={0}
              >
                <ResultText
                  content={result.text_content || "No text content extracted"}
                  maxHeight="400px"
                />
              </ResultCard>

              {Object.keys(result.metadata).length > 0 && (
                <ResultCard
                  title="Metadata"
                  description="Document metadata"
                  copyContent={JSON.stringify(result.metadata, null, 2)}
                  delay={0.1}
                >
                  <ResultJson data={result.metadata} maxHeight="200px" />
                </ResultCard>
              )}
            </>
          )}

          {!result && !isLoading && (
            <Card className="border-dashed">
              <CardContent className="flex items-center justify-center py-12">
                <p className="text-muted-foreground text-center">
                  Upload a document to see parsed results here
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </motion.div>
  );
}
