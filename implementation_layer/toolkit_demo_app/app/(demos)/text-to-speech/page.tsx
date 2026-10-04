"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard } from "@/components/demo/result-card";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  AudioLines,
  Check,
  Download,
  Languages,
  Loader2,
  RotateCcw,
  Trash2,
  Users,
  Volume2,
  Wand2,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  bytesFromBase64,
  estimateSeconds,
  EXAMPLES,
  type TtsExample,
  formatDuration,
  joinBytes,
  LANGUAGES,
  MAX_CHARACTERS,
  MAX_COMPARE_VOICES,
  MAX_PART_CHARACTERS,
  splitForSpeech,
  VOICES,
  wordCount,
  type Language,
  type VoiceId,
} from "./tts-data";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: AudioLines,
    title: "Write or load a text",
    text: "Up to 3,000 characters. A longer text is cut at the ends of sentences and read in parts, then joined into one audio file.",
  },
  {
    icon: Users,
    title: "Choose one voice, or compare",
    text: "Pick one voice, or up to three to hear the same text in each of them.",
  },
  {
    icon: Volume2,
    title: "Generate",
    text: "Each voice gets its own take, with a player, its length and a download.",
  },
  {
    icon: Check,
    title: "Listen and keep what you like",
    text: "Takes pile up on this page: play them one after another, download the ones you want, remove the rest.",
  },
];
const GUIDE_NOTES = [
  "The speech is made by one model through the GAIK TextToSpeech component. The language of the text is recognised from the text itself, and the voice sets how it sounds.",
  "Takes live in this browser tab only. Reloading or closing the tab loses them, so download the ones you want.",
];

interface TtsResponse {
  filename: string;
  job_id: string;
  model: string;
  voice: string;
  language: string;
  response_format: string;
  content_type: string;
  character_count: number;
  audio_base64: string;
}

interface Take {
  id: string;
  voice: string;
  language: string;
  model: string;
  characters: number;
  parts: number;
  format: string;
  filename: string;
  url: string;
  bytes: number;
  /** Known when the browser has read the file. */
  duration: number | null;
}

export default function TextToSpeechPage() {
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<Language>("fi");
  const [voices, setVoices] = useState<VoiceId[]>(["alloy"]);
  const [exampleTitle, setExampleTitle] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [takes, setTakes] = useState<Take[]>([]);
  const [playing, setPlaying] = useState<string | null>(null);
  const urls = useRef<Set<string>>(new Set());
  const players = useRef<Map<string, HTMLAudioElement>>(new Map());

  const parts = splitForSpeech(text);
  const tooLong = text.trim().length > MAX_CHARACTERS;
  const seconds = estimateSeconds(text, language);
  const requests = parts.length * voices.length;

  useEffect(() => {
    const known = urls.current;
    return () => known.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  function loadExample(example: TtsExample): void {
    setText(example.text);
    setLanguage(example.language);
    setVoices(example.voices);
    setExampleTitle(example.title);
  }

  function resetInput(): void {
    setText("");
    setLanguage("fi");
    setVoices(["alloy"]);
    setExampleTitle(null);
  }

  function toggleVoice(id: VoiceId): void {
    setVoices((current) => {
      if (current.includes(id))
        return current.length === 1 ? current : current.filter((v) => v !== id);
      if (current.length >= MAX_COMPARE_VOICES) {
        toast.error(`Compare up to ${MAX_COMPARE_VOICES} voices at a time.`);
        return current;
      }
      return [...current, id];
    });
    setExampleTitle(null);
  }

  /** One voice reads every part of the text; the parts are joined into one file. */
  async function speak(voice: VoiceId): Promise<Take> {
    const clips: Uint8Array[] = [];
    let first: TtsResponse | null = null;
    for (const part of parts) {
      const formData = new FormData();
      formData.append("text", part);
      formData.append("voice", voice);
      formData.append("language", language);
      const response = await apiFetch("/api/text-to-speech", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate audio");
      }
      const data = (await response.json()) as TtsResponse;
      first ??= data;
      clips.push(bytesFromBase64(data.audio_base64));
    }
    if (!first) throw new Error("There is no text to read");
    const bytes = joinBytes(clips);
    const url = URL.createObjectURL(
      new Blob([new Uint8Array(bytes)], { type: first.content_type }),
    );
    urls.current.add(url);
    return {
      id: `${first.job_id}-${voice}`,
      voice,
      language: first.language,
      model: first.model,
      characters: text.trim().length,
      parts: parts.length,
      format: first.response_format,
      filename: `${voice}-${first.filename}`,
      url,
      bytes: bytes.length,
      duration: null,
    };
  }

  async function handleSubmit(): Promise<void> {
    if (isLoading) return;
    if (!text.trim()) {
      toast.error("Please enter text first");
      return;
    }
    if (tooLong) {
      toast.error(`Text cannot exceed ${MAX_CHARACTERS} characters`);
      return;
    }
    setIsLoading(true);
    const chosen = [...voices];
    let done = 0;
    let failed = 0;
    setProgress(`0 of ${chosen.length} voices ready`);
    try {
      // The voices are read side by side: the takes appear as each one is ready.
      await Promise.all(
        chosen.map(async (voice) => {
          try {
            const take = await speak(voice);
            setTakes((previous) => [take, ...previous]);
            posthog.capture("tts_generated", {
              language: take.language,
              voice: take.voice,
              characters: take.characters,
              parts: take.parts,
              model: take.model,
              compared_voices: chosen.length,
              example: exampleTitle,
            });
          } catch (error) {
            if (error instanceof RateLimitError) return;
            failed += 1;
            toast.error(
              `${voice}: ${error instanceof Error ? error.message : "An error occurred"}`,
            );
          } finally {
            done += 1;
            setProgress(`${done} of ${chosen.length} voices ready`);
          }
        }),
      );
      if (failed < chosen.length)
        toast.success(
          chosen.length === 1 ? "Audio generated" : "Takes generated",
        );
    } finally {
      setIsLoading(false);
      setProgress(null);
    }
  }

  function removeTake(id: string): void {
    setTakes((previous) => {
      const gone = previous.find((take) => take.id === id);
      if (gone) {
        URL.revokeObjectURL(gone.url);
        urls.current.delete(gone.url);
      }
      return previous.filter((take) => take.id !== id);
    });
  }

  function clearTakes(): void {
    for (const take of takes) {
      URL.revokeObjectURL(take.url);
      urls.current.delete(take.url);
    }
    setTakes([]);
    setPlaying(null);
  }

  function download(take: Take): void {
    const link = document.createElement("a");
    link.href = take.url;
    link.download = take.filename;
    link.click();
  }

  /** Plays the takes one after another, newest first, to hear the voices in turn. */
  function playAll(): void {
    const order = takes.map((take) => take.id);
    const start = (index: number) => {
      const next = players.current.get(order[index]);
      if (!next) return;
      next.currentTime = 0;
      void next.play();
      next.onended = () => start(index + 1);
    };
    for (const player of players.current.values()) {
      player.pause();
      player.onended = null;
    }
    start(0);
  }

  const submitLabel =
    voices.length === 1
      ? "Generate speech"
      : `Generate with ${voices.length} voices`;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Volume2}
        title="Text-to-Speech"
        description="Convert text into downloadable speech audio using OpenAI or Azure OpenAI."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use Text-to-Speech"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Start from an example</h2>
          <div
            role="radiogroup"
            aria-label="Examples"
            className="grid gap-3 sm:grid-cols-2"
          >
            {EXAMPLES.map((example) => (
              <button
                key={example.title}
                type="button"
                role="radio"
                aria-checked={exampleTitle === example.title}
                disabled={isLoading}
                onClick={() => loadExample(example)}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                  exampleTitle === example.title
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
            <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
              <div>
                <CardTitle>1. The text</CardTitle>
                <CardDescription>
                  Up to {MAX_CHARACTERS.toLocaleString()} characters. The server
                  reads {MAX_PART_CHARACTERS.toLocaleString()} at a time, so a
                  longer text goes in parts.
                </CardDescription>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={resetInput}
                disabled={isLoading || (!text && voices.length === 1)}
                className="gap-1.5"
              >
                <RotateCcw className="h-4 w-4" />
                Reset
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <Label htmlFor="tts-text">Text</Label>
              <Textarea
                id="tts-text"
                value={text}
                onChange={(event) => {
                  setText(event.target.value);
                  setExampleTitle(null);
                }}
                placeholder="Write the text you want to convert into speech…"
                rows={12}
                disabled={isLoading}
              />
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <Badge
                  variant="outline"
                  className={cn(
                    "font-normal",
                    tooLong && "border-destructive text-destructive",
                  )}
                >
                  {text.trim().length.toLocaleString()} /{" "}
                  {MAX_CHARACTERS.toLocaleString()} characters
                </Badge>
                <Badge variant="outline" className="font-normal">
                  {wordCount(text).toLocaleString()} words
                </Badge>
                {text.trim() && !tooLong && (
                  <>
                    <Badge variant="outline" className="font-normal">
                      {parts.length} {parts.length === 1 ? "part" : "parts"}
                    </Badge>
                    <Badge variant="outline" className="font-normal">
                      about {formatDuration(seconds)} of speech
                    </Badge>
                  </>
                )}
              </div>
              {tooLong && (
                <p className="text-destructive text-xs">
                  The text is over {MAX_CHARACTERS.toLocaleString()} characters.
                  Shorten it to generate speech.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. The voice</CardTitle>
              <CardDescription>
                Pick one voice, or up to {MAX_COMPARE_VOICES} to compare them on
                the same text.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                role="group"
                aria-label="Voices"
                className="grid gap-2 sm:grid-cols-2"
              >
                {VOICES.map((voice) => {
                  const chosen = voices.includes(voice.id);
                  return (
                    <button
                      key={voice.id}
                      type="button"
                      aria-pressed={chosen}
                      disabled={isLoading}
                      onClick={() => toggleVoice(voice.id)}
                      className={cn(
                        "flex flex-col gap-0.5 rounded-lg border-2 p-2.5 text-left transition-all",
                        chosen
                          ? "border-primary bg-primary/5"
                          : "hover:border-primary/40",
                      )}
                    >
                      <span className="flex items-center gap-1.5 text-sm font-semibold capitalize">
                        {chosen && <Check className="text-primary size-3.5" />}
                        {voice.id}
                      </span>
                      <span className="text-muted-foreground text-xs">
                        {voice.note}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="text-muted-foreground text-xs">
                The descriptions are rough guidance: listen to find the voice
                that suits your text.
              </p>

              <div className="space-y-2">
                <Label className="flex items-center gap-1.5">
                  <Languages className="size-4" />
                  Language of the text
                </Label>
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
                      disabled={isLoading}
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
                  Tells the component which language to expect. The speech model
                  also recognises the language from the text.
                </p>
              </div>

              <Button
                onClick={() => void handleSubmit()}
                disabled={isLoading || !text.trim() || tooLong}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {progress ?? "Generating audio…"}
                  </>
                ) : (
                  submitLabel
                )}
              </Button>
              {text.trim() && !tooLong && requests > 1 && !isLoading && (
                <p className="text-muted-foreground text-center text-xs">
                  {requests} requests: {parts.length}{" "}
                  {parts.length === 1 ? "part" : "parts"} for each of{" "}
                  {voices.length} {voices.length === 1 ? "voice" : "voices"}.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {takes.length > 0 ? (
            <Card>
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>Takes</CardTitle>
                  <Badge variant="outline" className="font-normal">
                    {takes.length}
                  </Badge>
                  <div className="ml-auto flex flex-wrap items-center gap-1.5">
                    {takes.length > 1 && (
                      <Button size="sm" variant="outline" onClick={playAll}>
                        <Volume2 />
                        Play them in turn
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={clearTakes}>
                      <Trash2 />
                      Remove all
                    </Button>
                    <FeedbackButton demoType="text-to-speech" />
                  </div>
                </div>
                <CardDescription>
                  The newest take is first. They are kept in this tab only.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {takes.map((take) => (
                  <div
                    key={take.id}
                    className={cn(
                      "space-y-2 rounded-lg border p-3 transition-colors",
                      playing === take.id && "border-primary bg-primary/5",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold capitalize">
                        {take.voice}
                      </span>
                      <Badge variant="secondary" className="font-normal">
                        {take.language}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        {formatDuration(take.duration)}
                      </Badge>
                      <Badge variant="outline" className="font-normal">
                        {take.characters.toLocaleString()} characters
                        {take.parts > 1 && `, ${take.parts} parts`}
                      </Badge>
                      <Badge
                        variant="outline"
                        className="font-mono font-normal"
                      >
                        {take.model}
                      </Badge>
                      <div className="ml-auto flex gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => download(take)}
                        >
                          <Download />
                          {take.format}
                        </Button>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Remove the ${take.voice} take`}
                          onClick={() => removeTake(take.id)}
                        >
                          <X />
                        </Button>
                      </div>
                    </div>
                    <audio
                      ref={(element) => {
                        if (element) players.current.set(take.id, element);
                        else players.current.delete(take.id);
                      }}
                      controls
                      preload="metadata"
                      src={take.url}
                      className="w-full"
                      onLoadedMetadata={(e) => {
                        const length = e.currentTarget.duration;
                        setTakes((previous) =>
                          previous.map((entry) =>
                            entry.id === take.id && entry.duration === null
                              ? { ...entry, duration: length }
                              : entry,
                          ),
                        );
                      }}
                      onPlay={() => setPlaying(take.id)}
                      onPause={() =>
                        setPlaying((current) =>
                          current === take.id ? null : current,
                        )
                      }
                    />
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : (
            !isLoading && (
              <EmptyStateCard
                icon={Wand2}
                title="No audio generated yet"
                description="Write a text or load the example, choose a voice (or three to compare), then generate speech. The takes appear here."
                feedbackSlot={<FeedbackButton demoType="text-to-speech" />}
              />
            )
          )}
        </div>
      </div>
    </PageTransition>
  );
}
