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
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
  ArrowRight,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Mic,
  Sparkles,
  Subtitles,
  Video,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
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

interface ExampleDemo extends TranscriptionResult {
  video_id: string;
  title: string;
  source_url: string;
  video_url: string;
}

function exampleResultPayload(demo: ExampleDemo): TranscriptionResult {
  const { job_id, raw_transcript, srt_content, vtt_content, segments_count } =
    demo;
  return { job_id, raw_transcript, srt_content, vtt_content, segments_count };
}

const workflowItems = [
  {
    title: "Upload or open the example",
    description: "Use your own file or inspect the ready-made lecture clip.",
  },
  {
    title: "Whisper turns speech into text",
    description:
      "The backend produces transcript, SRT, and VTT subtitle files.",
  },
  {
    title: "Reuse it in video search",
    description: "The same subtitle output can power searchable video moments.",
  },
];

export default function DentalTranscriptionPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [activeTab, setActiveTab] = useState("transcript");
  const [isLoading, setIsLoading] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<SSEStep[]>([]);
  const [exampleDemo, setExampleDemo] = useState<ExampleDemo | null>(null);
  const [exampleLoading, setExampleLoading] = useState(true);
  const [exampleError, setExampleError] = useState<string | null>(null);
  const [exampleTrackUrl, setExampleTrackUrl] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    loadExampleDemo();

    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!exampleDemo?.vtt_content) {
      setExampleTrackUrl(null);
      return;
    }

    const blob = new Blob([exampleDemo.vtt_content], { type: "text/vtt" });
    const url = URL.createObjectURL(blob);
    setExampleTrackUrl(url);

    return () => {
      URL.revokeObjectURL(url);
    };
  }, [exampleDemo]);

  async function loadExampleDemo(): Promise<void> {
    setExampleLoading(true);
    setExampleError(null);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);

    try {
      const response = await apiFetch("/api/dental-transcribe/example", {
        signal: controller.signal,
      });
      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ detail: "Failed to load example" }));
        throw new Error(
          errorData.detail || errorData.error || "Failed to load example",
        );
      }

      const data = await response.json();
      const nextExampleDemo: ExampleDemo = {
        ...data,
        job_id: "example-demo",
      };

      setExampleDemo(nextExampleDemo);
      setResult((current) => current ?? exampleResultPayload(nextExampleDemo));
      setActiveTab((current) =>
        current === "subtitles" ? current : "transcript",
      );
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === "AbortError"
          ? "Example loading timed out. The storage service may be unavailable."
          : error instanceof Error
            ? error.message
            : "Failed to load example demo";
      setExampleError(message);
    } finally {
      clearTimeout(timeout);
      setExampleLoading(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading || !audioFile) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);
    setActiveTab("transcript");
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
            prev.map((step) => (step.step === update.step ? update : step)),
          );
        },
        onResult: (data) => {
          setResult(data);
          setActiveTab("transcript");
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
        prev.map((step) =>
          step.status === "in_progress"
            ? { ...step, status: "error", message: "Failed" }
            : step,
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
    setActiveTab("transcript");
  }

  const [exampleApplying, setExampleApplying] = useState(false);

  function useExampleOutput(): void {
    if (!exampleDemo || exampleApplying) return;

    setExampleApplying(true);
    setAudioFile(null);
    setIsLoading(false);
    setPipelineSteps([
      { step: 1, name: "Transcription", status: "completed" },
      { step: 2, name: "Subtitle Generation", status: "completed" },
    ]);

    setTimeout(() => {
      setResult(exampleResultPayload(exampleDemo));
      setActiveTab("subtitles");
      setExampleApplying(false);
      toast.success("Example output loaded — see transcript & subtitles above");
      document
        .querySelector('[data-slot="tabs-list"]')
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 600);
  }

  function downloadFile(
    content: string,
    filename: string,
    mimeType: string,
  ): void {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-6 space-y-3 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Mic className="text-primary h-8 w-8" />
          Video Transcription & Subtitles
        </h1>
        <p className="text-muted-foreground max-w-2xl leading-relaxed">
          Upload a recording or open the ready-made example. Whisper turns
          speech into a transcript and subtitle files (SRT &amp; VTT).
        </p>
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {workflowItems.map((item, i) => (
            <span key={item.title} className="flex items-center gap-1.5">
              <span className="bg-primary/10 text-primary inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold">
                {i + 1}
              </span>
              {item.title}
            </span>
          ))}
        </div>
      </header>

      <div className="space-y-6">
        <Card className="shadow-md">
          <CardHeader className="pb-4">
            <CardTitle>Upload Your Own File</CardTitle>
            <CardDescription>
              Add an audio or video file and the app will generate transcript,
              SRT, and VTT subtitle files.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 sm:grid-cols-[1fr_auto]">
              <FileUpload
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac,.mov"
                maxSize={50}
                file={audioFile}
                onFileSelect={setAudioFile}
                onFileRemove={resetDemo}
                disabled={isLoading}
              />

              <div className="flex flex-col gap-3 sm:w-52">
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
                      Transcribing…
                    </>
                  ) : (
                    <>
                      <Subtitles className="mr-2 h-4 w-4" />
                      Transcribe
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

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

        {result && (
          <div className="space-y-4">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
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
                  title={
                    result.job_id === "example-demo"
                      ? "Example Transcript"
                      : "Transcript"
                  }
                  description={
                    result.job_id === "example-demo"
                      ? "Pre-generated result from the example lecture video."
                      : undefined
                  }
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
                  <pre className="bg-muted max-h-96 overflow-auto rounded-lg p-4 font-mono text-sm whitespace-pre-wrap wrap-break-word">
                    {result.srt_content || "No subtitle data available."}
                  </pre>
                </ResultCard>
              </TabsContent>
            </Tabs>

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
                <Button variant="ghost" asChild>
                  <Link href="/video-search">
                    <Sparkles className="mr-2 h-4 w-4" />
                    Open Semantic Video Search
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        )}

        {!result && !isLoading && (
          <EmptyStateCard message="Upload your own file or load the ready-made example to see transcript and subtitle output here." />
        )}

        <Accordion
          type="single"
          collapsible
          defaultValue={!result && !isLoading ? "example" : undefined}
          className="border-border/70 rounded-xl border"
        >
          <AccordionItem value="example" className="border-none">
            <AccordionTrigger className="px-4 py-3 hover:no-underline">
              <span className="flex items-center gap-2">
                <Video className="text-primary h-4 w-4" />
                <span className="font-semibold">Ready-made Example</span>
                <span className="text-muted-foreground font-normal">
                  — lecture clip with pre-generated subtitles
                </span>
                {exampleLoading && (
                  <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />
                )}
              </span>
            </AccordionTrigger>
            <AccordionContent className="px-4">
              {exampleLoading ? (
                <div className="bg-muted flex h-32 items-center justify-center rounded-xl">
                  <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
                </div>
              ) : exampleError ? (
                <div className="bg-destructive/5 border-destructive/20 rounded-xl border p-4">
                  <p className="text-sm font-medium">Example unavailable</p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {exampleError}
                  </p>
                  <p className="text-muted-foreground mt-2 text-xs">
                    For local development, verify that the FastAPI backend is
                    running and that the Allas environment variables are loaded.
                  </p>
                  <Button
                    variant="outline"
                    className="mt-3"
                    onClick={loadExampleDemo}
                  >
                    Retry
                  </Button>
                </div>
              ) : exampleDemo ? (
                <div className="grid gap-5 md:grid-cols-[1.4fr_1fr]">
                  <div className="overflow-hidden rounded-xl bg-black">
                    <video
                      key={exampleDemo.video_url}
                      src={exampleDemo.video_url}
                      controls
                      playsInline
                      preload="metadata"
                      className="aspect-video w-full"
                    >
                      {exampleTrackUrl && (
                        <track
                          default
                          kind="captions"
                          src={exampleTrackUrl}
                          srcLang="fi"
                          label="Finnish captions"
                        />
                      )}
                    </video>
                  </div>

                  <div className="flex flex-col gap-3">
                    <div className="bg-muted/35 border-border/70 rounded-xl border p-3">
                      <p className="text-sm font-semibold">
                        {exampleDemo.title}
                      </p>
                      <p className="text-muted-foreground mt-1 text-sm">
                        {exampleDemo.segments_count} subtitle segments &middot;
                        Transcript + SRT + VTT
                      </p>
                    </div>

                    <Button
                      onClick={useExampleOutput}
                      disabled={exampleApplying}
                      className="w-full"
                    >
                      {exampleApplying ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Loading…
                        </>
                      ) : (
                        <>
                          {result?.job_id === "example-demo"
                            ? "Reload Example Output"
                            : "Load Example Output"}
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </>
                      )}
                    </Button>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        asChild
                        className="flex-1"
                      >
                        <a
                          href={exampleDemo.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          YouTube Source
                          <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                        </a>
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        asChild
                        className="flex-1"
                      >
                        <Link href="/video-search">
                          Video Search
                          <Sparkles className="ml-1.5 h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        <FeedbackButton demoType="dental-transcription" />
      </div>
    </motion.div>
  );
}
