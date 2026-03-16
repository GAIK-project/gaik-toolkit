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
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import { processSSEStream, type SSEStep } from "@/lib/sse";
import {
  ArrowLeft,
  AudioWaveform,
  ChevronDown,
  Download,
  Loader2,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { formatFieldName } from "@/lib/utils";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const DEFAULT_REQUIREMENTS = `Extract the following from the audio:
- Date
- Patient's date of birth
- Symptoms (in few keywords)
- Medical history (in few keywords)
- Examination description (in few keywords)
- Body temperature / Heart Rate / Oxygen saturation
- Procedure performed (in few keywords)
- Diagnosis (in few keywords)
- Prescription (in few keywords)
- Follow-up (in few keywords)`;

const DEFAULT_SCHEMA_KEY = "audio_structured_medical_default";

interface AudioStructuredResult {
  job_id: string;
  raw_transcript: string | null;
  enhanced_transcript: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

export default function AudioStructuredPage() {
  const router = useRouter();
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [userRequirements, setUserRequirements] = useState(DEFAULT_REQUIREMENTS);
  const [generatePdf, setGeneratePdf] = useState(true);
  const [regenerateSchema, setRegenerateSchema] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);

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

  async function handleLoadExample(): Promise<void> {
    try {
      const response = await fetch("/sample.mp3");
      if (!response.ok) {
        throw new Error("Failed to load example audio");
      }
      const blob = await response.blob();
      const exampleFile = new File([blob], "sample.mp3", { type: blob.type || "audio/mpeg" });
      setAudioFile(exampleFile);
      setResult(null);
      setPipelineSteps([]);
      toast.success("Example audio loaded");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load example audio");
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading || !hasInput) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);

    const usingDefaultRequirements = userRequirements.trim() === DEFAULT_REQUIREMENTS.trim();
    if (!usingDefaultRequirements && !regenerateSchema) {
      toast.error("If you edit the extraction requirements, enable Regenerate Schema before extraction.");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", audioFile!);
      formData.append("user_requirements", userRequirements);
      formData.append("compress_audio", "true");
      formData.append("generate_pdf", String(generatePdf));
      formData.append("pdf_title", "Audio Structured Data");
      formData.append("schema_key", usingDefaultRequirements ? DEFAULT_SCHEMA_KEY : "");
      formData.append("regenerate_schema", String(!usingDefaultRequirements && regenerateSchema));

      const response = await apiFetch("/api/pipeline/audio/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error("Failed to process audio");
      }

      let streamError: Error | null = null;

      await processSSEStream<AudioStructuredResult>(response, {
        onSteps: (steps) => setPipelineSteps(steps),
        onStepUpdate: (update) => {
          setPipelineSteps((prev) =>
            prev.map((s) => (s.step === update.step ? update : s)),
          );
        },
        onResult: (data) => {
          setResult(data);
          posthog.capture("audio_structured_executed", {
            generate_pdf: generatePdf,
          });
          toast.success("Audio processed successfully!");
        },
        onError: (message) => {
          streamError = new Error(message);
        },
      });

      if (streamError) throw streamError;
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
        <Button
          variant="ghost"
          className="mb-4 -ml-3 gap-2"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
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
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle>Audio Input</CardTitle>
                  <CardDescription>
                    Upload an audio file to transcribe and extract data from
                  </CardDescription>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleLoadExample}
                  disabled={isLoading}
                >
                  Load Example
                </Button>
              </div>
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
                rows={10}
              />
              <p className="text-muted-foreground mt-2 text-xs">
                If you edit the extraction requirements, enable Regenerate Schema before extraction. Custom regenerated schemas are used only for the current run and are not saved.
              </p>
            </CardContent>
          </Card>

          {/* Advanced Settings */}
          <Accordion type="single" collapsible className="rounded-xl border bg-card shadow-sm">
            <AccordionItem value="advanced" className="border-0">
              <AccordionTrigger className="px-4 py-3 text-sm font-medium hover:no-underline">
                Advanced Settings
              </AccordionTrigger>
              <AccordionContent className="px-4 pb-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="regenerate-schema" className="text-sm">Regenerate Schema</Label>
                      <p className="text-muted-foreground text-xs">
                        Required when you edit the default extraction requirements. Regenerated schemas are not persisted.
                      </p>
                    </div>
                    <Switch
                      id="regenerate-schema"
                      checked={regenerateSchema}
                      onCheckedChange={setRegenerateSchema}
                      disabled={isLoading}
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="generate-pdf" className="text-sm">Generate PDF Report</Label>
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
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>

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

          <Card>
            <button
              type="button"
              className="flex w-full items-center justify-between px-6 py-5 text-left"
              onClick={() => setHowItWorksOpen((current) => !current)}
            >
              <div>
                <CardTitle>How It Works</CardTitle>
                <CardDescription className="mt-1">
                  Transcribe the audio, load or regenerate the extraction schema, and return structured data.
                </CardDescription>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
                {howItWorksOpen ? "Hide" : "Show"}
                <ChevronDown className={`h-4 w-4 transition-transform ${howItWorksOpen ? "rotate-180" : ""}`} />
              </div>
            </button>
            {howItWorksOpen ? (
              <CardContent className="text-muted-foreground space-y-3 text-sm leading-6">
                <p>
                  This module extracts structured information from audios. The user can specify their extraction task in plain language. For instance, the example ("Load Example") audio contains a patient's medical examination done by a doctor. The task specified in the extraction requirements extracts symptoms, medical conditions, diagnosis, follow-up, and related details. The user can edit the extraction task for testing on their own data.
                </p>
                <p>
                  <strong>1. Upload audio:</strong> Add an audio or video file. You can also load the bundled example file.
                </p>
                <p>
                  <strong>2. Define extraction requirements:</strong> The default medical requirements use a persistent saved schema. If you edit the requirements, enable <em>Regenerate Schema</em> before extraction.
                </p>
                <p>
                  <strong>3. Transcribe and extract:</strong> The pipeline transcribes the audio, loads the saved schema when available, or generates a temporary new schema for custom requirements, and then extracts structured fields.
                </p>
                <p>
                  <strong>4. Review the results:</strong> The result panel shows the transcript, extracted structured data, and an optional PDF download when enabled.
                </p>
              </CardContent>
            ) : null}
          </Card>
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

          {isLoading && pipelineSteps.length === 0 && (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="text-primary mx-auto h-8 w-8 animate-spin" />
                  <p className="text-muted-foreground mt-2">Starting audio processing...</p>
                </div>
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
                  copyContent={result.raw_transcript || result.enhanced_transcript || ""}
                  delay={0}
                >
                  <ResultText
                    content={result.raw_transcript || result.enhanced_transcript || ""}
                    maxHeight="200px"
                  />
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
                              <span className="text-muted-foreground min-w-0 wrap-break-word text-sm">
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
