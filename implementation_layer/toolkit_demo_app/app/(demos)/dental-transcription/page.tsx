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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { processSSEStream, type SSEStep } from "@/lib/sse";
import {
  Download,
  FileText,
  Loader2,
  Mic,
  Subtitles,
} from "lucide-react";
import { motion } from "motion/react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface TranscriptionResult {
  job_id: string;
  raw_transcript: string;
  srt_content: string;
  vtt_content: string;
  segments_count: number;
}

export default function DentalTranscriptionPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  async function handleSubmit(): Promise<void> {
    if (isLoading || !audioFile) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setPipelineSteps([]);

    try {
      const formData = new FormData();
      formData.append("file", audioFile);
      formData.append("language", language);

      const response = await apiFetch("/api/dental-transcribe/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error("Failed to process audio");
      }

      let streamError: Error | null = null;

      await processSSEStream<TranscriptionResult>(response, {
        onSteps: (steps) => setPipelineSteps(steps),
        onStepUpdate: (update) => {
          setPipelineSteps((prev) =>
            prev.map((s) => (s.step === update.step ? update : s)),
          );
        },
        onResult: (data) => {
          setResult(data);
          posthog.capture("dental_transcription_completed", {
            language,
            segments_count: data.segments_count,
          });
          toast.success("Transcription complete!");
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

  function resetDemo(): void {
    setAudioFile(null);
    setResult(null);
    setPipelineSteps([]);
  }

  function downloadFile(
    content: string,
    filename: string,
    mimeType: string,
  ): void {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Mic className="h-8 w-8 text-blue-500" />
          Dental Transcription & Close Captioning
        </h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Upload dental education audio or video. Get transcripts and subtitle
          files for close captioning.
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Left: Input */}
        <div className="space-y-6">
          <Card className="shadow-md">
            <CardHeader className="pb-4">
              <CardTitle>Audio / Video Input</CardTitle>
              <CardDescription>
                Upload a dental lecture, procedure video, or audio recording.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <FileUpload
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac,.mov"
                maxSize={50}
                onFileSelect={setAudioFile}
                onFileRemove={resetDemo}
                disabled={isLoading}
              />

              <div className="space-y-2">
                <Label htmlFor="language">Language</Label>
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger id="language" className="w-full">
                    <SelectValue placeholder="Select language" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto-detect</SelectItem>
                    <SelectItem value="fi">Finnish (Suomi)</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="sv">Swedish (Svenska)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                onClick={handleSubmit}
                disabled={isLoading || !audioFile}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Transcribing...
                  </>
                ) : (
                  <>
                    <Subtitles className="mr-2 h-4 w-4" />
                    Transcribe & Generate Subtitles
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          <FeedbackButton demoType="dental-transcription" />
        </div>

        {/* Right: Results */}
        <div className="space-y-6">
          {/* Progress */}
          {isLoading && pipelineSteps.length > 0 && (
            <Card className="shadow-md">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Processing</CardTitle>
              </CardHeader>
              <CardContent>
                <StepIndicator steps={pipelineSteps} orientation="vertical" />
              </CardContent>
            </Card>
          )}

          {/* Results */}
          {result && (
            <div className="space-y-4">
              <Tabs defaultValue="transcript">
                <TabsList className="w-full">
                  <TabsTrigger value="transcript" className="flex-1">
                    <FileText className="mr-2 h-4 w-4" />
                    Transcript
                  </TabsTrigger>
                  <TabsTrigger value="subtitles" className="flex-1">
                    <Subtitles className="mr-2 h-4 w-4" />
                    Subtitles (SRT)
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="transcript">
                  <ResultCard
                    title="Transcript"
                    copyContent={result.raw_transcript}
                  >
                    <ResultText content={result.raw_transcript} />
                  </ResultCard>
                </TabsContent>

                <TabsContent value="subtitles">
                  <ResultCard
                    title={`SRT Subtitles (${result.segments_count} segments)`}
                    copyContent={result.srt_content}
                  >
                    <pre className="bg-muted max-h-96 overflow-auto rounded-lg p-4 font-mono text-sm">
                      {result.srt_content || "No subtitle data available."}
                    </pre>
                  </ResultCard>
                </TabsContent>
              </Tabs>

              {/* Download buttons */}
              <Card className="shadow-md">
                <CardContent className="flex flex-wrap gap-3 pt-6">
                  <Button
                    variant="outline"
                    onClick={() =>
                      downloadFile(
                        result.raw_transcript,
                        "transcript.txt",
                        "text/plain",
                      )
                    }
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Transcript (.txt)
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() =>
                      downloadFile(
                        result.srt_content,
                        "subtitles.srt",
                        "text/plain",
                      )
                    }
                    disabled={!result.srt_content}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Subtitles (.srt)
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() =>
                      downloadFile(
                        result.vtt_content,
                        "subtitles.vtt",
                        "text/vtt",
                      )
                    }
                    disabled={!result.vtt_content}
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Subtitles (.vtt)
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Empty state */}
          {!result && !isLoading && (
            <EmptyStateCard message="Upload an audio or video file to get started. The transcript and subtitle files will appear here." />
          )}
        </div>
      </div>
    </motion.div>
  );
}
