"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  Download,
  RotateCcw,
  Search,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  activeCue,
  clock,
  FAST_READING,
  isFast,
  LENGTHS,
  regroup,
  saveName,
  searchCues,
  shiftCues,
  statsOf,
  toSrt,
  toText,
  toVtt,
  type Cue,
  type RawSegment,
} from "./subtitle-data";

function save(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: `${type};charset=utf-8` }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

const SPEAKER_COLORS = [
  "bg-sky-100 text-sky-900",
  "bg-violet-100 text-violet-900",
  "bg-amber-100 text-amber-900",
  "bg-emerald-100 text-emerald-900",
  "bg-rose-100 text-rose-900",
];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}

/**
 * What the transcription made: the recording with its subtitles on, and the subtitles as a
 * list to read, search, correct and save. Their length can be changed without transcribing
 * again, and all their times moved.
 */
export function SubtitleStudio({
  segments,
  mediaUrl,
  isVideo,
  fileName,
  language,
  elapsed,
}: {
  segments: RawSegment[];
  mediaUrl: string | null;
  isVideo: boolean;
  fileName: string;
  language?: string | null;
  /** How long the transcription took, in seconds. */
  elapsed?: number | null;
}) {
  const [maxChars, setMaxChars] = useState(0);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [offset, setOffset] = useState(0);
  const [withSpeakers, setWithSpeakers] = useState(true);
  const [query, setQuery] = useState("");
  const [hit, setHit] = useState(0);
  const [time, setTime] = useState(0);
  const [follow, setFollow] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const media = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const track = useRef<TextTrack | null>(null);
  const list = useRef<HTMLOListElement>(null);

  const base = useMemo(() => regroup(segments, maxChars), [segments, maxChars]);
  const hasWords = segments.some((segment) => (segment.words?.length ?? 0) > 1);
  const hasSpeakers = base.some((cue) => cue.speaker !== null);
  const edited = Object.keys(edits).length > 0;

  // The subtitles as they are now: the regrouped text, the corrections, the shift in time.
  const cues: Cue[] = useMemo(
    () =>
      shiftCues(
        base.map((cue, index) =>
          edits[index] !== undefined ? { ...cue, text: edits[index] } : cue,
        ),
        offset,
      ),
    [base, edits, offset],
  );
  const stats = useMemo(() => statsOf(cues), [cues]);
  const hits = useMemo(() => searchCues(cues, query), [cues, query]);
  const playing = activeCue(cues, time);
  const speakerIndex = useMemo(() => {
    const names = [...new Set(cues.map((cue) => cue.speaker).filter(Boolean))];
    return new Map(names.map((name, index) => [name as string, index]));
  }, [cues]);

  // The subtitles are put on the video as a caption track, and replaced when they change.
  useEffect(() => {
    const element = media.current;
    if (!element || !isVideo) return;
    if (!track.current) {
      track.current = element.addTextTrack(
        "captions",
        "Subtitles",
        language ?? "",
      );
    }
    const current = track.current;
    current.mode = "showing";
    Array.from(current.cues ?? []).forEach((cue) => current.removeCue(cue));
    for (const cue of cues) {
      if (cue.end <= cue.start) continue;
      const text =
        withSpeakers && cue.speaker ? `${cue.speaker}: ${cue.text}` : cue.text;
      current.addCue(new VTTCue(cue.start, cue.end, text));
    }
  }, [cues, isVideo, language, withSpeakers]);

  // The subtitle being played is kept in view.
  useEffect(() => {
    if (!follow || playing < 0) return;
    list.current
      ?.querySelector<HTMLElement>(`[data-index="${playing}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [playing, follow]);

  const seek = (seconds: number) => {
    const element = media.current;
    if (!element) return;
    element.currentTime = seconds;
    void element.play().catch(() => undefined);
  };

  const jumpToHit = (next: number) => {
    if (hits.length === 0) return;
    const at = ((next % hits.length) + hits.length) % hits.length;
    setHit(at);
    const cue = cues[hits[at]];
    list.current
      ?.querySelector<HTMLElement>(`[data-index="${hits[at]}"]`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
    if (cue) seek(cue.start);
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

  const changeLength = (value: number) => {
    if (value === maxChars) return;
    if (edited) toast("Regrouping starts from the original text again.");
    setMaxChars(value);
    setEdits({});
  };

  const reset = () => {
    setEdits({});
    setOffset(0);
  };

  const srt = toSrt(cues, withSpeakers);
  const vtt = toVtt(cues, withSpeakers);
  const text = toText(cues, withSpeakers);
  const length =
    LENGTHS.find((entry) => entry.value === maxChars) ?? LENGTHS[0];

  return (
    <div className="space-y-4">
      <div className="bg-card flex flex-wrap items-center gap-3 rounded-xl border p-4 shadow-sm">
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {stats.count} {stats.count === 1 ? "subtitle" : "subtitles"}
            <span className="text-muted-foreground font-normal">
              {" "}
              · {stats.words} words · {clock(stats.duration)}
              {language ? ` · ${language}` : ""}
            </span>
          </p>
          <p className="text-muted-foreground text-xs">
            {elapsed != null ? `Transcribed in ${elapsed.toFixed(1)} s. ` : ""}
            Corrections and the length are kept in the files you save.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => save(saveName(fileName, "txt"), text, "text/plain")}
        >
          <Download className="size-4" />
          Transcript (.txt)
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => save(saveName(fileName, "srt"), srt, "text/plain")}
          disabled={cues.length === 0}
        >
          <Download className="size-4" />
          Subtitles (.srt)
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => save(saveName(fileName, "vtt"), vtt, "text/vtt")}
          disabled={cues.length === 0}
        >
          <Download className="size-4" />
          Subtitles (.vtt)
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/video-search">
            <Sparkles className="size-4" />
            Search videos by meaning
          </Link>
        </Button>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="bg-card space-y-4 rounded-xl border p-4 shadow-sm">
          {mediaUrl ? (
            isVideo ? (
              <video
                ref={media}
                src={mediaUrl}
                controls
                playsInline
                preload="metadata"
                className="aspect-video w-full rounded-lg bg-black"
                onTimeUpdate={(event) =>
                  setTime(event.currentTarget.currentTime)
                }
                aria-label="The recording, with the subtitles on"
              />
            ) : (
              <div className="space-y-2">
                <audio
                  ref={media}
                  src={mediaUrl}
                  controls
                  className="w-full"
                  onTimeUpdate={(event) =>
                    setTime(event.currentTarget.currentTime)
                  }
                  aria-label="The recording"
                />
                <p
                  aria-live="off"
                  className="bg-muted/50 flex min-h-14 items-center justify-center rounded-lg px-3 py-2 text-center text-sm"
                >
                  {playing >= 0 ? (
                    cues[playing].text
                  ) : (
                    <span className="text-muted-foreground">
                      The subtitle being played appears here.
                    </span>
                  )}
                </p>
              </div>
            )
          ) : (
            <p className="text-muted-foreground text-sm">
              The recording is not available to play.
            </p>
          )}

          <div className="grid grid-cols-3 gap-2">
            <Stat label="Subtitles" value={String(stats.count)} />
            <Stat label="Words" value={String(stats.words)} />
            <Stat
              label={`Over ${FAST_READING} chars/s`}
              value={String(stats.fast)}
            />
          </div>

          <div className="space-y-2">
            <Label>Subtitle length</Label>
            <div
              role="radiogroup"
              aria-label="Subtitle length"
              className="grid grid-cols-2 gap-2"
            >
              {LENGTHS.map((entry) => (
                <button
                  key={entry.value}
                  type="button"
                  role="radio"
                  aria-checked={maxChars === entry.value}
                  disabled={!hasWords && entry.value > 0}
                  onClick={() => changeLength(entry.value)}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50",
                    maxChars === entry.value
                      ? "border-primary bg-primary/10 text-primary font-medium"
                      : "hover:border-primary/40",
                  )}
                >
                  {entry.label}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground text-xs">
              {hasWords
                ? length.hint
                : "This transcript has no word times, so its subtitles cannot be regrouped."}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="shift">Shift all times (seconds)</Label>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setOffset((v) => Math.round((v - 0.5) * 10) / 10)
                }
              >
                −0.5
              </Button>
              <Input
                id="shift"
                type="number"
                step="0.1"
                value={offset}
                onChange={(e) => setOffset(Number(e.target.value) || 0)}
                className="w-24"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setOffset((v) => Math.round((v + 0.5) * 10) / 10)
                }
              >
                +0.5
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              Use it when the subtitles come a little early or late.
            </p>
          </div>

          {hasSpeakers && (
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-0.5">
                <Label htmlFor="with-speakers">
                  Speaker names in the subtitles
                </Label>
                <p className="text-muted-foreground text-xs">
                  Put “Speaker 1” in front of each subtitle, on the video and in
                  the files.
                </p>
              </div>
              <Switch
                id="with-speakers"
                checked={withSpeakers}
                onCheckedChange={setWithSpeakers}
              />
            </div>
          )}

          {(edited || offset !== 0) && (
            <Button variant="outline" size="sm" onClick={reset}>
              <RotateCcw className="size-4" />
              Undo corrections and shift
            </Button>
          )}
        </div>

        <div className="bg-card rounded-xl border p-4 shadow-sm">
          <Tabs defaultValue="subtitles">
            <TabsList>
              <TabsTrigger value="subtitles">Subtitles</TabsTrigger>
              <TabsTrigger value="transcript">Transcript</TabsTrigger>
              <TabsTrigger value="srt">SRT</TabsTrigger>
              <TabsTrigger value="vtt">VTT</TabsTrigger>
            </TabsList>

            <TabsContent value="subtitles" className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative min-w-48 flex-1">
                  <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
                  <Input
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setHit(0);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        jumpToHit(
                          e.shiftKey ? hit - 1 : hit + (hits.length ? 1 : 0),
                        );
                      }
                    }}
                    placeholder="Search the subtitles"
                    aria-label="Search the subtitles"
                    className="pl-8"
                  />
                </div>
                {query.trim() !== "" && (
                  <>
                    <span className="text-muted-foreground text-xs">
                      {hits.length === 0
                        ? "No match"
                        : `${Math.min(hit + 1, hits.length)} of ${hits.length}`}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={hits.length === 0}
                      onClick={() => jumpToHit(hit + 1)}
                    >
                      <ChevronDown className="size-4" />
                      Next
                    </Button>
                  </>
                )}
                <label className="text-muted-foreground flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={follow}
                    onChange={(e) => setFollow(e.target.checked)}
                    className="accent-primary size-4"
                  />
                  Follow the playback
                </label>
              </div>

              <ol
                ref={list}
                className="relative max-h-[32rem] space-y-1 overflow-y-auto rounded-lg border p-1"
              >
                {cues.map((cue, index) => {
                  const fast = isFast(cue);
                  const isHit = hits.includes(index);
                  return (
                    <li
                      key={`${maxChars}-${index}`}
                      data-index={index}
                      className={cn(
                        "flex items-start gap-2 rounded-md p-1.5",
                        index === playing && "bg-primary/10",
                        isHit && index !== playing && "bg-amber-100",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => seek(cue.start)}
                        className="text-muted-foreground hover:text-primary w-14 shrink-0 pt-1.5 text-right font-mono text-xs"
                        title="Play from here"
                      >
                        {clock(cue.start)}
                      </button>
                      {cue.speaker && (
                        <span
                          className={cn(
                            "mt-1.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium",
                            SPEAKER_COLORS[
                              (speakerIndex.get(cue.speaker) ?? 0) %
                                SPEAKER_COLORS.length
                            ],
                          )}
                        >
                          {cue.speaker}
                        </span>
                      )}
                      <textarea
                        value={cue.text}
                        rows={1}
                        aria-label={`Subtitle ${index + 1}, at ${clock(cue.start)}`}
                        onChange={(e) =>
                          setEdits((previous) => ({
                            ...previous,
                            [index]: e.target.value,
                          }))
                        }
                        className="hover:border-input focus:border-ring [field-sizing:content] min-w-0 flex-1 resize-none rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm focus:outline-none"
                      />
                      {fast && (
                        <span
                          title={`More than ${FAST_READING} characters each second: hard to read in time. Make it shorter, or let it stay longer.`}
                          className="mt-1.5 shrink-0 text-amber-600"
                        >
                          <AlertTriangle className="size-4" />
                          <span className="sr-only">Read too fast</span>
                        </span>
                      )}
                    </li>
                  );
                })}
                {cues.length === 0 && (
                  <li className="text-muted-foreground p-3 text-sm">
                    No subtitles: the recording has no speech that could be
                    read.
                  </li>
                )}
              </ol>
              <p className="text-muted-foreground text-xs">
                Click a time to play from there. Click a subtitle to correct its
                text.{" "}
                <Badge variant="outline" className="font-normal">
                  <AlertTriangle className="size-3 text-amber-600" /> too fast
                </Badge>{" "}
                marks a subtitle shown for too short a time to read.
              </p>
            </TabsContent>

            {(
              [
                ["transcript", text, "text"],
                ["srt", srt, "SRT"],
                ["vtt", vtt, "VTT"],
              ] as const
            ).map(([value, content, label]) => (
              <TabsContent key={value} value={value} className="mt-3 space-y-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void copy(value, content)}
                >
                  {copied === value ? (
                    <Check className="size-4" />
                  ) : (
                    <Copy className="size-4" />
                  )}
                  Copy the {label}
                </Button>
                <pre className="bg-muted/40 max-h-[32rem] overflow-auto rounded-lg border p-3 font-mono text-xs break-words whitespace-pre-wrap">
                  {content || "Nothing to show."}
                </pre>
              </TabsContent>
            ))}
          </Tabs>
        </div>
      </div>
    </div>
  );
}
