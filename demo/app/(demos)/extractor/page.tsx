"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Database, Loader2, Plus, Trash2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileUpload } from "@/components/demo/file-upload";
import { ResultCard, ResultJson } from "@/components/demo/result-card";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Field {
  name: string;
  description: string;
}

interface ExtractResult {
  results: Record<string, unknown>[];
  document_count: number;
}

const DEFAULT_FIELDS: Field[] = [
  { name: "company_name", description: "Name of the company or organization" },
  { name: "total_amount", description: "Total amount or price" },
  { name: "date", description: "Date of the document" },
];

export default function ExtractorPage() {
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [documentText, setDocumentText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [userRequirements, setUserRequirements] = useState(
    "Extract key information from this document"
  );
  const [fields, setFields] = useState<Field[]>(DEFAULT_FIELDS);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDesc, setNewFieldDesc] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [result, setResult] = useState<ExtractResult | null>(null);

  const handleAddField = () => {
    if (newFieldName.trim() && newFieldDesc.trim()) {
      const fieldKey = newFieldName.trim().toLowerCase().replace(/\s+/g, "_");
      if (fields.some((f) => f.name === fieldKey)) {
        toast.error("Field already exists");
        return;
      }
      setFields([...fields, { name: fieldKey, description: newFieldDesc.trim() }]);
      setNewFieldName("");
      setNewFieldDesc("");
    }
  };

  const handleRemoveField = (name: string) => {
    setFields(fields.filter((f) => f.name !== name));
  };

  const parseFile = async (): Promise<string | null> => {
    if (!file) return null;

    setIsParsing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("parser_type", "auto");

      const response = await fetch(`${API_URL}/parse/`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to parse document");
      }

      const data = await response.json();
      return data.text_content || "";
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to parse file"
      );
      return null;
    } finally {
      setIsParsing(false);
    }
  };

  const handleSubmit = async () => {
    let textToProcess = documentText;

    // If in file mode, parse the file first
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

    if (!userRequirements.trim()) {
      toast.error("Please provide extraction requirements");
      return;
    }

    if (fields.length === 0) {
      toast.error("Please add at least one field to extract");
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const fieldsMap = fields.reduce(
        (acc, field) => {
          acc[field.name] = field.description;
          return acc;
        },
        {} as Record<string, string>
      );

      const response = await fetch(`${API_URL}/extract/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          documents: [textToProcess],
          user_requirements: userRequirements,
          fields: fieldsMap,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to extract data");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Data extracted successfully!");
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
          <Database className="h-8 w-8" />
          Data Extractor
        </h1>
        <p className="mt-2 text-muted-foreground">
          Extract structured data from documents using natural language
          requirements
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Document Input</CardTitle>
              <CardDescription>
                Provide the document text to extract data from
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs
                value={inputMode}
                onValueChange={(v) => setInputMode(v as "text" | "file")}
              >
                <TabsList className="grid w-full grid-cols-2 mb-4">
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
                    maxSize={10}
                    onFileSelect={setFile}
                    onFileRemove={() => setFile(null)}
                    disabled={isLoading}
                  />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Extraction Settings</CardTitle>
              <CardDescription>
                Define what data to extract
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="requirements">Requirements</Label>
                <Textarea
                  id="requirements"
                  value={userRequirements}
                  onChange={(e) => setUserRequirements(e.target.value)}
                  placeholder="Describe what data to extract..."
                  disabled={isLoading}
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <Label>Fields to Extract</Label>
                <div className="space-y-2 max-h-48 overflow-auto">
                  {fields.map((field) => (
                    <div
                      key={field.name}
                      className="flex items-center gap-2 rounded-md border p-2 text-sm"
                    >
                      <div className="flex-1 min-w-0">
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
                        onClick={() => handleRemoveField(field.name)}
                        disabled={isLoading}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>

                <div className="flex gap-2 mt-2">
                  <Input
                    value={newFieldName}
                    onChange={(e) => setNewFieldName(e.target.value)}
                    placeholder="Field name"
                    disabled={isLoading}
                    className="flex-1"
                  />
                  <Input
                    value={newFieldDesc}
                    onChange={(e) => setNewFieldDesc(e.target.value)}
                    placeholder="Description"
                    disabled={isLoading}
                    className="flex-1"
                  />
                  <Button
                    variant="secondary"
                    size="icon"
                    onClick={handleAddField}
                    disabled={
                      isLoading || !newFieldName.trim() || !newFieldDesc.trim()
                    }
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <Button
                onClick={handleSubmit}
                disabled={
                  isLoading ||
                  isParsing ||
                  fields.length === 0 ||
                  (inputMode === "text" && !documentText.trim()) ||
                  (inputMode === "file" && !file)
                }
                className="w-full"
                size="lg"
              >
                {isLoading || isParsing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {isParsing ? "Parsing document..." : "Extracting..."}
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Extract Data
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {(isLoading || isParsing) && (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                  <p className="mt-2 text-muted-foreground">
                    {isParsing
                      ? "Parsing document..."
                      : "Extracting data..."}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    This may take a few seconds
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {result && !isLoading && !isParsing && (
            <ResultCard
              title="Extracted Data"
              description={`Processed ${result.document_count} document(s)`}
              copyContent={JSON.stringify(result.results, null, 2)}
              delay={0}
            >
              {result.results.length > 0 ? (
                <div className="space-y-4">
                  {result.results.map((item, index) => (
                    <div key={index} className="space-y-2">
                      {result.results.length > 1 && (
                        <p className="text-sm font-medium text-muted-foreground">
                          Document {index + 1}
                        </p>
                      )}
                      <div className="rounded-md border divide-y">
                        {Object.entries(item).map(([key, value]) => (
                          <div
                            key={key}
                            className="flex items-start gap-4 p-3"
                          >
                            <span className="font-mono text-sm font-medium min-w-32">
                              {key}
                            </span>
                            <span className="text-sm text-muted-foreground">
                              {value !== null && value !== undefined
                                ? String(value)
                                : "-"}
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
            <Card className="border-dashed">
              <CardContent className="flex items-center justify-center py-12">
                <p className="text-muted-foreground text-center">
                  Provide document text and click extract to see results
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </motion.div>
  );
}
