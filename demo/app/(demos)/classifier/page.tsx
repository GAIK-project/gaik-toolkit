"use client";

import { useState } from "react";
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
import { FileUpload } from "@/components/demo/file-upload";
import { ResultCard, ConfidenceBar } from "@/components/demo/result-card";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const handleAddClass = () => {
    const trimmed = classInput.trim().toLowerCase();
    if (trimmed && !classes.includes(trimmed)) {
      setClasses([...classes, trimmed]);
      setClassInput("");
    }
  };

  const handleRemoveClass = (classToRemove: string) => {
    setClasses(classes.filter((c) => c !== classToRemove));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddClass();
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      toast.error("Please select a file first");
      return;
    }
    if (classes.length < 2) {
      toast.error("Please add at least 2 classes");
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("classes", classes.join(","));
      formData.append("parser", parserType);

      const response = await fetch(`${API_URL}/classify/`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to classify document");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Document classified successfully!");
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
          <Tags className="h-8 w-8" />
          Document Classifier
        </h1>
        <p className="mt-2 text-muted-foreground">
          Classify documents into predefined categories using LLM analysis
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <Card>
          <CardHeader>
            <CardTitle>Upload & Configure</CardTitle>
            <CardDescription>
              Select a document and define classification categories
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <FileUpload
              accept=".pdf,.docx,.png,.jpg,.jpeg"
              maxSize={10}
              onFileSelect={setFile}
              onFileRemove={() => {
                setFile(null);
                setResult(null);
              }}
              disabled={isLoading}
            />

            <div className="space-y-2">
              <label className="text-sm font-medium">Classification Classes</label>
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
              <div className="flex flex-wrap gap-2 mt-2">
                {classes.map((cls) => (
                  <Badge
                    key={cls}
                    variant="secondary"
                    className="cursor-pointer hover:bg-destructive hover:text-destructive-foreground transition-colors"
                    onClick={() => !isLoading && handleRemoveClass(cls)}
                  >
                    {cls} ×
                  </Badge>
                ))}
              </div>
            </div>

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
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                  <p className="mt-2 text-muted-foreground">
                    Analyzing document...
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    This may take a few seconds
                  </p>
                </div>
              </CardContent>
            </Card>
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
                    <span className="text-sm text-muted-foreground">Category:</span>
                    <Badge variant="default" className="text-base px-3 py-1">
                      {result.classification}
                    </Badge>
                  </div>
                  <ConfidenceBar
                    value={result.confidence}
                    label="Confidence"
                  />
                </div>
              </ResultCard>

              {result.reasoning && (
                <ResultCard
                  title="Reasoning"
                  description="Why this classification was chosen"
                  copyContent={result.reasoning}
                  delay={0.1}
                >
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {result.reasoning}
                  </p>
                </ResultCard>
              )}
            </>
          )}

          {!result && !isLoading && (
            <Card className="border-dashed">
              <CardContent className="flex items-center justify-center py-12">
                <p className="text-muted-foreground text-center">
                  Upload a document and click classify to see results
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </motion.div>
  );
}
