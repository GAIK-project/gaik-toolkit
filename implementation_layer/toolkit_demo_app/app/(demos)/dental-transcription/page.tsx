"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
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
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream, type SSEStep } from "@/lib/sse";
import { cn } from "@/lib/utils";
import {
  AudioLines,
  ExternalLink,
  Languages,
  Loader2,
  Mic,
  PencilLine,
  Subtitles,
  Video,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { SubtitleStudio } from "./subtitle-studio";
import {
  EXAMPLES,
  LANGUAGES,
  parseSrt,
  type RawSegment,
  type SubtitleExample,
} from "./subtitle-data";

interface TranscriptionResult {
  job_id: string;
  segments: RawSegment[];
  segments_count: number;
  language?: string | null;
  elapsed_s?: number | null;
}

interface LectureExample {
  title: string;
  source_url: string;
  video_url: string;
  /** Missing from an older server, which sends the SRT text alone. */
  segments?: RawSegment[];
  srt_content?: string;
}

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: AudioLines,
    title: "Add a recording",
    text: "Upload an audio or video file, or start from a ready-made recording.",
  },
  {
    icon: Languages,
    title: "Choose the language",
    text: "Say which language is spoken, or let it be found. For a conversation, turn on speaker detection.",
  },
  {
    icon: Subtitles,
    title: "Transcribe",
    text: "The Finnish HH Whisper server transcribes it and times every segment, and every word.",
  },
  {
    icon: PencilLine,
    title: "Make the subtitles right",
    text: "Play the video with its subtitles, choose how long they are, correct them, and save SRT or VTT.",
  },
];
const GUIDE_NOTES = [
  "Subtitles are made from the timed segments, and their length can be changed afterwards without transcribing again. Corrections are kept in the files you save.",
  "Nothing is saved: the recording and its subtitles stay in this session.",
];

const ACCEPT = ".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac,.mov";
const IS_VIDEO = /\.(mp4|webm|mov)$/i;

export default function VideoTranscriptionPage() {
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [exampleId, setExampleId] = useState<string | null>(null);
  const [language, setLanguage] = useState("auto");
  const [diarization, setDiarization] = useState(false);
  const [speakers, setSpeakers] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingExample, setIsLoadingExample] = useState(false);
  const [steps, setSteps] = useState<SSEStep[]>([]);
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  // What the result is played from: the recording itself, or the lecture clip's own file.
  const [media, setMedia] = useState<{
    url: string;
    isVideo: boolean;
    name: string;
  } | null>(null);
  const [lecture, setLecture] = useState<LectureExample | null>(null);
  const [lectureError, setLectureError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const resultUrl = useRef<string | null>(null);
  const studio = useRef<HTMLDivElement>(null);

  const busy = isLoading || isLoadingExample;

  // The lecture clip is opened and selected when the page opens, without moving the page.
  useEffect(() => {
    void openLecture(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () => () => {
      abortControllerRef.current?.abort();
      if (resultUrl.current) URL.revokeObjectURL(resultUrl.current);
    },
    [],
  );

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

  function clearResult(): void {
    setResult(null);
    setSteps([]);
    setMedia(null);
    if (resultUrl.current) {
      URL.revokeObjectURL(resultUrl.current);
      resultUrl.current = null;
    }
  }

  async function pickExample(example: SubtitleExample): Promise<void> {
    if (busy || !example.url) return;
    setIsLoadingExample(true);
    try {
      const response = await fetch(example.url);
      if (!response.ok) throw new Error("Could not load the recording");
      const blob = await response.blob();
      setFile(
        new File([blob], example.fileName ?? "recording", {
          type: blob.type || "audio/mpeg",
        }),
      );
      setExampleId(example.id);
      setLanguage(example.language);
      setDiarization(Boolean(example.diarization));
      setSpeakers(example.speakers ?? "");
      clearResult();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoadingExample(false);
    }
  }

  /** The lecture clip comes with its finished subtitles: nothing is transcribed. */
  async function openLecture(scroll = true): Promise<void> {
    if (busy) return;
    setIsLoadingExample(true);
    setLectureError(null);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await apiFetch("/api/dental-transcribe/example", {
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to load the example");
      }
      const data = (await response.json()) as LectureExample;
      setLecture(data);
      setFile(null);
      setExampleId("lecture");
      clearResult();
      setMedia({
        url: data.video_url,
        isVideo: true,
        name: "lecture-clip.mp4",
      });
      // The subtitles are read from the SRT when the server sent no segments.
      const segments: RawSegment[] =
        data.segments ??
        parseSrt(data.srt_content ?? "").map((cue) => ({
          start: cue.start,
          end: cue.end,
          text: cue.text,
        }));
      setResult({
        job_id: "example-demo",
        segments,
        segments_count: segments.length,
        language: "fi",
      });
      // The video, with its subtitles, is what the example is for: bring it into view.
      if (scroll)
        setTimeout(
          () =>
            studio.current?.scrollIntoView({
              behavior: "smooth",
              block: "start",
            }),
          100,
        );
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === "AbortError"
          ? "Loading the example timed out. The storage service may be unavailable."
          : error instanceof Error
            ? error.message
            : "Failed to load the example";
      setLectureError(message);
      toast.error(message);
    } finally {
      clearTimeout(timeout);
      setIsLoadingExample(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (busy || !file) return;
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    clearResult();

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", language);
      formData.append("diarization", String(diarization));
      const count = Number.parseInt(speakers, 10);
      if (diarization && Number.isFinite(count) && count > 0) {
        formData.append("min_speakers", String(count));
        formData.append("max_speakers", String(count));
      }

      const response = await apiFetch("/api/dental-transcribe/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) throw new Error("Failed to process the recording");

      let streamError: Error | null = null;
      await processSSEStream<TranscriptionResult>(response, {
        onSteps: (next) => setSteps(next),
        onStepUpdate: (update) =>
          setSteps((previous) =>
            previous.map((step) => (step.step === update.step ? update : step)),
          ),
        onResult: (data) => {
          // The result plays the file it was made from, also if another is chosen later.
          const url = URL.createObjectURL(file);
          resultUrl.current = url;
          setMedia({ url, isVideo: IS_VIDEO.test(file.name), name: file.name });
          setResult(data);
          posthog.capture("dental_transcription_completed", {
            language,
            diarization,
            segments_count: data.segments_count,
            example: exampleId,
          });
          toast.success("Transcription complete");
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
      setSteps((previous) =>
        previous.map((step) =>
          step.status === "in_progress"
            ? { ...step, status: "error", message: "Failed" }
            : step,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Mic}
        iconClassName="text-primary h-8 w-8"
        title="Video Transcription & Subtitles"
        description="Turn a recording into a transcript and subtitles: play them on the video, correct them, and save them as SRT or VTT"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use Video Transcription & Subtitles"
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
            <button
              type="button"
              role="radio"
              aria-checked={exampleId === "lecture"}
              disabled={busy}
              onClick={() => void openLecture()}
              className={cn(
                "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                exampleId === "lecture"
                  ? "border-primary bg-primary/5"
                  : "bg-card hover:border-primary/40",
              )}
            >
              <span className="font-semibold">
                A lecture clip, with subtitles
              </span>
              <span className="text-muted-foreground text-sm">
                A finished video with its subtitles: open it to play, search and
                correct them, with nothing to wait for.
              </span>
              <span className="flex flex-wrap gap-1">
                {["Finnish", "video", "ready-made"].map((tag) => (
                  <Badge key={tag} variant="outline" className="font-normal">
                    {tag}
                  </Badge>
                ))}
              </span>
              {lectureError && (
                <span className="text-destructive text-xs">{lectureError}</span>
              )}
            </button>
            {EXAMPLES.map((example) => (
              <button
                key={example.id}
                type="button"
                role="radio"
                aria-checked={exampleId === example.id}
                disabled={busy}
                onClick={() => void pickExample(example)}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                  exampleId === example.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <span className="font-semibold">{example.title}</span>
                <span className="text-muted-foreground text-sm">
                  {example.summary}
                </span>
                <span className="flex flex-wrap gap-1">
                  {example.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="font-normal">
                      {tag}
                    </Badge>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The recording</CardTitle>
              <CardDescription>
                An audio or video file: MP3, WAV, M4A, MP4, WEBM, OGG, FLAC or
                MOV, up to 50 MB.
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
                  Loading…
                </p>
              )}
              {fileUrl &&
                file &&
                (IS_VIDEO.test(file.name) ? (
                  <video
                    src={fileUrl}
                    controls
                    className="max-h-64 w-full rounded-md"
                    aria-label="Watch the recording"
                  />
                ) : (
                  <audio
                    src={fileUrl}
                    controls
                    className="w-full"
                    aria-label="Listen to the recording"
                  />
                ))}
              {lecture && exampleId === "lecture" && (
                <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-sm">
                  <Video className="text-primary size-4" />
                  {lecture.title}
                  <a
                    href={lecture.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary inline-flex items-center gap-1 underline-offset-2 hover:underline"
                  >
                    Open on YouTube
                    <ExternalLink className="size-3.5" />
                  </a>
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. How to transcribe</CardTitle>
              <CardDescription>
                The language, and whether to tell the speakers apart.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label>Language</Label>
                <div
                  role="radiogroup"
                  aria-label="Language"
                  className="grid grid-cols-2 gap-2"
                >
                  {LANGUAGES.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      role="radio"
                      aria-checked={language === entry.id}
                      disabled={busy}
                      onClick={() => setLanguage(entry.id)}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-sm transition-colors",
                        language === entry.id
                          ? "border-primary bg-primary/10 text-primary font-medium"
                          : "hover:border-primary/40",
                      )}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>
                <p className="text-muted-foreground text-xs">
                  {language === "auto"
                    ? "The language is recognised from the speech. A good choice when it varies or is not known."
                    : "Naming the language is more accurate than letting it be found."}
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-0.5">
                    <Label htmlFor="diarization">Speaker detection</Label>
                    <p className="text-muted-foreground text-xs">
                      Tells who speaks when, so that each subtitle can name its
                      speaker.
                    </p>
                  </div>
                  <Switch
                    id="diarization"
                    checked={diarization}
                    onCheckedChange={setDiarization}
                    disabled={busy}
                  />
                </div>
                {diarization && (
                  <div className="space-y-1">
                    <Label htmlFor="speakers" className="text-xs">
                      Number of speakers (optional)
                    </Label>
                    <Input
                      id="speakers"
                      type="number"
                      min="1"
                      value={speakers}
                      onChange={(e) => setSpeakers(e.target.value)}
                      placeholder="Leave empty to let the server decide"
                      disabled={busy}
                      className="max-w-64"
                    />
                  </div>
                )}
              </div>

              <Button
                onClick={() => void handleSubmit()}
                disabled={!file || busy}
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
              {!file && (
                <p className="text-muted-foreground text-center text-xs">
                  Add a recording first.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isLoading && (
            <Card>
              <CardHeader>
                <CardTitle>Processing</CardTitle>
                <CardDescription>
                  A video has its sound taken out first. A long recording takes
                  a while.
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
            <div ref={studio} className="scroll-mt-20">
              <SubtitleStudio
                key={result.job_id}
                segments={result.segments}
                mediaUrl={media?.url ?? null}
                isVideo={media?.isVideo ?? false}
                fileName={media?.name ?? "subtitles"}
                language={result.language}
                elapsed={result.elapsed_s}
              />
            </div>
          )}

          {!result && !isLoading && (
            <EmptyStateCard
              icon={Subtitles}
              title="No transcription yet"
              description="Add a recording and click Transcribe, or open the lecture clip. The video appears here with its subtitles."
              feedbackSlot={<FeedbackButton demoType="dental-transcription" />}
            />
          )}
          {result && !isLoading && (
            <div className="flex justify-end">
              <FeedbackButton demoType="dental-transcription" />
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  );
}
