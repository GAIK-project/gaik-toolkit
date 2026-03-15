"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { FileUpload } from "@/components/demo/file-upload";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, ChevronDown, Download, Mic, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface TranscriptSegment {
  start: number | null;
  end: number | null;
  speaker: string | null;
  text: string | null;
}

interface CorrectionSummary {
  total_changes: number;
  insertions: number;
  deletions: number;
  substitutions: number;
}

interface DiffChunk {
  kind: "equal" | "delete" | "insert" | "replace";
  original: string;
  corrected: string;
}

interface TranscribeResult {
  filename: string;
  raw_transcript: string;
  enhanced_transcript: string | null;
  corrected_transcript: string | null;
  correction_summary: CorrectionSummary | null;
  diff_chunks: DiffChunk[] | null;
  job_id: string;
  segments: TranscriptSegment[] | null;
}

export default function TranscriberPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [customContext, setCustomContext] = useState("");
  const [fixTranscriptionErrors, setFixTranscriptionErrors] = useState(false);
  const [compressAudio, setCompressAudio] = useState(true);
  const [language, setLanguage] = useState("auto");
  const [diarization, setDiarization] = useState(false);
  const [speakerCount, setSpeakerCount] = useState("");
  const [minSpeakers, setMinSpeakers] = useState("");
  const [maxSpeakers, setMaxSpeakers] = useState("");
  const [initialPrompt, setInitialPrompt] = useState("");
  const [preferLocalFirst, setPreferLocalFirst] = useState(true);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const [selectedTranscriptView, setSelectedTranscriptView] = useState<"corrected" | "diff" | "diarized" | "raw">("raw");
  const rawDiffRef = useRef<HTMLDivElement | null>(null);
  const correctedDiffRef = useRef<HTMLDivElement | null>(null);
  const syncingPaneRef = useRef<"raw" | "corrected" | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TranscribeResult | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const diarizedContent = result?.segments?.length
    ? result.segments
        .map((segment) => {
          const start = typeof segment.start === "number" ? `${segment.start.toFixed(1)}s` : "?";
          const end = typeof segment.end === "number" ? `${segment.end.toFixed(1)}s` : "?";
          const speaker = segment.speaker || "UNK";
          const text = segment.text?.trim() || "";
          return `[${start} - ${end}] ${speaker}: ${text}`;
        })
        .join("\n")
    : "";

  useEffect(() => {
    if (!result) {
      setSelectedTranscriptView("raw");
      return;
    }

    if (result.corrected_transcript) {
      setSelectedTranscriptView("corrected");
    } else if (diarizedContent) {
      setSelectedTranscriptView("diarized");
    } else {
      setSelectedTranscriptView("raw");
    }
  }, [result, diarizedContent]);

  const selectedTranscriptContent =
    selectedTranscriptView === "corrected"
      ? result?.corrected_transcript || result?.raw_transcript || ""
      : selectedTranscriptView === "diff"
        ? result?.corrected_transcript || result?.raw_transcript || ""
        : selectedTranscriptView === "diarized"
          ? diarizedContent || result?.raw_transcript || ""
          : result?.raw_transcript || "";


  const availableTabCount = [
    Boolean(result?.corrected_transcript),
    Boolean(result?.corrected_transcript && result?.diff_chunks?.length),
    Boolean(diarizedContent),
    true,
  ].filter(Boolean).length;

  function renderDiffColumn(side: "original" | "corrected") {
    if (!result?.diff_chunks?.length) return null;

    return result.diff_chunks.map((chunk, index) => {
      const text = side === "original" ? chunk.original : chunk.corrected;
      if (!text) return null;

      let className = "";
      if (chunk.kind === "replace") {
        className = side === "original" ? "bg-red-100 text-red-900" : "bg-green-100 text-green-900";
      } else if (chunk.kind === "delete" && side === "original") {
        className = "bg-red-100 text-red-900";
      } else if (chunk.kind === "insert" && side === "corrected") {
        className = "bg-green-100 text-green-900";
      }

      return (
        <span key={`${side}-${index}`} className={className ? `${className} rounded px-1 py-0.5` : undefined}>
          {text}{" "}
        </span>
      );
    });
  }

  function syncDiffScroll(source: "raw" | "corrected"): void {
    const sourceEl = source === "raw" ? rawDiffRef.current : correctedDiffRef.current;
    const targetEl = source === "raw" ? correctedDiffRef.current : rawDiffRef.current;
    if (!sourceEl || !targetEl) return;

    if (syncingPaneRef.current && syncingPaneRef.current !== source) {
      syncingPaneRef.current = null;
      return;
    }

    syncingPaneRef.current = source;
    const sourceMax = sourceEl.scrollHeight - sourceEl.clientHeight;
    const targetMax = targetEl.scrollHeight - targetEl.clientHeight;
    const ratio = sourceMax > 0 ? sourceEl.scrollTop / sourceMax : 0;
    targetEl.scrollTop = ratio * Math.max(targetMax, 0);
    targetEl.scrollLeft = sourceEl.scrollLeft;
    requestAnimationFrame(() => {
      if (syncingPaneRef.current === source) {
        syncingPaneRef.current = null;
      }
    });
  }

  function handleDownloadTranscript(): void {
    if (!result || !selectedTranscriptContent.trim()) return;

    const stem = result.filename.replace(/\.[^.]+$/, "") || "transcript";
    const blob = new Blob([selectedTranscriptContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${stem}_transcript.txt`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function loadExampleAudio(): Promise<void> {
    try {
      const response = await fetch("/sample.m4a");
      if (!response.ok) {
        throw new Error(`Failed to load example data (${response.status})`);
      }

      const blob = await response.blob();
      const sampleFile = new File([blob], "sample.m4a", { type: blob.type || "audio/mp4" });
      setFile(sampleFile);
      setResult(null);
      toast.success("Example audio loaded");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load example data");
    }
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading) return; // Prevent double-click

    if (!file) {
      toast.error("Please select an audio/video file first");
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
      formData.append("custom_context", customContext);
      formData.append("fix_transcription_errors", String(fixTranscriptionErrors));
      formData.append("compress_audio", String(compressAudio));
      formData.append("language", language);
      formData.append("diarization", String(diarization));
      formData.append("prefer_local_first", String(preferLocalFirst));
      if (speakerCount.trim() !== "") formData.append("speaker_count", speakerCount.trim());
      if (minSpeakers.trim() !== "") formData.append("min_speakers", minSpeakers.trim());
      if (maxSpeakers.trim() !== "") formData.append("max_speakers", maxSpeakers.trim());
      if (initialPrompt.trim() !== "") formData.append("initial_prompt", initialPrompt.trim());

      const response = await apiFetch("/api/transcribe", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        let errorMessage = "Failed to transcribe";
        try {
          const error = await response.json();
          errorMessage = error.detail || errorMessage;
        } catch {
          // JSON parsing failed, use default message
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setResult(data);

      posthog.capture("audio_transcribed", {
        file_type: file.type,
        file_size: file.size,
        fix_transcription_errors: fixTranscriptionErrors,
        compress_audio: compressAudio,
        has_custom_context: customContext.length > 0,
        language: language,
        diarization: diarization,
        prefer_local_first: preferLocalFirst,
      });

      toast.success("Transcription complete!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return; // Request was aborted, don't show error
      }
      if (error instanceof RateLimitError) {
        return; // Toast already shown by apiFetch
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
        <Button
          variant="ghost"
          className="mb-4 -ml-3 gap-2"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Mic className="h-8 w-8" />
          Transcriber
        </h1>
        <p className="text-muted-foreground mt-2">
          Convert voice recordings and videos into clear, written text
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle>Upload Media</CardTitle>
                  <CardDescription>
                    Select an audio or video file to transcribe
                  </CardDescription>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={loadExampleAudio}
                  disabled={isLoading}
                >
                  Load Example
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <FileUpload
                file={file}
                accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                maxSize={50}
                onFileSelect={setFile}
                onFileRemove={() => {
                  setFile(null);
                  setResult(null);
                }}
                disabled={isLoading}
              />

              <Accordion type="single" collapsible defaultValue="settings" className="w-full">
                <AccordionItem value="settings" className="border-none">
                  <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-sm font-medium">
                    Processing Settings
                  </AccordionTrigger>
                  <AccordionContent className="space-y-6 pt-4">
                    <div className="space-y-2">
                      <Label htmlFor="language">Language</Label>
                      <select
                        id="language"
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                        disabled={isLoading}
                        className="border-input bg-background ring-offset-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <option value="auto">auto</option>
                        <option value="fi">fi</option>
                        <option value="en">en</option>
                      </select>
                    </div>

                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="fix-transcription-errors">Fix Transcription Errors (Beta). Finnish Only.</Label>
                          <p className="text-muted-foreground text-xs">
                            Finnish-focused correction for spelling and ASR errors
                          </p>
                        </div>
                        <Switch
                          id="fix-transcription-errors"
                          checked={fixTranscriptionErrors}
                          onCheckedChange={setFixTranscriptionErrors}
                          disabled={isLoading}
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="compress">Compress Audio</Label>
                          <p className="text-muted-foreground text-xs">
                            Compress before sending (faster upload)
                          </p>
                        </div>
                        <Switch
                          id="compress"
                          checked={compressAudio}
                          onCheckedChange={setCompressAudio}
                          disabled={isLoading}
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="prefer-local-first">Finnish Transcriber</Label>
                          <p className="text-muted-foreground text-xs">
                            Finnish fine-tuned transcriber at HH's FastAPI server
                          </p>
                        </div>
                        <Switch
                          id="prefer-local-first"
                          checked={preferLocalFirst}
                          onCheckedChange={setPreferLocalFirst}
                          disabled={isLoading}
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label htmlFor="diarization">Diarization</Label>
                          <p className="text-muted-foreground text-xs">
                            Enable speaker diarization for the local transcriber
                          </p>
                        </div>
                        <Switch
                          id="diarization"
                          checked={diarization}
                          onCheckedChange={setDiarization}
                          disabled={isLoading}
                        />
                      </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      {diarization ? (
                        <>
                          <div className="space-y-2">
                            <Label htmlFor="speaker-count">Speaker Count</Label>
                            <Input
                              id="speaker-count"
                              type="number"
                              min="1"
                              value={speakerCount}
                              onChange={(e) => setSpeakerCount(e.target.value)}
                              placeholder="Optional"
                              disabled={isLoading}
                            />
                          </div>

                          <div className="space-y-2">
                            <Label htmlFor="min-speakers">Min Speakers</Label>
                            <Input
                              id="min-speakers"
                              type="number"
                              min="1"
                              value={minSpeakers}
                              onChange={(e) => setMinSpeakers(e.target.value)}
                              placeholder="Optional"
                              disabled={isLoading}
                            />
                          </div>

                          <div className="space-y-2">
                            <Label htmlFor="max-speakers">Max Speakers</Label>
                            <Input
                              id="max-speakers"
                              type="number"
                              min="1"
                              value={maxSpeakers}
                              onChange={(e) => setMaxSpeakers(e.target.value)}
                              placeholder="Optional"
                              disabled={isLoading}
                            />
                          </div>
                        </>
                      ) : null}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="initial-prompt">Initial Prompt (Finnish Transcriber)</Label>
                      <Textarea
                        id="initial-prompt"
                        value={initialPrompt}
                        onChange={(e) => setInitialPrompt(e.target.value)}
                        placeholder="Optional hint text for the local transcriber..."
                        disabled={isLoading}
                        rows={3}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="context">Custom Context (OpenAI/Azure fallback)</Label>
                      <Textarea
                        id="context"
                        value={customContext}
                        onChange={(e) => setCustomContext(e.target.value)}
                        placeholder="Optional context for the OpenAI/Azure fallback transcriber (speaker names, technical terms, topic)..."
                        disabled={isLoading}
                        rows={3}
                      />
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <Button
                onClick={handleSubmit}
                disabled={!file || isLoading}
                className="w-full"
                size="lg"
              >
                <Sparkles className="mr-2 h-4 w-4" />
                {isLoading ? "Converting..." : "Transcribe"}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && (
            <LoadingCard
              message="Transcribing audio..."
              subMessage="This may take a while for longer files"
            />
          )}

          {result && !isLoading && (
            <ResultCard
              title="Result"
              description={`File: ${result.filename}`}
              feedbackSlot={<FeedbackButton demoType="transcriber" />}
              delay={0}
            >
              <div className="mb-4 flex justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadTranscript}
                  disabled={!selectedTranscriptContent.trim()}
                >
                  <Download className="mr-2 h-4 w-4" />
                  Download Transcript (.txt)
                </Button>
              </div>

              {result.correction_summary ? (
                <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg border p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-wide">Total changes</div>
                    <div className="text-lg font-semibold">{result.correction_summary.total_changes}</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-wide">Insertions</div>
                    <div className="text-lg font-semibold">{result.correction_summary.insertions}</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-wide">Deletions</div>
                    <div className="text-lg font-semibold">{result.correction_summary.deletions}</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-muted-foreground text-xs uppercase tracking-wide">Substitutions</div>
                    <div className="text-lg font-semibold">{result.correction_summary.substitutions}</div>
                  </div>
                </div>
              ) : null}

              {result.corrected_transcript || diarizedContent ? (
                <Tabs
                  value={selectedTranscriptView}
                  onValueChange={(value) => setSelectedTranscriptView(value as "corrected" | "diff" | "diarized" | "raw")}
                  className="w-full"
                >
                  <TabsList
                    className={`grid w-full ${availableTabCount === 4 ? "grid-cols-4" : availableTabCount === 3 ? "grid-cols-3" : "grid-cols-2"}`}
                  >
                    {result.corrected_transcript ? (
                      <TabsTrigger value="corrected">Corrected</TabsTrigger>
                    ) : null}
                    {result.corrected_transcript && result.diff_chunks?.length ? (
                      <TabsTrigger value="diff">Diff</TabsTrigger>
                    ) : null}
                    {diarizedContent ? (
                      <TabsTrigger value="diarized">Diarized</TabsTrigger>
                    ) : null}
                    <TabsTrigger value="raw">Raw</TabsTrigger>
                  </TabsList>
                  {result.corrected_transcript ? (
                    <TabsContent value="corrected" className="mt-4">
                      <ResultText
                        content={result.corrected_transcript}
                        maxHeight="400px"
                      />
                    </TabsContent>
                  ) : null}
                  {result.corrected_transcript && result.diff_chunks?.length ? (
                    <TabsContent value="diff" className="mt-4">
                      <div className="grid gap-4 lg:grid-cols-2">
                        <div className="rounded-lg border p-4">
                          <div className="mb-3 text-sm font-semibold">Raw</div>
                          <div
                            ref={rawDiffRef}
                            onScroll={() => syncDiffScroll("raw")}
                            className="max-h-[400px] overflow-auto whitespace-pre-wrap text-sm leading-6"
                          >
                            {renderDiffColumn("original")}
                          </div>
                        </div>
                        <div className="rounded-lg border p-4">
                          <div className="mb-3 text-sm font-semibold">Corrected</div>
                          <div
                            ref={correctedDiffRef}
                            onScroll={() => syncDiffScroll("corrected")}
                            className="max-h-[400px] overflow-auto whitespace-pre-wrap text-sm leading-6"
                          >
                            {renderDiffColumn("corrected")}
                          </div>
                        </div>
                      </div>
                    </TabsContent>
                  ) : null}
                  {diarizedContent ? (
                    <TabsContent value="diarized" className="mt-4">
                      <ResultText
                        content={diarizedContent}
                        maxHeight="400px"
                      />
                    </TabsContent>
                  ) : null}
                  <TabsContent value="raw" className="mt-4">
                    <ResultText
                      content={result.raw_transcript || "No transcript generated"}
                      maxHeight="400px"
                    />
                  </TabsContent>
                </Tabs>
              ) : (
                <ResultText
                  content={result.raw_transcript || "No transcript generated"}
                  maxHeight="400px"
                />
              )}
            </ResultCard>
          )}

          {!result && !isLoading && (
            <>
              <EmptyStateCard message="Upload an audio/video file to see transcription here" />

              <Card>
                <button
                  type="button"
                  onClick={() => setHowItWorksOpen((open) => !open)}
                  className="flex w-full items-center justify-between px-6 py-5 text-left transition-colors hover:bg-muted/30"
                  aria-expanded={howItWorksOpen}
                >
                  <h2 className="text-lg font-semibold text-foreground">How It Works</h2>
                  <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <span>{howItWorksOpen ? "Hide" : "Show"}</span>
                    <ChevronDown
                      className={`h-5 w-5 shrink-0 transition-transform ${howItWorksOpen ? "rotate-180" : "rotate-0"}`}
                    />
                  </div>
                </button>
                {howItWorksOpen && (
                  <CardContent className="space-y-4 border-t pt-5 text-sm text-muted-foreground">
                    <p>
                      <strong>1. Upload media:</strong> Add an audio or video file. The demo accepts common speech and meeting formats.
                    </p>
                    <p>
                      <strong>2. Choose transcription settings:</strong> You can select the language, enable the Finnish FastAPI transcriber, turn on diarization, and optionally provide an initial prompt or fallback context.
                    </p>
                    <p>
                      <strong>3. Generate the transcript:</strong> The demo first tries the Finnish transcriber when enabled. If that service is unavailable, it falls back to the configured transcription model.
                    </p>
                    <p>
                      <strong>4. Correct transcription errors:</strong> If the beta Finnish correction option is enabled, the raw transcript is passed through a two-pass correction flow focused on spelling and ASR repair.
                    </p>
                    <p>
                      <strong>5. Review and compare outputs:</strong> The result view can show raw text, diarized output, corrected text, and a side-by-side diff with highlighted changes when correction is enabled.
                    </p>
                    <p>
                      <strong>6. Download the transcript:</strong> The download button exports the transcript currently selected in the result tabs as a <code>.txt</code> file.
                    </p>
                  </CardContent>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}
