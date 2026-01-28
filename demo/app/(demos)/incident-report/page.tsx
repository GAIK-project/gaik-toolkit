"use client";

import { FileUpload } from "@/components/demo/file-upload";
import { IncidentDetails } from "@/components/demo/incident-details";
import {
  EmptyStateCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
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
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import { parseSSEEvents, type SSEStep } from "@/lib/sse";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ClipboardPaste,
  Download,
  FileText,
  Keyboard,
  Loader2,
  Mic,
  PenLine,
  Settings2,
  Sparkles,
  Wand2,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

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
  input_text: string | null; // For text pipeline
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function IncidentReportPage() {
  const [inputMode, setInputMode] = useState<"audio" | "text">("audio");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState("");
  // Advanced settings state
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [extractionMode, setExtractionMode] = useState<"auto" | "custom">(
    "auto",
  );
  const [customSchema, setCustomSchema] = useState(DEFAULT_INCIDENT_SCHEMA);
  const [enhanced, setEnhanced] = useState(true);
  const [generatePdf, setGeneratePdf] = useState(true);

  const [result, setResult] = useState<IncidentReportResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const hasInput = inputMode === "audio" ? !!audioFile : !!textInput.trim();

  async function handleSubmit(): Promise<void> {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);

    // Initialize steps for immediate feedback
    setPipelineSteps([
      {
        step: 1,
        name: inputMode === "audio" ? "Processing Audio" : "Analyzing Text",
        status: "in_progress",
        message: "Starting pipeline...",
      },
      { step: 2, name: "Data Extraction", status: "pending" },
      { step: 3, name: "Report Formatting", status: "pending" },
    ]);

    try {
      const userRequirements =
        extractionMode === "auto"
          ? "Extract all relevant incident details automatically including date, time, location, description, people involved, injuries, damages, and actions taken."
          : customSchema;

      const formData = new FormData();
      formData.append("user_requirements", userRequirements);
      formData.append("generate_pdf", String(generatePdf));

      // Use SSE streaming for text mode, regular fetch for audio
      if (inputMode === "audio" && audioFile) {
        formData.append("file", audioFile);
        formData.append("enhanced", String(enhanced));
        formData.append("compress_audio", "true");
        formData.append("pdf_title", "Incident Report");

        // Simulating steps for Audio (since it's not SSE in this demo version effectively)
        // In a real app, the audio endpoint ideally should stream too, but we'll adapt.
        const response = await fetch("/api/pipeline/audio", {
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
        // Manually complete steps on success
        setPipelineSteps([
          { step: 1, name: "Processing Audio", status: "completed" },
          { step: 2, name: "Data Extraction", status: "completed" },
          { step: 3, name: "Report Formatting", status: "completed" },
        ]);
        setResult(data);
        toast.success("Incident report generated!");
      } else {
        // Text mode with SSE streaming
        formData.append("text", textInput);
        formData.append("pdf_title", "Incident Report");

        const response = await fetch("/api/pipeline/text/stream", {
          method: "POST",
          body: formData,
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error("Failed to process input");
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = parseSSEEvents(buffer);

          for (const event of events) {
            if (event.type === "steps") {
              setPipelineSteps(event.data.steps as unknown as SSEStep[]);
            } else if (event.type === "step_update") {
              const update = event.data as unknown as SSEStep;
              setPipelineSteps((prev) =>
                prev.map((s) => (s.step === update.step ? update : s)),
              );
            } else if (event.type === "result") {
              setResult(event.data as unknown as IncidentReportResult);
              toast.success("Incident report generated!");
            } else if (event.type === "error") {
              throw new Error(
                (event.data.message as string) || "Processing failed",
              );
            }
          }

          // Clear processed events from buffer
          const lastEventEnd = buffer.lastIndexOf("\n\n");
          if (lastEventEnd !== -1) {
            buffer = buffer.slice(lastEventEnd + 2);
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
      setPipelineSteps((prev) =>
        prev.map((s) =>
          s.status === "in_progress"
            ? { ...s, status: "error", message: "Failed" }
            : s,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }

  function openPdfDownload(jobId: string): void {
    window.open(`/api/pipeline/pdf/${jobId}`, "_blank");
  }

  function resetDemo(): void {
    setAudioFile(null);
    setTextInput("");
    setResult(null);
    setPipelineSteps([]);
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
      <header className="mb-8 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <AlertTriangle className="h-8 w-8 text-amber-500" />
          Incident Reporting
        </h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Easily report incidents via voice or text. AI handles the rest.
        </p>
      </header>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          {/* Input Method Selection Cards */}
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => {
                setInputMode("audio");
                resetDemo();
              }}
              className={cn(
                "hover:bg-muted/50 relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 p-6 text-center transition-all",
                inputMode === "audio"
                  ? "border-primary bg-primary/5 shadow-sm"
                  : "border-muted bg-card hover:border-primary/50",
              )}
            >
              <div
                className={cn(
                  "flex h-12 w-12 items-center justify-center rounded-full transition-colors",
                  inputMode === "audio"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <Mic className="h-6 w-6" />
              </div>
              <div>
                <span className="block font-medium">Audio Report</span>
                <span className="text-muted-foreground text-xs">
                  Record or upload
                </span>
              </div>
              {inputMode === "audio" && (
                <motion.div
                  layoutId="active-indicator"
                  className="bg-primary absolute -bottom-2 h-1 w-12 rounded-full"
                />
              )}
            </button>

            <button
              onClick={() => {
                setInputMode("text");
                resetDemo();
              }}
              className={cn(
                "hover:bg-muted/50 relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 p-6 text-center transition-all",
                inputMode === "text"
                  ? "border-primary bg-primary/5 shadow-sm"
                  : "border-muted bg-card hover:border-primary/50",
              )}
            >
              <div
                className={cn(
                  "flex h-12 w-12 items-center justify-center rounded-full transition-colors",
                  inputMode === "text"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <Keyboard className="h-6 w-6" />
              </div>
              <div>
                <span className="block font-medium">Text Report</span>
                <span className="text-muted-foreground text-xs">
                  Type description
                </span>
              </div>
              {inputMode === "text" && (
                <motion.div
                  layoutId="active-indicator"
                  className="bg-primary absolute -bottom-2 h-1 w-12 rounded-full"
                />
              )}
            </button>
          </div>

          <Card className="border-t-0 shadow-md">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>
                    {inputMode === "audio" ? "Audio Input" : "Text Description"}
                  </CardTitle>
                  <CardDescription>
                    {inputMode === "audio"
                      ? "Upload an audio recording of the incident."
                      : "Provide a detailed description of the event."}
                  </CardDescription>
                </div>
                {inputMode === "text" && (
                  <Button variant="ghost" size="sm" onClick={loadExampleText}>
                    <ClipboardPaste className="mr-2 h-4 w-4" />
                    Load Example
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
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
                  <div
                    className={cn(
                      "rounded-lg border-2 transition-colors",
                      textInput
                        ? "border-primary/30 bg-primary/5"
                        : "border-muted-foreground/25 border-dashed",
                    )}
                  >
                    <Textarea
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      placeholder="Describe the incident: Date, location, who was involved, injuries, and actions taken..."
                      disabled={isLoading}
                      rows={8}
                      className="placeholder:text-muted-foreground/60 min-h-[180px] resize-none border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0"
                    />
                  </div>
                  {textInput && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setTextInput("")}
                      className="text-muted-foreground h-auto p-0 hover:bg-transparent"
                    >
                      Clear text
                    </Button>
                  )}
                </div>
              )}

              {/* Advanced Settings Toggle */}
              <div className="border-muted rounded-lg border">
                <button
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="hover:bg-muted/50 flex w-full items-center justify-between p-3 text-sm font-medium transition-colors"
                  type="button"
                >
                  <div className="flex items-center gap-2">
                    <Settings2 className="text-muted-foreground h-4 w-4" />
                    <span>Advanced Options</span>
                  </div>
                  {showAdvanced ? (
                    <ChevronUp className="text-muted-foreground h-4 w-4" />
                  ) : (
                    <ChevronDown className="text-muted-foreground h-4 w-4" />
                  )}
                </button>
                <AnimatePresence>
                  {showAdvanced && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-4 border-t p-4 pt-4">
                        <div className="space-y-4">
                          <Label>Extraction Mode</Label>
                          <ToggleGroup
                            type="single"
                            value={extractionMode}
                            onValueChange={(val) =>
                              val && setExtractionMode(val as "auto" | "custom")
                            }
                            className="justify-start"
                          >
                            <ToggleGroupItem value="auto" className="gap-2">
                              <Wand2 className="h-4 w-4" />
                              Automatic
                            </ToggleGroupItem>
                            <ToggleGroupItem value="custom" className="gap-2">
                              <PenLine className="h-4 w-4" />
                              Custom Fields
                            </ToggleGroupItem>
                          </ToggleGroup>
                          <p className="text-muted-foreground text-xs">
                            {extractionMode === "auto"
                              ? "AI automatically identifies all relevant details."
                              : "Define specific questions or fields you want answered."}
                          </p>
                        </div>

                        {extractionMode === "custom" && (
                          <div className="space-y-2">
                            <Label htmlFor="schema">Fields to Extract</Label>
                            <Textarea
                              id="schema"
                              value={customSchema}
                              onChange={(e) => setCustomSchema(e.target.value)}
                              placeholder="E.g., What was the weather? Was safety gear worn? Estimate repair costs..."
                              disabled={isLoading}
                              rows={4}
                              className="font-mono text-sm"
                            />
                          </div>
                        )}

                        <div className="space-y-4 pt-2">
                          {inputMode === "audio" && (
                            <div className="flex items-center justify-between">
                              <div className="space-y-0.5">
                                <Label htmlFor="enhanced">
                                  Enhanced Transcript
                                </Label>
                                <p className="text-muted-foreground text-xs">
                                  Clean up grammar and filler words
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
                                Create downloadable PDF file
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
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <Button
                onClick={handleSubmit}
                disabled={!hasInput || isLoading}
                className="w-full"
                size="lg"
              >
                <Sparkles className="mr-2 h-4 w-4" />
                {isLoading ? "Processing..." : "Generate Incident Report"}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Results / Processing Section */}
        <div className="space-y-4">
          {isLoading && (
            <Card className="border-primary/20 overflow-hidden shadow-lg">
              <CardContent className="pt-6">
                <div className="flex flex-col gap-6">
                  <div className="flex items-center gap-4">
                    <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-full">
                      <Loader2 className="text-primary h-6 w-6 animate-spin" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold">
                        AI is working...
                      </h3>
                      <p className="text-muted-foreground text-sm">
                        Please wait while we process your incident report.
                      </p>
                    </div>
                  </div>

                  {pipelineSteps.length > 0 && (
                    <div className="bg-muted/30 rounded-lg border p-4">
                      <StepIndicator
                        steps={pipelineSteps.map((s) => ({
                          id: String(s.step),
                          name: s.name,
                          status: s.status,
                          message: s.message,
                        }))}
                        orientation="vertical"
                      />
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
              className="space-y-4"
            >
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
                  title="Incident Details"
                  description="Details extracted by AI"
                  copyContent={JSON.stringify(result.extracted_data, null, 2)}
                  delay={0.1}
                >
                  <IncidentDetails data={result.extracted_data} />
                </ResultCard>
              )}

              {result.pdf_available && (
                <Card className="bg-primary/5 border-primary/20">
                  <CardContent className="flex items-center justify-between p-6">
                    <div>
                      <h4 className="flex items-center gap-2 font-medium">
                        <FileText className="text-primary h-4 w-4" />
                        PDF Report Ready
                      </h4>
                      <p className="text-muted-foreground text-sm">
                        Download the official report
                      </p>
                    </div>
                    <Button
                      onClick={() => openPdfDownload(result.job_id)}
                      variant="default"
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Download PDF
                    </Button>
                  </CardContent>
                </Card>
              )}
            </motion.div>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              message={
                inputMode === "audio"
                  ? "Your generated report will appear here."
                  : "Submit your details to see the magic happen."
              }
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}
