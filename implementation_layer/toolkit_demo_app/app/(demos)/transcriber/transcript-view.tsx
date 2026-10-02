"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { splitByQuery } from "../parser/parser-data";
import {
  activeSegment,
  applyChanges,
  changedParts,
  downloadName,
  formatTime,
  hasSpeakers,
  segmentsToText,
  speakerNames,
  speakerStats,
  wordCount,
  type DiffPart,
  type Segment,
} from "./transcriber-data";

export interface TranscribeResult {
  filename: string;
  raw_transcript: string;
  enhanced_transcript: string | null;
  corrected_transcript: string | null;
  correction_summary: {
    total_changes: number;
    insertions: number;
    deletions: number;
    substitutions: number;
  } | null;
  diff_chunks: DiffPart[] | null;
  job_id: string;
  segments: Segment[] | null;
  used_fallback: boolean;
  fallback_reason: string | null;
  transcription_model: string | null;
  audio_duration_s?: number | null;
  duration_s?: number | null;
  srt_content?: string | null;
  vtt_content?: string | null;
  usage?: Record<string, number> | null;
}

const SPEAKER_COLORS = [
  "bg-sky-100 text-sky-900",
  "bg-violet-100 text-violet-900",
  "bg-amber-100 text-amber-900",
  "bg-emerald-100 text-emerald-900",
  "bg-rose-100 text-rose-900",
  "bg-teal-100 text-teal-900",
];
const SPEAKER_BARS = [
  "bg-sky-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-teal-500",
];

function save(name: string, text: string, type = "text/plain"): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: `${type};charset=utf-8` }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Text with the matches of the search marked. */
function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {splitByQuery(text, query).map((part, index) =>
        part.hit ? (
          <mark
            key={index}
            className="rounded bg-amber-200 px-0.5 text-inherit"
          >
            {part.text}
          </mark>
        ) : (
          part.text
        ),
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}

/** What the transcription made: a player that follows the text, and the ways to read it. */
export function TranscriptView({
  result,
  audioUrl,
}: {
  result: TranscribeResult;
  audioUrl: string | null;
}) {
  const segments = useMemo(() => result.segments ?? [], [result.segments]);
  const parts = useMemo(() => result.diff_chunks ?? [], [result.diff_chunks]);
  const changes = useMemo(() => changedParts(parts), [parts]);
  const speakers = hasSpeakers(segments);
  const names = useMemo(() => speakerNames(segments), [segments]);
  const speakerIndex = useMemo(
    () => new Map([...names.keys()].map((key, index) => [key, index])),
    [names],
  );
  const stats = useMemo(() => speakerStats(segments), [segments]);
  const hasTimeline = segments.length > 0;
  const hasReview = Boolean(result.corrected_transcript) && parts.length > 0;

  const firstTab = result.corrected_transcript
    ? "corrected"
    : hasTimeline
      ? "timeline"
      : "raw";
  const [tab, setTab] = useState(firstTab);
  const [query, setQuery] = useState("");
  const [time, setTime] = useState(0);
  const [follow, setFollow] = useState(true);
  const [accepted, setAccepted] = useState<Set<number>>(() => new Set(changes));
  const [copied, setCopied] = useState<string | null>(null);
  // The text made when the person pressed Done (or Accept all, or Reject all).
  const [saved, setSaved] = useState<{ text: string; key: string } | null>(
    null,
  );
  const [current, setCurrent] = useState(0);
  const [hover, setHover] = useState<number | null>(null);
  const leftPane = useRef<HTMLDivElement>(null);
  const rightPane = useRef<HTMLDivElement>(null);
  const syncing = useRef<"left" | "right" | "nav" | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const list = useRef<HTMLOListElement>(null);

  const playing = hasTimeline ? activeSegment(segments, time) : -1;
  const finalText = useMemo(
    () => (hasReview ? applyChanges(parts, accepted) : ""),
    [accepted, hasReview, parts],
  );

  // The segment being played is kept in view.
  useEffect(() => {
    if (!follow || playing < 0 || tab !== "timeline") return;
    list.current
      ?.querySelector<HTMLElement>(`[data-index="${playing}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [playing, follow, tab]);

  const seek = (seconds: number | null) => {
    const element = audio.current;
    if (!element || seconds === null) return;
    element.currentTime = seconds;
    void element.play().catch(() => undefined);
  };

  const copy = async (what: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  const shownText =
    tab === "corrected"
      ? (result.corrected_transcript ?? "")
      : tab === "review"
        ? (saved?.text ?? finalText)
        : tab === "timeline"
          ? segmentsToText(segments)
          : result.raw_transcript;

  const searchable = tab === "timeline" || tab === "raw" || tab === "corrected";
  const words = wordCount(result.corrected_transcript ?? result.raw_transcript);
  // An older server does not say how long the recording is: the last segment does.
  const lastEnd = segments.reduce(
    (end, segment) => Math.max(end, segment.end ?? 0),
    0,
  );
  const audioSeconds =
    result.audio_duration_s ?? (lastEnd > 0 ? lastEnd : null);
  const took = result.duration_s ?? null;

  const toggle = (index: number) =>
    setAccepted((previous) => {
      const next = new Set(previous);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const choiceKey = (choices: Set<number>) =>
    [...choices].sort((x, y) => x - y).join(",");
  const isStale = saved !== null && saved.key !== choiceKey(accepted);

  /** Takes the choices as they are and makes the final text of them. */
  const finalize = (choices: Set<number>) => {
    setAccepted(choices);
    setSaved({ text: applyChanges(parts, choices), key: choiceKey(choices) });
  };

  // The two panes scroll together, by how far down each one is.
  const syncScroll = (source: "left" | "right") => {
    if (syncing.current === "nav") return;
    const from = source === "left" ? leftPane.current : rightPane.current;
    const to = source === "left" ? rightPane.current : leftPane.current;
    if (!from || !to) return;
    if (syncing.current && syncing.current !== source) {
      syncing.current = null;
      return;
    }
    syncing.current = source;
    const fromMax = from.scrollHeight - from.clientHeight;
    const toMax = to.scrollHeight - to.clientHeight;
    to.scrollTop =
      (fromMax > 0 ? from.scrollTop / fromMax : 0) * Math.max(toMax, 0);
    requestAnimationFrame(() => {
      if (syncing.current === source) syncing.current = null;
    });
  };

  /** Brings a change to the middle of both panes. */
  const reveal = (partIndex: number) => {
    syncing.current = "nav";
    for (const pane of [leftPane.current, rightPane.current]) {
      const target = pane?.querySelector<HTMLElement>(
        `[data-change="${partIndex}"]`,
      );
      if (!pane || !target) continue;
      const top =
        target.getBoundingClientRect().top -
        pane.getBoundingClientRect().top +
        pane.scrollTop -
        pane.clientHeight / 2;
      pane.scrollTo({ top: Math.max(0, top) });
    }
    setTimeout(() => {
      syncing.current = null;
    }, 150);
  };

  const goTo = (position: number) => {
    if (changes.length === 0) return;
    const next = (position + changes.length) % changes.length;
    setCurrent(next);
    reveal(changes[next]);
  };

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>Transcript</CardTitle>
          <Badge variant="outline" className="font-normal">
            {result.filename}
          </Badge>
          {result.transcription_model && (
            <Badge variant="secondary" className="font-mono font-normal">
              {result.transcription_model}
            </Badge>
          )}
          <div className="ml-auto flex flex-wrap gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void copy("text", shownText)}
              disabled={!shownText.trim()}
            >
              {copied === "text" ? <Check /> : <Copy />}
              Copy
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!shownText.trim()}
              onClick={() =>
                save(
                  downloadName(result.filename, "_transcript.txt"),
                  shownText,
                )
              }
            >
              <Download />
              .txt
            </Button>
            {result.srt_content && (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  save(
                    downloadName(result.filename, ".srt"),
                    result.srt_content ?? "",
                  )
                }
              >
                <Download />
                .srt
              </Button>
            )}
            {result.vtt_content && (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  save(
                    downloadName(result.filename, ".vtt"),
                    result.vtt_content ?? "",
                    "text/vtt",
                  )
                }
              >
                <Download />
                .vtt
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                save(
                  downloadName(result.filename, "_transcript.json"),
                  JSON.stringify(result, null, 2),
                  "application/json",
                )
              }
            >
              <Download />
              .json
            </Button>
          </div>
        </div>

        {result.used_fallback && (
          <Alert className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            <AlertTitle>Fallback transcription used</AlertTitle>
            <AlertDescription>
              {result.fallback_reason ||
                "The HH server was unavailable. The cloud model was used instead."}
            </AlertDescription>
          </Alert>
        )}

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Words" value={words.toLocaleString()} />
          <Stat
            label="Recording"
            value={audioSeconds !== null ? formatTime(audioSeconds) : "–"}
          />
          <Stat
            label="Transcribed in"
            value={
              took !== null
                ? `${took.toFixed(1)} s${audioSeconds && took > 0 ? ` (${(audioSeconds / took).toFixed(1)}× real time)` : ""}`
                : "–"
            }
          />
          <Stat
            label={speakers ? "Speakers" : "Timed segments"}
            value={String(speakers ? names.size : segments.length)}
          />
        </div>

        {audioUrl && (
          <audio
            ref={audio}
            src={audioUrl}
            controls
            preload="metadata"
            className="w-full"
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          />
        )}
      </CardHeader>

      <CardContent>
        <Tabs value={tab} onValueChange={setTab}>
          <div className="flex flex-wrap items-center gap-2">
            <TabsList className="h-auto flex-wrap">
              {hasTimeline && (
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
              )}
              {result.corrected_transcript && (
                <TabsTrigger value="corrected">Corrected</TabsTrigger>
              )}
              {hasReview && (
                <TabsTrigger value="review">
                  Review changes
                  <span className="text-muted-foreground ml-1.5 text-xs">
                    {changes.length}
                  </span>
                </TabsTrigger>
              )}
              <TabsTrigger value="raw">Raw</TabsTrigger>
              {speakers && <TabsTrigger value="speakers">Speakers</TabsTrigger>}
              <TabsTrigger value="details">Details</TabsTrigger>
            </TabsList>
            {tab === "timeline" && (
              <label className="text-muted-foreground ml-auto flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(e) => setFollow(e.target.checked)}
                  className="accent-primary size-4"
                />
                Follow the playback
              </label>
            )}
          </div>

          {searchable && (
            <div className="relative mt-3">
              <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search in the transcript"
                aria-label="Search in the transcript"
                className="pr-9 pl-8"
              />
              {query && (
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label="Clear the search"
                  onClick={() => setQuery("")}
                  className="absolute top-1.5 right-1.5"
                >
                  <X />
                </Button>
              )}
            </div>
          )}

          {hasTimeline && (
            <TabsContent value="timeline" className="mt-3">
              <ol
                ref={list}
                className="max-h-[28rem] space-y-1 overflow-auto rounded-md border p-2"
              >
                {segments.map((segment, index) => {
                  const key = segment.speaker ?? "UNKNOWN";
                  const colour = speakerIndex.get(key);
                  const text = segment.text ?? "";
                  if (
                    query.trim() &&
                    !text.toLowerCase().includes(query.trim().toLowerCase())
                  )
                    return null;
                  return (
                    <li key={index} data-index={index}>
                      <button
                        type="button"
                        onClick={() => seek(segment.start)}
                        aria-current={index === playing}
                        className={cn(
                          "hover:bg-muted/60 flex w-full items-start gap-3 rounded-md px-2 py-1.5 text-left transition-colors",
                          index === playing &&
                            "bg-primary/10 ring-primary/40 ring-1",
                        )}
                      >
                        <span className="text-muted-foreground w-12 shrink-0 pt-0.5 font-mono text-xs">
                          {formatTime(segment.start)}
                        </span>
                        {colour !== undefined && (
                          <span
                            className={cn(
                              "shrink-0 rounded px-1.5 py-0.5 text-xs font-medium",
                              SPEAKER_COLORS[colour % SPEAKER_COLORS.length],
                            )}
                          >
                            {names.get(key)}
                          </span>
                        )}
                        <span className="min-w-0 text-sm leading-relaxed">
                          <Marked text={text.trim()} query={query} />
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
              <p className="text-muted-foreground mt-2 text-xs">
                Click a line to play from there.
              </p>
            </TabsContent>
          )}

          {result.corrected_transcript && (
            <TabsContent value="corrected" className="mt-3">
              <div className="max-h-[28rem] overflow-auto rounded-md border p-4 text-sm leading-relaxed whitespace-pre-wrap">
                <Marked text={result.corrected_transcript} query={query} />
              </div>
              {result.correction_summary && (
                <p className="text-muted-foreground mt-2 text-xs">
                  {result.correction_summary.total_changes} changes:{" "}
                  {result.correction_summary.substitutions} substituted,{" "}
                  {result.correction_summary.insertions} added,{" "}
                  {result.correction_summary.deletions} removed. Open “Review
                  changes” to accept or reject them one by one.
                </p>
              )}
            </TabsContent>
          )}

          {hasReview && (
            <TabsContent value="review" className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span>
                  <strong>{accepted.size}</strong> of {changes.length} changes
                  accepted
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => finalize(new Set(changes))}
                >
                  Accept all
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => finalize(new Set())}
                >
                  Reject all
                </Button>
                <div className="ml-auto flex items-center gap-1">
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="Previous change"
                    onClick={() => goTo(current - 1)}
                  >
                    <ChevronUp />
                  </Button>
                  <span className="text-muted-foreground text-xs">
                    change {Math.min(current + 1, changes.length)} of{" "}
                    {changes.length}
                  </span>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="Next change"
                    onClick={() => goTo(current + 1)}
                  >
                    <ChevronDown />
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block size-3 rounded bg-red-200" />
                  Original: where the transcription may be wrong
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block size-3 rounded bg-green-200" />
                  Correction
                </span>
                <span className="text-muted-foreground">
                  Click a change in either column to switch it. The outlined one
                  is kept.
                </span>
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                {(["original", "corrected"] as const).map((side) => (
                  <div key={side} className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <span
                        className={cn(
                          "inline-block size-3 rounded",
                          side === "original" ? "bg-red-200" : "bg-green-200",
                        )}
                      />
                      {side === "original" ? "Original" : "Corrected"}
                    </div>
                    <div
                      ref={side === "original" ? leftPane : rightPane}
                      onScroll={() =>
                        syncScroll(side === "original" ? "left" : "right")
                      }
                      className="bg-background relative h-80 overflow-auto rounded-md border p-4 text-sm leading-9"
                    >
                      {parts.map((part, index) => {
                        if (part.kind === "equal")
                          return <span key={index}>{part.original} </span>;
                        const isOn = accepted.has(index);
                        const corrected = side === "corrected";
                        const chosen = corrected === isOn;
                        const text = corrected
                          ? part.corrected || "(removed)"
                          : part.original || "(nothing)";
                        return (
                          <span key={index}>
                            <button
                              type="button"
                              data-change={index}
                              aria-pressed={chosen}
                              onClick={() => {
                                toggle(index);
                                setCurrent(changes.indexOf(index));
                              }}
                              onMouseEnter={() => setHover(index)}
                              onMouseLeave={() => setHover(null)}
                              title={
                                corrected
                                  ? "Use the correction"
                                  : "Keep the original"
                              }
                              className={cn(
                                "rounded px-1.5 py-0.5 transition-all",
                                corrected
                                  ? "bg-green-100 text-green-900 hover:bg-green-200"
                                  : "bg-red-100 text-red-900 hover:bg-red-200",
                                chosen
                                  ? corrected
                                    ? "ring-2 ring-green-500"
                                    : "ring-2 ring-red-400"
                                  : "line-through opacity-50",
                                hover === index && "outline-primary outline-2",
                              )}
                            >
                              {text}
                            </button>{" "}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={() => finalize(accepted)}>
                  <Check />
                  Done
                </Button>
                <span className="text-muted-foreground text-xs">
                  Done takes the changes you accepted and makes the final text
                  of them.
                </span>
              </div>

              {saved ? (
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold">Final text</span>
                    {isStale ? (
                      <Badge
                        variant="outline"
                        className="border-amber-500 text-amber-700"
                      >
                        You changed the choices: press Done again
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="font-normal">
                        {saved.key === "" ? 0 : saved.key.split(",").length} of{" "}
                        {changes.length} changes applied
                      </Badge>
                    )}
                    <div className="ml-auto flex gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void copy("final", saved.text)}
                      >
                        {copied === "final" ? <Check /> : <Copy />}
                        Copy
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          save(
                            downloadName(result.filename, "_final.txt"),
                            saved.text,
                          )
                        }
                      >
                        <Download />
                        .txt
                      </Button>
                    </div>
                  </div>
                  <div className="bg-muted/30 h-40 overflow-auto rounded-md border p-4 text-sm leading-relaxed whitespace-pre-wrap">
                    {saved.text}
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">
                  The final text appears here when you press Done, Accept all or
                  Reject all.
                </p>
              )}
            </TabsContent>
          )}

          <TabsContent value="raw" className="mt-3">
            <div className="max-h-[28rem] overflow-auto rounded-md border p-4 text-sm leading-relaxed whitespace-pre-wrap">
              {result.raw_transcript ? (
                <Marked text={result.raw_transcript} query={query} />
              ) : (
                "No transcript generated"
              )}
            </div>
          </TabsContent>

          {speakers && (
            <TabsContent value="speakers" className="mt-3 space-y-4">
              <div className="space-y-3">
                {stats.map((stat) => {
                  const colour = speakerIndex.get(stat.key) ?? 0;
                  return (
                    <div key={stat.key} className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 text-xs font-medium",
                            SPEAKER_COLORS[colour % SPEAKER_COLORS.length],
                          )}
                        >
                          {stat.name}
                        </span>
                        <span className="text-muted-foreground">
                          {Math.round(stat.share * 100)}% of the talk ·{" "}
                          {formatTime(stat.seconds)} · {stat.words} words ·{" "}
                          {stat.turns} {stat.turns === 1 ? "turn" : "turns"}
                        </span>
                      </div>
                      <div className="bg-muted h-2 overflow-hidden rounded-full">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            SPEAKER_BARS[colour % SPEAKER_BARS.length],
                          )}
                          style={{ width: `${stat.share * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              {audioSeconds && (
                <div className="space-y-1">
                  <div className="text-sm font-medium">Who speaks when</div>
                  <div
                    className="bg-muted relative h-8 overflow-hidden rounded-md"
                    role="group"
                    aria-label="Speakers along the recording"
                  >
                    {segments.map((segment, index) => {
                      const colour = speakerIndex.get(segment.speaker ?? "");
                      if (
                        colour === undefined ||
                        segment.start === null ||
                        segment.end === null
                      )
                        return null;
                      return (
                        <button
                          key={index}
                          type="button"
                          title={`${names.get(segment.speaker ?? "")} · ${formatTime(segment.start)}`}
                          onClick={() => seek(segment.start)}
                          className={cn(
                            "absolute top-0 h-full opacity-80 hover:opacity-100",
                            SPEAKER_BARS[colour % SPEAKER_BARS.length],
                          )}
                          style={{
                            left: `${(segment.start / audioSeconds) * 100}%`,
                            width: `${Math.max(((segment.end - segment.start) / audioSeconds) * 100, 0.4)}%`,
                          }}
                        />
                      );
                    })}
                    {audioSeconds > 0 && (
                      <span
                        className="bg-foreground pointer-events-none absolute top-0 h-full w-0.5"
                        style={{
                          left: `${Math.min(100, (time / audioSeconds) * 100)}%`,
                        }}
                      />
                    )}
                  </div>
                  <p className="text-muted-foreground text-xs">
                    Click a block to play from there.
                  </p>
                </div>
              )}
            </TabsContent>
          )}

          <TabsContent value="details" className="mt-3">
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
              <dt className="text-muted-foreground">Model</dt>
              <dd className="font-mono">{result.transcription_model ?? "–"}</dd>
              <dt className="text-muted-foreground">Job</dt>
              <dd className="font-mono break-all">{result.job_id}</dd>
              <dt className="text-muted-foreground">Used the fallback</dt>
              <dd>{result.used_fallback ? "yes" : "no"}</dd>
              {result.usage && (
                <>
                  <dt className="text-muted-foreground">Usage</dt>
                  <dd className="font-mono">
                    {Object.entries(result.usage)
                      .map(
                        ([key, value]) => `${key}: ${value.toLocaleString()}`,
                      )
                      .join(" · ")}
                  </dd>
                </>
              )}
              {!hasTimeline && (
                <>
                  <dt className="text-muted-foreground">Timestamps</dt>
                  <dd>
                    Not in this result. Only the HH server times the text; the
                    cloud model returns the text alone.
                  </dd>
                </>
              )}
            </dl>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
