"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { FileUpload } from "@/components/demo/file-upload";
import { DiaryDetails } from "@/components/demo/diary-details";
import { ProcessingDetails } from "@/components/demo/processing-details";
import {
  EmptyStateCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { PipelineLogViewer } from "@/components/demo/pipeline-log-viewer";
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
import { cn } from "@/lib/utils";
import { parseSSEEvents, type SSEStep } from "@/lib/sse";
import {
  ChevronDown,
  ChevronUp,
  ClipboardPaste,
  Download,
  FileText,
  HardHat,
  Keyboard,
  Loader2,
  Mic,
  Settings2,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const EXAMPLE_ENGLISH = `Construction Site Diary

Project: Riverside Office Complex - Phase 2 Renovation
Author: John Smith, Site Supervisor
Date: January 15, 2025
Week: 3

Weather: Temperature 5°C, wind 3 m/s, partly cloudy

Personnel:
- Site supervisors: 2 persons
- Workers: 5 persons
- Subcontractors: 6 persons (electrical and plumbing)
- Total: 13 persons

Today's work:
- Continued interior demolition on 3rd floor
- Electrical wiring installation on 2nd floor
- Plumbing rough-in started in basement
- Site safety inspection completed

Started work phases: Plumbing installation basement
Ongoing phases: Interior demolition, Electrical installation
Completed phases: Asbestos removal, Initial site prep

Supervisor observations: Work progressing on schedule. Safety compliance excellent.`;

const EXAMPLE_FINNISH = `Työmaapäiväkirja

Kohde: Asunto Oy Tampereen Puistokatu 15 peruskorjaus
Laatija: Matti Virtanen, työnjohtaja
Päivämäärä: 8.1.2025
Työviikko: 2

Sää: Lämpötila -3 astetta, tuuli 2 m/s, pilvinen

Henkilöstö:
- Työnjohtajat: 2 henkilöä
- Työntekijät: 3 henkilöä
- Alihankkijat: 4 henkilöä (sähköurakoitsija)
- Yhteensä: 9 henkilöä

Päivän työt:
- Sisäpurkutyöt jatkuvat 2. kerroksessa
- Sähkövetojen asennus 1. kerroksessa
- Työmaan aitauksen tarkistus

Aloitetut työvaiheet: Sähköasennukset 1. kerros
Käynnissä olevat: Sisäpurku, Rungon purku
Päättyneet: Asbestipurku

Valvojan huomiot: Ei huomautettavaa, työt etenevät aikataulussa`;

// Finnish audio example path
const EXAMPLE_AUDIO_PATH = "/diary-demo/diary.mp3";

interface DiaryResult {
  job_id: string;
  raw_transcript: string | null;
  enhanced_transcript: string | null;
  input_text: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function DiaryPage() {
  const [inputMode, setInputMode] = useState<"audio" | "text">("audio");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [enhanced, setEnhanced] = useState(true);
  const [generatePdf, setGeneratePdf] = useState(true);

  const [result, setResult] = useState<DiaryResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const [processingMetadata, setProcessingMetadata] = useState<{
    schema?: string;
  } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  // Create object URL when audio file changes
  useEffect(() => {
    if (audioFile) {
      const url = URL.createObjectURL(audioFile);
      setAudioUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setAudioUrl(null);
    }
  }, [audioFile]);

  const hasInput = inputMode === "audio" ? !!audioFile : !!textInput.trim();

  async function handleSubmit(): Promise<void> {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);
    setProcessingMetadata(null);

    // Steps are sent by backend via SSE

    try {
      const formData = new FormData();
      formData.append("generate_pdf", String(generatePdf));

      if (inputMode === "audio" && audioFile) {
        formData.append("file", audioFile);
        formData.append("enhanced", String(enhanced));
        formData.append("compress_audio", "true");

        // Use streaming endpoint for real-time progress updates
        const response = await apiFetch("/api/diary/audio/stream", {
          method: "POST",
          body: formData,
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          const errorMessage = await response
            .json()
            .then((err) => err.detail || "Failed to process audio")
            .catch(() => "Failed to process audio");
          throw new Error(errorMessage);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const { events, remaining } = parseSSEEvents(buffer);
          buffer = remaining;

          for (const event of events) {
            if (event.type === "steps") {
              setPipelineSteps(event.data.steps as unknown as SSEStep[]);
            } else if (event.type === "step_update") {
              const update = event.data as unknown as SSEStep;
              setPipelineSteps((prev) =>
                prev.map((s) => (s.step === update.step ? update : s)),
              );
              // Capture schema from step details
              if (update.details?.content) {
                setProcessingMetadata((prev) => ({
                  ...prev,
                  schema: update.details?.content,
                }));
              }
            } else if (event.type === "result") {
              setResult(event.data as unknown as DiaryResult);

              posthog.capture("pipeline_executed", {
                pipeline_type: "diary_audio",
                enhanced: enhanced,
                generate_pdf: generatePdf,
              });

              toast.success("Construction diary processed!");
            } else if (event.type === "error") {
              throw new Error(
                (event.data.message as string) || "Processing failed",
              );
            }
          }

        }
      } else if (inputMode === "text" && textInput.trim()) {
        // Text mode with SSE streaming
        formData.append("text", textInput);

        const response = await apiFetch("/api/diary/text/stream", {
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
          const { events, remaining } = parseSSEEvents(buffer);
          buffer = remaining;

          for (const event of events) {
            if (event.type === "steps") {
              setPipelineSteps(event.data.steps as unknown as SSEStep[]);
            } else if (event.type === "step_update") {
              const update = event.data as unknown as SSEStep;
              setPipelineSteps((prev) =>
                prev.map((s) => (s.step === update.step ? update : s)),
              );
              // Capture schema from step details
              if (update.details?.content) {
                setProcessingMetadata((prev) => ({
                  ...prev,
                  schema: update.details?.content,
                }));
              }
            } else if (event.type === "result") {
              setResult(event.data as unknown as DiaryResult);

              posthog.capture("pipeline_executed", {
                pipeline_type: "diary_text",
                generate_pdf: generatePdf,
              });

              toast.success("Construction diary processed!");
            } else if (event.type === "error") {
              throw new Error(
                (event.data.message as string) || "Processing failed",
              );
            }
          }

        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
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
    window.open(`/api/diary/pdf/${jobId}`, "_blank");
  }

  function resetDemo(): void {
    setAudioFile(null);
    setAudioUrl(null);
    setTextInput("");
    setResult(null);
    setPipelineSteps([]);
    setProcessingMetadata(null);
  }

  function loadExampleText(language: "en" | "fi"): void {
    setInputMode("text");
    setTextInput(language === "en" ? EXAMPLE_ENGLISH : EXAMPLE_FINNISH);
    setResult(null);
  }

  async function loadExampleAudio(): Promise<void> {
    try {
      const response = await fetch(EXAMPLE_AUDIO_PATH);
      const blob = await response.blob();
      const file = new File([blob], "diary-example.mp3", {
        type: "audio/mpeg",
      });
      setInputMode("audio");
      setAudioFile(file);
      setResult(null);
      toast.success("Finnish audio example loaded");
    } catch {
      toast.error("Failed to load audio example");
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <HardHat className="h-8 w-8 text-amber-500" />
          Construction Diary
        </h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Record daily construction site activities via voice or text. AI
          extracts structured data.
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
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
                <span className="block font-medium">Audio Recording</span>
                <span className="text-muted-foreground text-xs">
                  Record or upload
                </span>
              </div>
              {inputMode === "audio" && (
                <motion.div
                  layoutId="diary-active-indicator"
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
                <span className="block font-medium">Text Entry</span>
                <span className="text-muted-foreground text-xs">
                  Type description
                </span>
              </div>
              {inputMode === "text" && (
                <motion.div
                  layoutId="diary-active-indicator"
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
                      ? "Upload an audio recording of the daily diary entry."
                      : "Provide a description of the construction site activities."}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {inputMode === "audio" ? (
                <div className="space-y-4">
                  <FileUpload
                    accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                    maxSize={50}
                    onFileSelect={setAudioFile}
                    onFileRemove={resetDemo}
                    disabled={isLoading}
                  />
                  {/* Load Example Audio Button */}
                  {!audioFile && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={loadExampleAudio}
                      disabled={isLoading}
                      className="w-full"
                    >
                      <ClipboardPaste className="mr-2 h-4 w-4" />
                      Load Example (Finnish)
                    </Button>
                  )}
                  {/* Audio Player Preview */}
                  {audioUrl && (
                    <div className="bg-muted/30 rounded-lg border p-4">
                      <p className="text-muted-foreground mb-2 text-sm font-medium">
                        Preview before processing:
                      </p>
                      <audio controls className="w-full">
                        <source src={audioUrl} type={audioFile?.type} />
                        Your browser does not support the audio element.
                      </audio>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Load Example Buttons */}
                  {!textInput && (
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadExampleText("en")}
                        disabled={isLoading}
                        className="flex-1"
                      >
                        <ClipboardPaste className="mr-2 h-4 w-4" />
                        English Example
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadExampleText("fi")}
                        disabled={isLoading}
                        className="flex-1"
                      >
                        <ClipboardPaste className="mr-2 h-4 w-4" />
                        Finnish Example
                      </Button>
                    </div>
                  )}
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
                      placeholder="Describe the day's activities: Project name, weather, personnel, work completed, started/ongoing/completed work phases, supervisor observations..."
                      disabled={isLoading}
                      rows={10}
                      className="placeholder:text-muted-foreground/60 min-h-[220px] resize-none border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0"
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
                {isLoading ? "Processing..." : "Generate Diary Entry"}
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
                        {pipelineSteps.find((s) => s.status === "in_progress")
                          ?.name || "AI is working..."}
                      </h3>
                      <p className="text-muted-foreground text-sm">
                        {pipelineSteps.find((s) => s.status === "in_progress")
                          ?.message ||
                          "Please wait while we process your diary entry."}
                      </p>
                    </div>
                  </div>

                  {pipelineSteps.length > 0 && (
                    <div className="bg-muted/30 rounded-lg border p-4">
                      <PipelineLogViewer steps={pipelineSteps} />
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

              {processingMetadata?.schema && (
                <ProcessingDetails schema={processingMetadata.schema} />
              )}

              {result.extracted_data && result.extracted_data.length > 0 && (
                <ResultCard
                  title="Diary Details"
                  description="Extracted construction diary fields"
                  copyContent={JSON.stringify(result.extracted_data, null, 2)}
                  feedbackSlot={
                    <FeedbackButton demoType="construction-diary" />
                  }
                  delay={0.1}
                >
                  <DiaryDetails data={result.extracted_data} />
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
                        Download the construction diary report
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
                  ? "Your processed diary entry will appear here."
                  : "Submit your diary details to see the extracted data."
              }
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}
