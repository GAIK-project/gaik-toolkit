"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import {
  AlertTriangle,
  Loader2,
  Sparkles,
  Download,
  Eye,
  Wand2,
  PenLine,
  FileAudio,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { FileUpload } from "@/components/demo/file-upload";
import { DemoStepper } from "@/components/demo/demo-stepper";
import {
  ResultCard,
  ResultText,
  ResultJson,
} from "@/components/demo/result-card";
import { Step } from "@/components/demo/step-indicator";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEFAULT_INCIDENT_SCHEMA = `Extract the following from the incident report:
- Incident date and time
- Location of incident
- Brief description of what happened
- People involved (names, roles if mentioned)
- Injuries or damages reported
- Immediate actions taken
- Witness information (if any)`;

const EXAMPLE_INCIDENT_TEXT = `Incident Report

Date: 12 January 2026
Location: Warehouse Area B

Description:
An employee slipped on a wet floor near the loading dock while carrying empty boxes. No warning sign was in place at the time.

Injury:
Minor bruising to the right arm. No medical treatment required.

Immediate Action Taken:
The area was cleaned and warning signs were placed. The employee was advised to rest and report any further discomfort.

Preventive Measures:
Regular floor inspections and immediate placement of warning signs when surfaces are wet.`;

interface IncidentReportResult {
  job_id: string;
  raw_transcript: string | null;
  enhanced_transcript: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function IncidentReportPage() {
  const [inputMode, setInputMode] = useState<"audio" | "text">("audio");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState("");
  const [extractionMode, setExtractionMode] = useState<"auto" | "custom">(
    "auto",
  );
  const [customSchema, setCustomSchema] = useState(DEFAULT_INCIDENT_SCHEMA);
  const [enhanced, setEnhanced] = useState(true);
  const [generatePdf, setGeneratePdf] = useState(false);
  const [result, setResult] = useState<IncidentReportResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  function getProcessStatus(): Step["status"] {
    if (result) return "completed";
    if (isLoading) return "in_progress";
    return "pending";
  }

  const hasInput = inputMode === "audio" ? !!audioFile : !!textInput.trim();

  const flowSteps: Step[] = [
    {
      id: "input",
      name: inputMode === "audio" ? "Upload" : "Input",
      status: hasInput ? "completed" : "pending",
    },
    {
      id: "process",
      name: "Process",
      status: getProcessStatus(),
    },
    {
      id: "report",
      name: "Report",
      status: result?.extracted_data ? "completed" : "pending",
    },
  ];

  const handleSubmit = async () => {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);

    try {
      const userRequirements =
        extractionMode === "auto"
          ? "Extract all relevant incident details automatically including date, time, location, description, people involved, injuries, damages, and actions taken."
          : customSchema;

      const formData = new FormData();
      formData.append("user_requirements", userRequirements);
      formData.append("generate_pdf", String(generatePdf));

      let endpoint: string;

      if (inputMode === "audio" && audioFile) {
        formData.append("file", audioFile);
        formData.append("enhanced", String(enhanced));
        formData.append("compress_audio", "true");
        endpoint = `${API_URL}/pipeline/audio`;
      } else {
        formData.append("text", textInput);
        endpoint = `${API_URL}/pipeline/text`;
      }

      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const errorMessage = await response
          .json()
          .then((err) => err.detail || "Failed to process input")
          .catch(() => "Failed to process input");
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setResult(data);
      toast.success("Incident report generated!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  function openPdfDownload(jobId: string): void {
    window.open(`${API_URL}/pipeline/pdf/${jobId}`, "_blank");
  }

  function resetDemo(): void {
    setAudioFile(null);
    setTextInput("");
    setResult(null);
  }

  function loadExampleText(): void {
    setInputMode("text");
    setTextInput(EXAMPLE_INCIDENT_TEXT);
    setResult(null);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <AlertTriangle className="h-8 w-8" />
          Incident Reporting Demo
        </h1>
        <p className="text-muted-foreground mt-2">
          Submit an incident via audio or text and automatically generate a
          structured report
        </p>
      </header>

      <DemoStepper steps={flowSteps} className="mb-8" />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>
                  {inputMode === "audio"
                    ? "Upload Incident Recording"
                    : "Enter Incident Text"}
                </CardTitle>
                <CardDescription>
                  {inputMode === "audio"
                    ? "Upload an audio recording of the incident report"
                    : "Enter or paste the incident report text"}
                </CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={loadExampleText}>
                <Eye className="mr-2 h-4 w-4" />
                Example
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              <Label>Input Type</Label>
              <ToggleGroup
                type="single"
                value={inputMode}
                onValueChange={(v) => {
                  if (v) {
                    setInputMode(v as "audio" | "text");
                    resetDemo();
                  }
                }}
                className="justify-start"
              >
                <ToggleGroupItem value="audio" className="gap-2">
                  <FileAudio className="h-4 w-4" />
                  Audio
                </ToggleGroupItem>
                <ToggleGroupItem value="text" className="gap-2">
                  <FileText className="h-4 w-4" />
                  Text
                </ToggleGroupItem>
              </ToggleGroup>
            </div>

            {inputMode === "audio" ? (
              <FileUpload
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                maxSize={50}
                onFileSelect={setAudioFile}
                onFileRemove={resetDemo}
                disabled={isLoading}
              />
            ) : (
              <div className="space-y-2">
                <Textarea
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="Enter incident report text here..."
                  disabled={isLoading}
                  rows={8}
                  className="min-h-[180px] resize-none"
                />
                {textInput && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setTextInput("")}
                    className="text-muted-foreground"
                  >
                    Clear text
                  </Button>
                )}
              </div>
            )}

            <div className="space-y-3">
              <Label>Extraction Mode</Label>
              <ToggleGroup
                type="single"
                value={extractionMode}
                onValueChange={(v) =>
                  v && setExtractionMode(v as "auto" | "custom")
                }
                className="justify-start"
              >
                <ToggleGroupItem value="auto" className="gap-2">
                  <Wand2 className="h-4 w-4" />
                  Automatic
                </ToggleGroupItem>
                <ToggleGroupItem value="custom" className="gap-2">
                  <PenLine className="h-4 w-4" />
                  Custom Schema
                </ToggleGroupItem>
              </ToggleGroup>
              <p className="text-muted-foreground text-xs">
                {extractionMode === "auto"
                  ? "AI will automatically identify and extract relevant incident details"
                  : "Define exactly what fields to extract from the recording"}
              </p>
            </div>

            {extractionMode === "custom" && (
              <div className="space-y-2">
                <Label htmlFor="schema">Custom Extraction Schema</Label>
                <Textarea
                  id="schema"
                  value={customSchema}
                  onChange={(e) => setCustomSchema(e.target.value)}
                  placeholder="Describe what data to extract..."
                  disabled={isLoading}
                  rows={6}
                  className="font-mono text-sm"
                />
              </div>
            )}

            <div className="space-y-4">
              {inputMode === "audio" && (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="enhanced">Enhanced Transcript</Label>
                    <p className="text-muted-foreground text-xs">
                      Improve readability with AI
                    </p>
                  </div>
                  <Switch
                    id="enhanced"
                    checked={enhanced}
                    onCheckedChange={setEnhanced}
                    disabled={isLoading}
                  />
                </div>
              )}

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="pdf">Generate PDF Report</Label>
                  <p className="text-muted-foreground text-xs">
                    Create downloadable PDF
                  </p>
                </div>
                <Switch
                  id="pdf"
                  checked={generatePdf}
                  onCheckedChange={setGeneratePdf}
                  disabled={isLoading}
                />
              </div>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!hasInput || isLoading}
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
                  Generate Report
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {isLoading && (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="text-primary mx-auto h-8 w-8 animate-spin" />
                  <p className="text-muted-foreground mt-2">
                    {inputMode === "audio"
                      ? "Processing incident recording..."
                      : "Extracting incident data..."}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    This may take a moment
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <>
              {(result.raw_transcript || result.enhanced_transcript) && (
                <ResultCard
                  title="Transcript"
                  copyContent={
                    result.enhanced_transcript || result.raw_transcript || ""
                  }
                >
                  {result.enhanced_transcript ? (
                    <Tabs defaultValue="enhanced" className="w-full">
                      <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="enhanced">Enhanced</TabsTrigger>
                        <TabsTrigger value="raw">Raw</TabsTrigger>
                      </TabsList>
                      <TabsContent value="enhanced" className="mt-4">
                        <ResultText
                          content={result.enhanced_transcript}
                          maxHeight="180px"
                        />
                      </TabsContent>
                      <TabsContent value="raw" className="mt-4">
                        <ResultText
                          content={result.raw_transcript || ""}
                          maxHeight="180px"
                        />
                      </TabsContent>
                    </Tabs>
                  ) : (
                    <ResultText
                      content={result.raw_transcript || ""}
                      maxHeight="180px"
                    />
                  )}
                </ResultCard>
              )}

              {result.extracted_data && result.extracted_data.length > 0 && (
                <ResultCard
                  title="Incident Report Data"
                  copyContent={JSON.stringify(result.extracted_data, null, 2)}
                  delay={0.1}
                >
                  <ResultJson data={result.extracted_data} maxHeight="220px" />
                </ResultCard>
              )}

              {result.pdf_available && (
                <Card>
                  <CardContent className="pt-6">
                    <Button
                      onClick={() => openPdfDownload(result.job_id)}
                      className="w-full"
                      variant="outline"
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
            <Card className="border-dashed">
              <CardContent className="flex items-center justify-center py-12">
                <p className="text-muted-foreground text-center">
                  {inputMode === "audio"
                    ? "Upload an incident recording to generate a structured report"
                    : "Enter incident text to generate a structured report"}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </motion.div>
  );
}
