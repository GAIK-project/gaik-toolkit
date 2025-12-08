"use client";

import { useState } from "react";
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
import { ResultCard, ResultText, ResultJson } from "@/components/demo/result-card";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const handleSubmit = async () => {
    if (!file) {
      toast.error("Please select a file first");
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", parserType);

      const response = await fetch(`${API_URL}/parse/`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to parse document");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Document parsed successfully!");
    } catch (error) {
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
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FileText className="h-8 w-8" />
          Document Parser
        </h1>
        <p className="mt-2 text-muted-foreground">
          Parse PDFs and Word documents with PyMuPDF or DOCX parsers
        </p>
      </header>

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
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                  <p className="mt-2 text-muted-foreground">
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
