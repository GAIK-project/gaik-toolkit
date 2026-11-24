"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FeedbackButton } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { RunButton } from "@/components/demo/run-button";
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
import { useAittaSpeech } from "@/components/model-settings";
import { cn } from "@/lib/utils";
import {
  AudioLines,
  Check,
  Languages,
  Loader2,
  Globe,
  Mic,
  Sparkles,
  Users,
  Wand2,
} from "lucide-react";
import Image from "next/image";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { TranscriptView, type TranscribeResult } from "./transcript-view";
import { DialectComparison, MakerLogo } from "./dialect-comparison";
import { CompareColumns, EngineLogo, type Run } from "./compare-columns";
import {
  DEFAULT_OPTIONS,
  ENGINES,
  EXAMPLES,
  LANGUAGES,
  engineById,
  engineRequest,
  languageMatters,
  type EngineId,
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
    text: "One model or several side by side, the language, speaker detection, hints and error fixing.",
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
  "Only the HH server times the text and detects speakers. OpenAI returns the text alone.",
  "On the HH server, Finnish Whisper is used only when the recording is read as Finnish; Whisper large is its general model.",
  "Recordings can be up to 30 minutes; the GAIK team has no time limit.",
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
  const [runs, setRuns] = useState<Run[]>([]);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [resultFile, setResultFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const isLoading = runs.some((run) => run.status === "running");
  const busy = isLoading || isLoadingExample;
  const set = (patch: Partial<TranscriberOptions>) =>
    setOptions((previous) => ({ ...previous, ...patch }));
  const language =
    LANGUAGES.find((entry) => entry.id === options.language) ?? LANGUAGES[0];
  // With an Aitta model picked, Aitta's Whisper transcribes: the HH server and
  // what only it does (a set language, timed text, speakers) are out.
  const aittaSpeech = useAittaSpeech();
  const usesServer =
    !aittaSpeech && options.engines.some((id) => engineById(id).server);
  const speakersNeedServer = options.diarization && !usesServer && !aittaSpeech;
  const languageUsed = !!aittaSpeech || languageMatters(options.engines);
  const openRun =
    runs.find((run) => run.key === openKey && run.status === "done") ??
    runs.find((run) => run.status === "done");

  function toggleEngine(id: EngineId): void {
    setOptions((previous) => {
      const on = previous.engines.includes(id);
      if (on && previous.engines.length === 1) return previous;
      const engines = on
        ? previous.engines.filter((entry) => entry !== id)
        : ENGINES.map((engine) => engine.id).filter(
            (entry) => entry === id || previous.engines.includes(entry),
          );
      return { ...previous, engines };
    });
  }

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
    setRuns([]);
    setOpenKey(null);
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

  /** One model's request; resolves to its result, or throws with the reason. */
  async function transcribeWith(
    recording: File,
    engine: EngineId | null,
    signal: AbortSignal,
  ): Promise<TranscribeResult> {
    const request =
      engine === null
        ? { language: options.language, preferLocalFirst: false }
        : engineRequest(engine, options.language);
    const formData = new FormData();
    formData.append("file", recording);
    formData.append("custom_context", options.context);
    formData.append("fix_transcription_errors", String(options.fixErrors));
    if (options.fixInstructions.trim() !== "")
      formData.append(
        "enhanced_transcript_instructions",
        options.fixInstructions.trim(),
      );
    formData.append("compress_audio", String(options.compress));
    formData.append("language", request.language);
    formData.append("diarization", String(options.diarization));
    formData.append("prefer_local_first", String(request.preferLocalFirst));
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
      signal,
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
    posthog.capture("audio_transcribed", {
      file_type: recording.type,
      file_size: recording.size,
      fix_transcription_errors: options.fixErrors,
      has_enhanced_transcript_instructions:
        options.fixInstructions.trim().length > 0,
      compress_audio: options.compress,
      has_custom_context: options.context.length > 0,
      language: request.language,
      diarization: options.diarization,
      prefer_local_first: request.preferLocalFirst,
      engine: engine ?? "aitta",
      engines: options.engines.length,
      used_fallback: data.used_fallback,
      fallback_reason: data.fallback_reason,
      transcription_model: data.transcription_model,
      example: exampleId,
    });
    return data;
  }

  async function handleSubmit(): Promise<void> {
    if (busy) return;
    if (!file) {
      toast.error("Please select an audio/video file first");
      return;
    }

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // A picked Aitta model transcribes alone; otherwise every picked model runs
    // at the same time, and its column fills in when its answer lands.
    const startedAt = Date.now();
    const planned: Run[] = aittaSpeech
      ? [
          {
            key: "aitta",
            engine: null,
            label: aittaSpeech,
            where: "CSC Aitta",
            status: "running",
            startedAt,
          },
        ]
      : options.engines.map((id) => {
          const engine = engineById(id);
          return {
            key: id,
            engine: id,
            label: engine.name,
            where: engine.where,
            status: "running",
            startedAt,
          };
        });
    setRuns(planned);
    setOpenKey(null);
    setResultFile(file);

    const update = (key: string, patch: Partial<Run>) => {
      if (abortControllerRef.current !== controller) return;
      setRuns((previous) =>
        previous.map((run) => (run.key === key ? { ...run, ...patch } : run)),
      );
    };

    await Promise.all(
      planned.map(async (run) => {
        try {
          const result = await transcribeWith(
            file,
            run.engine,
            controller.signal,
          );
          update(run.key, {
            status: "done",
            result,
            ms: Date.now() - startedAt,
          });
        } catch (error) {
          if (
            controller.signal.aborted ||
            (error instanceof Error && error.name === "AbortError")
          )
            return;
          const message =
            error instanceof RateLimitError
              ? "The run limit is reached for now."
              : error instanceof Error
                ? error.message
                : "An error occurred";
          update(run.key, { status: "error", error: message });
          if (planned.length === 1 && !(error instanceof RateLimitError))
            toast.error(message);
        }
      }),
    );
  }

  /** Cancels the runs in the browser; the page is ready again with its input. */
  function stopRun(): void {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setRuns((previous) => previous.filter((run) => run.status === "done"));
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Mic}
        title="Transcriber"
        description="Turn recordings and videos into text"
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

        <div className="grid grid-cols-1 items-stretch gap-6 md:gap-8 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>1. The recording</CardTitle>
                <CardDescription>
                  An audio or video file of up to 30 minutes. The GAIK team has
                  no time limit.
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
                <Label id="engine-label">Models</Label>
                <div
                  role="group"
                  aria-labelledby="engine-label"
                  className="grid gap-2"
                >
                  {ENGINES.map((engine) => {
                    const checked =
                      !aittaSpeech && options.engines.includes(engine.id);
                    const last = checked && options.engines.length === 1;
                    return (
                      <button
                        key={engine.id}
                        type="button"
                        role="checkbox"
                        aria-checked={checked}
                        disabled={busy || !!aittaSpeech}
                        onClick={() => toggleEngine(engine.id)}
                        title={last ? "Keep at least one model" : undefined}
                        className={cn(
                          "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-[color,background-color,border-color,transform] active:scale-[0.99] disabled:opacity-60",
                          checked
                            ? "border-primary bg-primary/10"
                            : "hover:border-primary/40",
                        )}
                      >
                        <EngineLogo engine={engine.id} />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium">
                            {engine.name}{" "}
                            <span className="text-muted-foreground font-normal">
                              · {engine.where}
                            </span>
                          </span>
                          <span className="text-muted-foreground block text-xs">
                            {engine.note}
                          </span>
                        </span>
                        <span
                          aria-hidden
                          className={cn(
                            "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                            checked
                              ? "border-primary bg-primary text-primary-foreground"
                              : "border-input",
                          )}
                        >
                          {checked && (
                            <Check className="animate-in zoom-in-50 size-3 duration-150" />
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <a
                  href="#dialect-comparison"
                  className="hover:border-primary/40 flex items-center gap-3 rounded-lg border border-dashed px-3 py-2.5 transition-colors"
                >
                  <MakerLogo maker="gaik" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">
                      GAIK dialect model
                    </span>
                    <span className="text-muted-foreground block text-xs">
                      A third of the errors on dialect speech.{" "}
                      <span className="text-primary">See the comparison</span>
                    </span>
                  </span>
                  <Badge variant="outline" className="shrink-0 font-normal">
                    Coming soon
                  </Badge>
                </a>
                <p className="text-muted-foreground text-xs">
                  {aittaSpeech
                    ? `Not used while a CSC Aitta model is picked: ${aittaSpeech} transcribes, and it returns the text without timestamps or speakers.`
                    : options.engines.length > 1
                      ? "The models run at the same time and their texts come side by side. Each model counts as one run."
                      : usesServer
                        ? "If the HH server cannot be reached, OpenAI is used instead."
                        : "Timed text and speaker detection need the HH server."}
                </p>
              </div>

              <div className="space-y-2">
                <Label id="language-label">Language</Label>
                <div
                  role="radiogroup"
                  aria-labelledby="language-label"
                  className="grid grid-cols-3 gap-2"
                >
                  {LANGUAGES.map((entry) => {
                    const checked =
                      languageUsed && options.language === entry.id;
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        role="radio"
                        aria-checked={checked}
                        disabled={busy || !!aittaSpeech || !languageUsed}
                        onClick={() => set({ language: entry.id })}
                        className={cn(
                          "flex min-w-0 items-center justify-center gap-2 rounded-lg border px-2 py-2 text-sm transition-[color,background-color,border-color,transform] active:scale-[0.97] disabled:opacity-60",
                          checked
                            ? "border-primary bg-primary/10 text-primary font-medium"
                            : "hover:border-primary/40",
                        )}
                      >
                        {entry.id === "auto" ? (
                          <Globe className="size-4 shrink-0" aria-hidden />
                        ) : (
                          <Image
                            src={`/icons/flag-${entry.id === "fi" ? "fi" : "gb"}.svg`}
                            alt=""
                            width={16}
                            height={16}
                            className="size-4 shrink-0"
                          />
                        )}
                        {entry.id === "auto" ? (
                          <>
                            <span className="sm:hidden">Auto</span>
                            <span className="hidden truncate sm:inline">
                              {entry.label}
                            </span>
                          </>
                        ) : (
                          <span className="truncate">{entry.label}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
                <p className="text-muted-foreground text-xs">
                  {aittaSpeech
                    ? `Not used: ${aittaSpeech} recognises the language from the speech.`
                    : !languageUsed
                      ? "Not asked: Finnish Whisper always reads the speech as Finnish."
                      : language.hint}
                </p>
              </div>

              <div className="space-y-3">
                <Option
                  title="Speaker detection"
                  htmlFor="diarization"
                  description="Tells who speaks when, and shows each speaker's share of the talk. Works with the HH server only."
                  disabled={!usesServer}
                  control={
                    <Switch
                      id="diarization"
                      checked={options.diarization && !aittaSpeech}
                      onCheckedChange={(value) => set({ diarization: value })}
                      disabled={busy || !!aittaSpeech}
                    />
                  }
                />
                {speakersNeedServer && (
                  <p className="text-xs text-amber-700">
                    Speaker detection needs the HH server. Pick one of its
                    models above, or OpenAI returns the text without speakers.
                  </p>
                )}
                {options.diarization && !aittaSpeech && (
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

              <RunButton
                running={isLoading}
                onRun={() => void handleSubmit()}
                onStop={stopRun}
                icon={Sparkles}
                disabled={!file || isLoadingExample}
                className="mt-auto w-full"
                size="lg"
              >
                Transcribe
              </RunButton>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {runs.length === 1 && isLoading && (
            <LoadingCard
              message="Transcribing audio…"
              subMessage="This may take a while for longer files"
            />
          )}

          {runs.length > 1 && (
            <CompareColumns
              runs={runs}
              openKey={openRun?.key ?? null}
              onOpen={setOpenKey}
            />
          )}

          {runs.length === 1 && runs[0].status === "error" && (
            <EmptyStateCard
              icon={Wand2}
              title="The transcription failed"
              description={runs[0].error ?? "Try again."}
              feedbackSlot={<FeedbackButton demoType="transcriber" />}
            />
          )}

          {openRun?.result && (
            <TranscriptView
              key={openRun.result.job_id}
              result={openRun.result}
              audioUrl={resultUrl}
            />
          )}

          {runs.length === 0 && (
            <EmptyStateCard
              icon={Wand2}
              title="No transcription yet"
              description="Add a recording and click Transcribe. The text appears here with a player that follows it; with more than one model, their texts come side by side."
              feedbackSlot={<FeedbackButton demoType="transcriber" />}
            />
          )}
        </div>

        <DialectComparison />
      </div>
    </PageTransition>
  );
}
