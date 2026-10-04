"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
import { schemaTabs, SchemaTabsView } from "@/components/demo/schema-views";
import type { SchemaField } from "@/components/demo/schema-fields-table";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { TaskChangeNotice } from "@/components/demo/task-change-notice";
import { StepIndicator } from "@/components/demo/step-indicator";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream, type SSEStep } from "@/lib/sse";
import { cn } from "@/lib/utils";
import {
  AudioLines,
  AudioWaveform,
  ClipboardList,
  Download,
  FileText,
  Languages,
  Loader2,
  Sparkles,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { ResultView } from "../extractor/result-view";
import {
  TranscriptView,
  type TranscribeResult,
} from "../transcriber/transcript-view";
import { LANGUAGES } from "../transcriber/transcriber-data";
import {
  DEFAULT_OPTIONS,
  EXAMPLES,
  formFields,
  reusableSchemaId,
  schemaKeyFor,
  timingText,
  transcriptRead,
  type AudioExample,
  type AudioOptions,
  type MadeSchema,
  type Timings,
} from "./audio-data";

type AudioResult = Omit<TranscribeResult, "filename"> & {
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  field_table?: SchemaField[];
  structure_type?: string;
  schema_code?: string;
  requirements_json?: string;
  schema_name?: string;
  schema_source?: "saved" | "generated" | "reused";
  schema_id?: string | null;
  timings?: Timings;
};

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: AudioLines,
    title: "Add a recording",
    text: "Upload an audio or video file, or start from a ready-made recording with the task that suits it.",
  },
  {
    icon: ClipboardList,
    title: "Say what to extract",
    text: "Describe the fields in plain words, including lists. The task decides the shape of the result.",
  },
  {
    icon: Languages,
    title: "Choose how to listen",
    text: "Language, speaker detection, hints and error fixing: the same options as in the Transcriber.",
  },
  {
    icon: FileText,
    title: "Check the result",
    text: "Read the data, then the transcript it came from, and the schema that was made for it.",
  },
];
const GUIDE_NOTES = [
  "Three steps run in turn: the recording is transcribed, a schema is made from your task, and the data is extracted from the text. If the transcript is wrong, the data is wrong, so read it.",
  "Change the task and a new schema is made. Nothing is saved: the recording and the result stay in this session.",
];

const ACCEPT = ".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac";
const IS_VIDEO = /\.(mp4|webm)$/i;

function Option({
  title,
  description,
  htmlFor,
  control,
}: {
  title: string;
  description: string;
  htmlFor: string;
  control: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-0.5">
        <Label htmlFor={htmlFor}>{title}</Label>
        <p className="text-muted-foreground text-xs">{description}</p>
      </div>
      {control}
    </div>
  );
}

export default function AudioStructuredPage() {
  const [file, setFile] = useState<File | null>(null);
  const [example, setExample] = useState<AudioExample | null>(EXAMPLES[0]);
  const [task, setTask] = useState(EXAMPLES[0].task);
  const [options, setOptions] = useState<AudioOptions>({
    ...DEFAULT_OPTIONS,
    ...EXAMPLES[0].options,
  });
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<SSEStep[]>([]);
  const [result, setResult] = useState<AudioResult | null>(null);
  const [resultName, setResultName] = useState("");
  // The schema of the last run: while the task is unchanged it is used again.
  const [madeSchema, setMadeSchema] = useState<MadeSchema | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const busy = isLoading || isLoadingExample;
  const set = (patch: Partial<AudioOptions>) =>
    setOptions((previous) => ({ ...previous, ...patch }));
  const language =
    LANGUAGES.find((entry) => entry.id === options.language) ?? LANGUAGES[0];
  const reusable = reusableSchemaId(madeSchema, task) !== null;
  // The text differs from the one the schema in hand was made from: the example's own
  // (ready-made) task, or the task of the last run. A new schema is made for it.
  const changed =
    !reusable &&
    (example ? task.trim() !== example.task.trim() : madeSchema !== null);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  // The player of the chosen recording; the object URL is released when it changes.
  useEffect(() => {
    if (!file) {
      setFileUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // The result keeps its own player, so a new file does not change what is shown.
  useEffect(() => {
    if (!result || !file) {
      setResultUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setResultUrl(url);
    return () => URL.revokeObjectURL(url);
    // Made once per result: the file of that run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  function clearResult(): void {
    setResult(null);
    setSteps([]);
    setSeconds(null);
  }

  async function pickExample(next: AudioExample): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    try {
      const response = await fetch(next.url);
      if (!response.ok) throw new Error("Could not load the recording");
      const blob = await response.blob();
      setFile(
        new File([blob], next.fileName, {
          type: blob.type || "audio/mpeg",
        }),
      );
      setExample(next);
      setTask(next.task);
      setMadeSchema(null);
      setOptions({ ...DEFAULT_OPTIONS, ...next.options });
      clearResult();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy || !file) return;
    if (!task.trim()) {
      toast.error("Describe what to extract");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    clearResult();
    const started = performance.now();

    try {
      const formData = new FormData();
      formData.append("file", file);
      for (const [key, value] of formFields(
        options,
        task,
        schemaKeyFor(example, task),
        reusableSchemaId(madeSchema, task),
      ))
        formData.append(key, value);

      const response = await apiFetch("/api/pipeline/audio/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) throw new Error("Failed to process the recording");

      let streamError: Error | null = null;
      await processSSEStream<AudioResult & { job_id: string }>(response, {
        onSteps: (next) => setSteps(next),
        onStepUpdate: (update) =>
          setSteps((previous) =>
            previous.map((step) => (step.step === update.step ? update : step)),
          ),
        onResult: (data) => {
          setResultName(file.name);
          setResult(data);
          setMadeSchema(data.schema_id ? { id: data.schema_id, task } : null);
          setSeconds((performance.now() - started) / 1000);
          posthog.capture("audio_structured_executed", {
            generate_pdf: options.generatePdf,
            language: options.language,
            diarization: options.diarization,
            fix_errors: options.fixErrors,
            items: data.extracted_data?.length ?? 0,
            schema_source: data.schema_source,
            example: example?.id ?? null,
          });
          toast.success("Recording processed");
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
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `audio_structured_${result.job_id.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Failed to download PDF");
    }
  }

  const transcript = result ? transcriptRead(result) : "";
  const fields = result?.field_table ?? [];

  return (
    <PageTransition>
      <DemoPageHeader
        icon={AudioWaveform}
        title="Audio → Structured Data"
        description="Turn a recording into structured data: it is transcribed, and the fields you describe are extracted from the text"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use Audio → Structured Data"
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
            {EXAMPLES.map((entry) => (
              <div
                key={entry.id}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border-2 p-3 transition-all",
                  example?.id === entry.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={example?.id === entry.id}
                  disabled={busy}
                  onClick={() => void pickExample(entry)}
                  className="flex flex-1 flex-col gap-1.5 text-left"
                >
                  <span className="font-semibold">{entry.title}</span>
                  <span className="text-primary text-xs font-medium">
                    {entry.shape}
                  </span>
                  <span className="text-muted-foreground text-sm">
                    {entry.summary}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {entry.tags.map((tag) => (
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
                  src={entry.url}
                  controls
                  preload="none"
                  className="h-8 w-full"
                  aria-label={`Listen to ${entry.title}`}
                />
              </div>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
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
                    setExample(null);
                    clearResult();
                  }}
                  onFileRemove={() => {
                    setFile(null);
                    setExample(null);
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

            <Card>
              <CardHeader>
                <CardTitle>2. What to extract</CardTitle>
                <CardDescription>
                  Describe the fields in plain words. Ask for a list, and you
                  get one row for each item.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Textarea
                  aria-label="What to extract"
                  value={task}
                  onChange={(e) => setTask(e.target.value)}
                  placeholder="Describe what data to extract…"
                  disabled={busy}
                  rows={12}
                />
                {changed ? (
                  <TaskChangeNotice />
                ) : (
                  <p className="text-muted-foreground text-xs">
                    {reusable
                      ? "The schema of the last run is used again, so only the extraction runs. Change the text and a new schema is generated."
                      : example
                        ? "This task has a ready-made schema, so only the extraction runs. Change the text and a new schema is generated."
                        : "A schema is generated from this text the first time you run it, and used again while the text stays the same. Name the type of a field (number, yes or no, date) and the allowed values to get them exactly."}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle>3. How to listen</CardTitle>
                <CardDescription>
                  The same options as in the Transcriber. The ready-made
                  recordings set them for you.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
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
                  <p className="text-muted-foreground text-xs">
                    {language.hint}
                  </p>
                </div>

                <div className="space-y-3">
                  <Option
                    title="Speaker detection"
                    htmlFor="diarization"
                    description="Tells who speaks when, so that the transcript names the speakers. It works with the HH server only."
                    control={
                      <Switch
                        id="diarization"
                        checked={options.diarization}
                        onCheckedChange={(value) => set({ diarization: value })}
                        disabled={busy}
                      />
                    }
                  />
                  {options.diarization && (
                    <div className="space-y-1">
                      <Label htmlFor="speakers" className="text-xs">
                        Number of speakers (optional)
                      </Label>
                      <Input
                        id="speakers"
                        type="number"
                        min="1"
                        value={options.speakers}
                        onChange={(e) => set({ speakers: e.target.value })}
                        placeholder="Leave empty to let the server decide"
                        disabled={busy}
                        className="max-w-64"
                      />
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="context">Hints (optional)</Label>
                  <Textarea
                    id="context"
                    value={options.context}
                    onChange={(e) => set({ context: e.target.value })}
                    placeholder="Names, technical terms, the topic…"
                    disabled={busy}
                    rows={2}
                  />
                  <p className="text-muted-foreground text-xs">
                    Sent to the model with the recording, so that it spells
                    names and terms the way you wrote them.
                  </p>
                </div>

                <Option
                  title="Fix transcription errors (Beta, Finnish only)"
                  htmlFor="fix-errors"
                  description="A second pass corrects the text before the data is extracted from it. You can review every change in the transcript afterwards."
                  control={
                    <Switch
                      id="fix-errors"
                      checked={options.fixErrors}
                      onCheckedChange={(value) => set({ fixErrors: value })}
                      disabled={busy}
                    />
                  }
                />
                {options.fixErrors && options.language === "en" && (
                  <p className="-mt-3 text-xs text-amber-700">
                    Error fixing is made for Finnish. For English text it may
                    change things that were right.
                  </p>
                )}

                <Option
                  title="Make a PDF report"
                  htmlFor="generate-pdf"
                  description="A PDF with the extracted data, to download after the run."
                  control={
                    <Switch
                      id="generate-pdf"
                      checked={options.generatePdf}
                      onCheckedChange={(value) => set({ generatePdf: value })}
                      disabled={busy}
                    />
                  }
                />

                <Button
                  onClick={() => void handleSubmit()}
                  disabled={!file || busy}
                  className="w-full"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Processing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="mr-2 h-4 w-4" />
                      Extract data
                    </>
                  )}
                </Button>
                {!file && (
                  <p className="text-muted-foreground text-center text-xs">
                    Add a recording first.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <Card>
              <CardHeader>
                <CardTitle>Processing</CardTitle>
                <CardDescription>
                  Transcribing, making the schema, then extracting. A long
                  recording takes a while.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {steps.length > 0 ? (
                  <StepIndicator steps={steps} />
                ) : (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting…
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {result && !isLoading && (
            <Tabs defaultValue="data">
              <TabsList>
                <TabsTrigger value="data">Data</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
                <TabsTrigger value="schema" disabled={fields.length === 0}>
                  Schema
                </TabsTrigger>
              </TabsList>

              <TabsContent value="data" className="mt-3">
                <ResultView
                  results={result.extracted_data ?? []}
                  documentCount={1}
                  noun="recording"
                  seconds={seconds}
                  detail={timingText(result.timings)}
                >
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="outline" className="font-normal">
                      {resultName}
                    </Badge>
                    {result.transcription_model && (
                      <Badge variant="outline" className="font-normal">
                        {result.transcription_model}
                      </Badge>
                    )}
                    {result.corrected_transcript && (
                      <Badge variant="outline" className="font-normal">
                        read the corrected text
                      </Badge>
                    )}
                    {result.used_fallback && (
                      <Badge
                        variant="outline"
                        className="border-amber-500 font-normal text-amber-700"
                      >
                        cloud fallback
                        {result.fallback_reason
                          ? `: ${result.fallback_reason}`
                          : ""}
                      </Badge>
                    )}
                    {result.pdf_available && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleDownloadPdf()}
                      >
                        <Download />
                        Download PDF report
                      </Button>
                    )}
                    <FeedbackButton demoType="audio-structured" />
                  </div>
                  {(result.extracted_data?.length ?? 0) === 0 && transcript && (
                    <p className="text-muted-foreground text-sm">
                      Nothing was extracted. Read the transcript: the recording
                      may not say what the task asks for.
                    </p>
                  )}
                </ResultView>
              </TabsContent>

              <TabsContent value="transcript" className="mt-3">
                {transcript ? (
                  <TranscriptView
                    key={result.job_id}
                    result={{ ...result, filename: resultName }}
                    audioUrl={resultUrl}
                  />
                ) : (
                  <p className="text-muted-foreground text-sm">
                    The recording has no speech that could be read.
                  </p>
                )}
              </TabsContent>

              <TabsContent value="schema" className="mt-3 space-y-2">
                <p className="text-muted-foreground text-sm">
                  The schema made from your task
                  {result.schema_source === "saved"
                    ? " (ready-made)"
                    : result.schema_source === "reused"
                      ? " (made in an earlier run)"
                      : ""}
                  : every field with its type and rule. The data above has
                  exactly these fields.
                </p>
                <SchemaTabsView
                  tabs={schemaTabs({
                    schema_name: result.schema_name ?? "",
                    structure_type: result.structure_type ?? "",
                    schema_code: result.schema_code ?? "",
                    requirements_json: result.requirements_json,
                    field_table: fields,
                  })}
                />
              </TabsContent>
            </Tabs>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={Wand2}
              title="No structured data yet"
              description="Add a recording and click Extract data. The data appears here, with the transcript it came from."
              feedbackSlot={<FeedbackButton demoType="audio-structured" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
