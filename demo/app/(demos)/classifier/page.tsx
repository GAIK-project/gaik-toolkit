"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import { Tags, Loader2, Sparkles } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { FileUpload } from "@/components/demo/file-upload";
import { DemoStepper } from "@/components/demo/demo-stepper";
import {
  ResultCard,
  ConfidenceBar,
  LoadingCard,
  EmptyStateCard,
} from "@/components/demo/result-card";
import { Step } from "@/components/demo/step-indicator";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
import toast from "react-hot-toast";

interface ClassifyResult {
  filename: string;
  classification: string;
  confidence: number;
  reasoning: string;
}

const DEFAULT_CLASSES = ["invoice", "receipt", "contract", "report", "letter"];

export default function ClassifierPage() {
  const [file, setFile] = useState<File | null>(null);
  const [classes, setClasses] = useState<string[]>(DEFAULT_CLASSES);
  const [classInput, setClassInput] = useState("");
  const [parserType, setParserType] = useState<string>("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ClassifyResult | null>(null);
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

  const flowSteps: Step[] = [
    {
      id: "upload",
      name: "Upload",
      status: file ? "completed" : "pending",
    },
    {
      id: "classes",
      name: "Classes",
      status: file && classes.length >= 2 ? "completed" : "pending",
    },
    {
      id: "review",
      name: "Review",
      status: result ? "completed" : "pending",
    },
  ];

  function handleAddClass(): void {
    const trimmed = classInput.trim().toLowerCase();
    if (trimmed && !classes.includes(trimmed)) {
      setClasses([...classes, trimmed]);
      setClassInput("");
    }
  }

  function handleRemoveClass(classToRemove: string): void {
    setClasses(classes.filter((c) => c !== classToRemove));
  }

  function handleKeyDown(e: React.KeyboardEvent): void {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddClass();
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading) return; // Prevent double-click

    if (!file) {
      toast.error("Please select a file first");
      return;
    }
    if (classes.length < 2) {
      toast.error("Please add at least 2 classes");
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
      formData.append("classes", classes.join(","));
      formData.append("parser", parserType);

      const response = await fetch("/api/classify", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to classify document");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Document classified successfully!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return; // Request was aborted, don't show error
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
          <Tags className="h-8 w-8" />
          Document Classifier
        </h1>
        <p className="text-muted-foreground mt-2">
          Classify documents into predefined categories using LLM analysis
        </p>
      </header>

      <DemoStepper steps={flowSteps} className="mb-8" />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Upload & Configure</CardTitle>
                <CardDescription>
                  Select a document and define classification categories
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
              accept=".pdf,.docx,.png,.jpg,.jpeg"
              maxSize={10}
              file={file}
              onFileSelect={setFile}
              onFileRemove={() => {
                setFile(null);
                setResult(null);
              }}
              disabled={isLoading}
            />

            <div className="space-y-2">
              <Label>Classification Classes</Label>
              <div className="flex gap-2">
                <Input
                  value={classInput}
                  onChange={(e) => setClassInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Add a class..."
                  disabled={isLoading}
                />
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleAddClass}
                  disabled={isLoading || !classInput.trim()}
                >
                  Add
                </Button>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {classes.map((cls) => (
                  <Badge
                    key={cls}
                    variant="secondary"
                    className="hover:bg-destructive hover:text-destructive-foreground cursor-pointer transition-colors"
                    onClick={() => !isLoading && handleRemoveClass(cls)}
                  >
                    {cls} ×
                  </Badge>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Parser Type</Label>
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
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!file || classes.length < 2 || isLoading}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Classifying...
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Classify Document
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && (
            <LoadingCard
              message="Analyzing document..."
              subMessage="This may take a few seconds"
            />
          )}

          {result && !isLoading && (
            <>
              <ResultCard
                title="Classification Result"
                description={`File: ${result.filename}`}
                delay={0}
              >
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <span className="text-muted-foreground text-sm">
                      Category:
                    </span>
                    <Badge variant="default" className="px-3 py-1 text-base">
                      {result.classification}
                    </Badge>
                  </div>
                  <ConfidenceBar value={result.confidence} label="Confidence" />
                </div>
              </ResultCard>

              {result.reasoning && (
                <ResultCard
                  title="Reasoning"
                  description="Why this classification was chosen"
                  copyContent={result.reasoning}
                  delay={0.1}
                >
                  <p className="text-muted-foreground text-sm leading-relaxed">
                    {result.reasoning}
                  </p>
                </ResultCard>
              )}
            </>
          )}

          {!result && !isLoading && (
            <EmptyStateCard message="Upload a document and click classify to see results" />
          )}
        </div>
      </div>
    </motion.div>
  );
}
