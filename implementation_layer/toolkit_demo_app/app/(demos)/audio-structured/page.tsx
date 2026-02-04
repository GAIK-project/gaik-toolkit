"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { FileUpload } from "@/components/demo/file-upload";
import {
  EmptyStateCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
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
import { Textarea } from "@/components/ui/textarea";
import { parseSSEEvents, type SSEStep } from "@/lib/sse";
import {
  AudioWaveform,
  ChevronDown,
  ChevronUp,
  Download,
  Loader2,
  Sparkles,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

// Helper function to format field names
function formatFieldName(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

const DEFAULT_REQUIREMENTS = `Extract the following from the audio:
- Key topics discussed
- Important dates and times
- Names of people mentioned
- Action items or decisions made
- Any numerical data or measurements`;

interface AudioStructuredResult {
  job_id: string;
  raw_transcript: string | null;
  enhanced_transcript: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function AudioStructuredPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [userRequirements, setUserRequirements] = useState(DEFAULT_REQUIREMENTS);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [enhanced, setEnhanced] = useState(true);
  const [generatePdf, setGeneratePdf] = useState(false);

  const [result, setResult] = useState<AudioStructuredResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const hasInput = !!audioFile;

  async function handleSubmit(): Promise<void> {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);

    try {
      const formData = new FormData();
      formData.append("file", audioFile!);
      formData.append("user_requirements", userRequirements);
      formData.append("enhanced", String(enhanced));
      formData.append("compress_audio", "true");
      formData.append("generate_pdf", String(generatePdf));
      formData.append("pdf_title", "Audio Structured Data");

      const response = await apiFetch("/api/pipeline/audio/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error("Failed to process audio");
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
            setResult(event.data as unknown as AudioStructuredResult);

            posthog.capture("audio_structured_executed", {
              generate_pdf: generatePdf,
              enhanced: enhanced,
            });

            toast.success("Audio processed successfully!");
          } else if (event.type === "error") {
            throw new Error(
              (event.data.message as string) || "Processing failed",
            );
          }
        }

        const lastEventEnd = buffer.lastIndexOf("\n\n");
        if (lastEventEnd !== -1) {
          buffer = buffer.slice(lastEventEnd + 2);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDownloadPdf(): Promise<void> {
    if (!result?.job_id) return;

    try {
      const response = await apiFetch(`/api/pipeline/pdf/${result.job_id}`);

      if (!response.ok) throw new Error("Failed to download PDF");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audio_structured_${result.job_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success("PDF downloaded!");
    } catch (error) {
      toast.error("Failed to download PDF");
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
          <AudioWaveform className="h-8 w-8" />
          Audio → Structured Data
        </h1>
        <p className="text-muted-foreground mt-2">
          Transcribe audio and extract structured data automatically
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Audio Input</CardTitle>
              <CardDescription>
                Upload an audio file to transcribe and extract data from
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FileUpload
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                maxSize={50}
                file={audioFile}
                onFileSelect={setAudioFile}
                onFileRemove={() => setAudioFile(null)}
                disabled={isLoading}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Extraction Requirements</CardTitle>
              <CardDescription>
                Describe what data you want to extract from the audio
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={userRequirements}
                onChange={(e) => setUserRequirements(e.target.value)}
                placeholder="Describe what data to extract..."
                disabled={isLoading}
                rows={6}
              />
            </CardContent>
          </Card>

          {/* Advanced Settings */}
          <Card>
            <CardHeader className="cursor-pointer" onClick={() => setShowAdvanced(!showAdvanced)}>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Advanced Settings</CardTitle>
                {showAdvanced ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </div>
            </CardHeader>
            <AnimatePresence>
              {showAdvanced && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="enhanced">Enhanced Transcript</Label>
                        <p className="text-muted-foreground text-xs">
                          Improve transcript with punctuation and formatting
                        </p>
                      </div>
                      <Switch
                        id="enhanced"
                        checked={enhanced}
                        onCheckedChange={setEnhanced}
                        disabled={isLoading}
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="generate-pdf">Generate PDF Report</Label>
                        <p className="text-muted-foreground text-xs">
                          Create a downloadable PDF with extracted data
                        </p>
                      </div>
                      <Switch
                        id="generate-pdf"
                        checked={generatePdf}
                        onCheckedChange={setGeneratePdf}
                        disabled={isLoading}
                      />
                    </div>
                  </CardContent>
                </motion.div>
              )}
            </AnimatePresence>
          </Card>

          <Button
            onClick={handleSubmit}
            disabled={isLoading || !hasInput}
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
                Process Audio
              </>
            )}
          </Button>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && pipelineSteps.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Processing</CardTitle>
                <CardDescription>Running audio to structured data pipeline</CardDescription>
              </CardHeader>
              <CardContent>
                <StepIndicator steps={pipelineSteps} />
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <>
              {/* Transcript - only show if there's actual content */}
              {(result.enhanced_transcript && result.enhanced_transcript.trim() !== "") ||
               (result.raw_transcript && result.raw_transcript.trim() !== "") ? (
                <ResultCard
                  title="Transcript"
                  description="Audio transcription"
                  copyContent={result.enhanced_transcript || result.raw_transcript || ""}
                  delay={0}
                >
                  <ResultText>
                    {result.enhanced_transcript || result.raw_transcript}
                  </ResultText>
                </ResultCard>
              ) : null}

              {/* Extracted Data */}
              {result.extracted_data && result.extracted_data.length > 0 && (
                <ResultCard
                  title="Extracted Data"
                  description="Structured data from audio"
                  copyContent={JSON.stringify(result.extracted_data, null, 2)}
                  feedbackSlot={<FeedbackButton demoType="audio-structured" />}
                  delay={0.1}
                >
                  <div className="space-y-4">
                    {result.extracted_data.map((item, index) => (
                      <div key={index} className="space-y-2">
                        {result.extracted_data!.length > 1 && (
                          <p className="text-muted-foreground text-sm font-medium">
                            Item {index + 1}
                          </p>
                        )}
                        <div className="divide-y rounded-md border">
                          {Object.entries(item).map(([key, value]) => (
                            <div key={key} className="flex items-start gap-4 p-3">
                              <span className="min-w-32 text-sm font-medium">
                                {formatFieldName(key)}
                              </span>
                              <span className="text-muted-foreground text-sm">
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
                </ResultCard>
              )}

              {/* PDF Download */}
              {result.pdf_available && (
                <Card>
                  <CardContent className="pt-6">
                    <Button
                      onClick={handleDownloadPdf}
                      variant="outline"
                      className="w-full"
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
            <EmptyStateCard message="Upload an audio file and click process to see results" />
          )}
        </div>
      </div>
    </motion.div>
  );
}
