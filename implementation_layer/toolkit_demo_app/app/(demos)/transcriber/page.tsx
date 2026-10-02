"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  AudioLines,
  Languages,
  Loader2,
  Mic,
  Sparkles,
  Users,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { TranscriptView, type TranscribeResult } from "./transcript-view";
import {
  DEFAULT_OPTIONS,
  EXAMPLES,
  LANGUAGES,
  type TranscriberExample,
  type TranscriberOptions,
} from "./transcriber-data";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: AudioLines,
    title: "Add a recording",
    text: "Upload an audio or video file, or start from a ready-made recording that comes with the options that suit it.",
  },
  {
    icon: Languages,
    title: "Choose how to transcribe",
    text: "Language, the Finnish HH server or the cloud model, speaker detection, hints and error fixing.",
  },
  {
    icon: Sparkles,
    title: "Transcribe",
    text: "The text comes with timestamps and speakers when the HH server reads it.",
  },
  {
    icon: Users,
    title: "Explore the result",
    text: "Play the recording and follow the text, search it, see who spoke, and accept or reject each correction.",
  },
];
const GUIDE_NOTES = [
  "Only the HH server (the Finnish transcriber) times the text and detects speakers. The cloud model returns the text alone.",
  "Nothing is saved: the recording and its transcript stay in this session.",
];

const ACCEPT = ".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac";
const IS_VIDEO = /\.(mp4|webm)$/i;

function Option({
  title,
  description,
  htmlFor,
  control,
  disabled,
}: {
  title: string;
  description: string;
  htmlFor: string;
  control: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4",
        disabled && "opacity-60",
      )}
    >
      <div className="space-y-0.5">
        <Label htmlFor={htmlFor}>{title}</Label>
        <p className="text-muted-foreground text-xs">{description}</p>
      </div>
      {control}
    </div>
  );
}

export default function TranscriberPage() {
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<TranscriberOptions>(DEFAULT_OPTIONS);
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TranscribeResult | null>(null);
  const [resultFile, setResultFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isLoading || isLoadingExample;
  const set = (patch: Partial<TranscriberOptions>) =>
    setOptions((previous) => ({ ...previous, ...patch }));
  const language =
    LANGUAGES.find((entry) => entry.id === options.language) ?? LANGUAGES[0];
  const speakersNeedServer = options.diarization && !options.preferLocalFirst;

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  // The recordings are played from the browser's own copy.
  useEffect(() => {
    if (!file) {
      setFileUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!resultFile) {
      setResultUrl(null);
      return;
    }
    const url = URL.createObjectURL(resultFile);
    setResultUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [resultFile]);

  function clearResult(): void {
    setResult(null);
    setResultFile(null);
  }

  async function pickExample(example: TranscriberExample): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    try {
      const response = await fetch(example.url);
      if (!response.ok) throw new Error("Could not load the recording");
      const blob = await response.blob();
      setFile(
        new File([blob], example.fileName, {
          type: blob.type || "audio/mpeg",
        }),
      );
      setOptions({ ...DEFAULT_OPTIONS, ...example.options });
      setExampleId(example.id);
      clearResult();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    if (!file) {
      toast.error("Please select an audio/video file first");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    clearResult();

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("custom_context", options.context);
      formData.append("fix_transcription_errors", String(options.fixErrors));
      if (options.fixInstructions.trim() !== "")
        formData.append(
          "enhanced_transcript_instructions",
          options.fixInstructions.trim(),
        );
      formData.append("compress_audio", String(options.compress));
      formData.append("language", options.language);
      formData.append("diarization", String(options.diarization));
      formData.append("prefer_local_first", String(options.preferLocalFirst));
      if (options.diarization) {
        if (options.speakerCount.trim() !== "")
          formData.append("speaker_count", options.speakerCount.trim());
        if (options.minSpeakers.trim() !== "")
          formData.append("min_speakers", options.minSpeakers.trim());
        if (options.maxSpeakers.trim() !== "")
          formData.append("max_speakers", options.maxSpeakers.trim());
      }
      if (options.context.trim() !== "")
        formData.append("initial_prompt", options.context.trim());

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

      const data = (await response.json()) as TranscribeResult;
      setResult(data);
      setResultFile(file);

      posthog.capture("audio_transcribed", {
        file_type: file.type,
        file_size: file.size,
        fix_transcription_errors: options.fixErrors,
        has_enhanced_transcript_instructions:
          options.fixInstructions.trim().length > 0,
        compress_audio: options.compress,
        has_custom_context: options.context.length > 0,
        language: options.language,
        diarization: options.diarization,
        prefer_local_first: options.preferLocalFirst,
        used_fallback: data.used_fallback,
        fallback_reason: data.fallback_reason,
        transcription_model: data.transcription_model,
        example: exampleId,
      });

      toast.success(
        data.used_fallback
          ? "Transcription complete (cloud fallback)"
          : "Transcription complete!",
      );
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Mic}
        title="Transcriber"
        description="Convert voice recordings and videos into clear, written text"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Transcriber"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">
            Start from a ready-made recording
          </h2>
          <div
            role="radiogroup"
            aria-label="Ready-made recordings"
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
          >
            {EXAMPLES.map((example) => (
              <div
                key={example.id}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border-2 p-3 transition-all",
                  exampleId === example.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={exampleId === example.id}
                  disabled={busy}
                  onClick={() => void pickExample(example)}
                  className="flex flex-1 flex-col gap-1.5 text-left"
                >
                  <span className="font-semibold">{example.title}</span>
                  <span className="text-muted-foreground text-sm">
                    {example.summary}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {example.tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="outline"
                        className="font-normal"
                      >
                        {tag}
                      </Badge>
                    ))}
                  </span>
                </button>
                <audio
                  src={example.url}
                  controls
                  preload="none"
                  className="h-8 w-full"
                  aria-label={`Listen to ${example.title}`}
                />
              </div>
            ))}
          </div>
        </section>

        <div className="grid items-stretch gap-6 md:gap-8 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>1. The recording</CardTitle>
                <CardDescription>
                  An audio or video file: MP3, WAV, M4A, MP4, WEBM, OGG or FLAC.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FileUpload
                  compact
                  file={file}
                  accept={ACCEPT}
                  maxSize={50}
                  onFileSelect={(next) => {
                    setFile(next);
                    setExampleId(null);
                    clearResult();
                  }}
                  onFileRemove={() => {
                    setFile(null);
                    setExampleId(null);
                    clearResult();
                  }}
                  disabled={busy}
                />
                {isLoadingExample && (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading the recording…
                  </p>
                )}
                {fileUrl && file && !IS_VIDEO.test(file.name) && (
                  <audio
                    src={fileUrl}
                    controls
                    className="w-full"
                    aria-label="Listen to the recording"
                  />
                )}
                {fileUrl && file && IS_VIDEO.test(file.name) && (
                  <video
                    src={fileUrl}
                    controls
                    className="max-h-64 w-full rounded-md"
                    aria-label="Watch the recording"
                  />
                )}
              </CardContent>
            </Card>

            <Card className="flex-1">
              <CardHeader>
                <CardTitle>Hints and corrections (optional)</CardTitle>
                <CardDescription>
                  Help the model with the words of this recording, and let it
                  correct the text afterwards.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-2">
                  <Label htmlFor="additional-context">Hints (context)</Label>
                  <Textarea
                    id="additional-context"
                    value={options.context}
                    onChange={(e) => set({ context: e.target.value })}
                    placeholder="Names, technical terms, the topic…"
                    disabled={busy}
                    rows={3}
                  />
                  <p className="text-muted-foreground text-xs">
                    Sent to the model with the recording, so that it spells
                    names and terms the way you wrote them.
                  </p>
                </div>

                <div className="space-y-3">
                  <Option
                    title="Fix transcription errors (Beta, Finnish only)"
                    htmlFor="fix-transcription-errors"
                    description="A second pass corrects spelling and recognition errors in Finnish text. You then review every change and accept or reject it."
                    control={
                      <Switch
                        id="fix-transcription-errors"
                        checked={options.fixErrors}
                        onCheckedChange={(value) => set({ fixErrors: value })}
                        disabled={busy}
                      />
                    }
                  />
                  {options.fixErrors && options.language === "en" && (
                    <p className="text-xs text-amber-700">
                      Error fixing is made for Finnish. For English text it may
                      change things that were right.
                    </p>
                  )}
                  {options.fixErrors && (
                    <div className="space-y-1">
                      <Label
                        htmlFor="enhanced-transcript-instructions"
                        className="text-xs"
                      >
                        Instructions for the fixing
                      </Label>
                      <Textarea
                        id="enhanced-transcript-instructions"
                        value={options.fixInstructions}
                        onChange={(e) =>
                          set({ fixInstructions: e.target.value })
                        }
                        placeholder="For example: keep company names exactly as written…"
                        disabled={busy}
                        rows={2}
                      />
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
          <Card className="flex flex-col">
            <CardHeader>
              <CardTitle>2. How to transcribe</CardTitle>
              <CardDescription>
                Each choice says what it does. The defaults suit most
                recordings.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-5">
              <div className="space-y-2">
                <Label>Language</Label>
                <div
                  role="radiogroup"
                  aria-label="Language"
                  className="grid grid-cols-3 gap-2"
                >
                  {LANGUAGES.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      role="radio"
                      aria-checked={options.language === entry.id}
                      disabled={busy}
                      onClick={() => set({ language: entry.id })}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-sm transition-colors",
                        options.language === entry.id
                          ? "border-primary bg-primary/10 text-primary font-medium"
                          : "hover:border-primary/40",
                      )}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>
                <p className="text-muted-foreground text-xs">{language.hint}</p>
              </div>

              <Option
                title="Finnish transcriber (HH server)"
                htmlFor="prefer-local-first"
                description="Try the Whisper server of Haaga-Helia first. It is the more accurate for Finnish, and it times the text and can tell speakers apart. If it cannot be reached, the cloud model is used instead."
                control={
                  <Switch
                    id="prefer-local-first"
                    checked={options.preferLocalFirst}
                    onCheckedChange={(value) =>
                      set({ preferLocalFirst: value })
                    }
                    disabled={busy}
                  />
                }
              />

              <div className="space-y-3">
                <Option
                  title="Speaker detection"
                  htmlFor="diarization"
                  description="Tells who speaks when, and shows each speaker's share of the talk. Works with the HH server only."
                  disabled={!options.preferLocalFirst}
                  control={
                    <Switch
                      id="diarization"
                      checked={options.diarization}
                      onCheckedChange={(value) => set({ diarization: value })}
                      disabled={busy}
                    />
                  }
                />
                {speakersNeedServer && (
                  <p className="text-xs text-amber-700">
                    Speaker detection needs the HH server. Turn it on above, or
                    the cloud model will return the text without speakers.
                  </p>
                )}
                {options.diarization && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    {(
                      [
                        ["speakerCount", "Exact number", "speaker-count"],
                        ["minSpeakers", "At least", "min-speakers"],
                        ["maxSpeakers", "At most", "max-speakers"],
                      ] as const
                    ).map(([field, label, id]) => (
                      <div key={id} className="space-y-1">
                        <Label htmlFor={id} className="text-xs">
                          {label}
                        </Label>
                        <Input
                          id={id}
                          type="number"
                          min="1"
                          value={options[field]}
                          onChange={(e) => set({ [field]: e.target.value })}
                          placeholder="Optional"
                          disabled={busy}
                        />
                      </div>
                    ))}
                    <p className="text-muted-foreground text-xs sm:col-span-3">
                      Leave them empty to let the server decide. If you know the
                      exact number of speakers, give it.
                    </p>
                  </div>
                )}
              </div>

              <Option
                title="Compress audio"
                htmlFor="compress"
                description="Kept for compatibility. It has no effect at the moment: the file is sent as it is."
                disabled
                control={
                  <Switch
                    id="compress"
                    checked={options.compress}
                    onCheckedChange={(value) => set({ compress: value })}
                    disabled={busy}
                  />
                }
              />

              <Button
                onClick={() => void handleSubmit()}
                disabled={!file || busy}
                className="mt-auto w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Transcribing…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Transcribe
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <LoadingCard
              message="Transcribing audio…"
              subMessage="This may take a while for longer files"
            />
          )}

          {result && !isLoading && (
            <TranscriptView
              key={result.job_id}
              result={result}
              audioUrl={resultUrl}
            />
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={Wand2}
              title="No transcription yet"
              description="Add a recording and click Transcribe. The text appears here with a player that follows it."
              feedbackSlot={<FeedbackButton demoType="transcriber" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
