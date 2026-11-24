"use client";

import { Openai } from "@/components/ui/svgs/openai";
import { cn } from "@/lib/utils";
import { AlertCircle, Loader2 } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { differingWords, wordCount, type EngineId } from "./transcriber-data";
import type { TranscribeResult } from "./transcript-view";

/** One model's run of the recording. */
export interface Run {
  key: string;
  /** Null when a CSC Aitta model transcribes instead. */
  engine: EngineId | null;
  label: string;
  where: string;
  status: "running" | "done" | "error";
  startedAt: number;
  /** From the press of Transcribe to the answer, in the browser. */
  ms?: number;
  result?: TranscribeResult;
  error?: string;
}

export function EngineLogo({
  engine,
  className,
}: {
  engine: EngineId | null;
  className?: string;
}) {
  if (engine === "openai")
    return (
      <Openai
        className={cn("size-5 shrink-0 dark:invert", className)}
        aria-hidden
      />
    );
  if (engine === null)
    return (
      <Image
        src="/logos/gaik-logo-letter-only.png"
        alt=""
        width={20}
        height={20}
        className={cn("size-5 shrink-0 object-contain", className)}
      />
    );
  return (
    <Image
      src="/logos/haaga-helia.png"
      alt=""
      width={20}
      height={20}
      className={cn("size-5 shrink-0 object-contain", className)}
    />
  );
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Ticks once a second while a run is going, so its time counts up. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function MarkedText({
  text,
  marks,
}: {
  text: string;
  marks: boolean[] | null;
}) {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0)
    return <span className="text-muted-foreground">(no text)</span>;
  return (
    <>
      {words.map((word, index) => (
        <span key={index}>
          {index > 0 && " "}
          {marks?.[index] ? (
            <mark className="rounded-sm bg-amber-200/70 px-0.5 text-inherit">
              {word}
            </mark>
          ) : (
            word
          )}
        </span>
      ))}
    </>
  );
}

/**
 * The runs side by side, each in its own column, with the words that differ
 * from the first column's text marked. A column's button opens that result in
 * the full view below (player, speakers, corrections).
 */
export function CompareColumns({
  runs,
  openKey,
  onOpen,
}: {
  runs: Run[];
  openKey: string | null;
  onOpen: (key: string) => void;
}) {
  const now = useNow(runs.some((run) => run.status === "running"));
  const base = runs[0];
  const baseText =
    base.status === "done" ? (base.result?.raw_transcript ?? "") : null;
  const marks = useMemo(
    () =>
      runs.map((run, index) =>
        index === 0 || baseText === null || run.status !== "done"
          ? null
          : differingWords(baseText, run.result?.raw_transcript ?? ""),
      ),
    [runs, baseText],
  );
  const done = runs.filter((run) => run.status === "done" && run.ms);
  const fastest =
    done.length > 1
      ? done.reduce((a, b) => ((a.ms ?? 0) <= (b.ms ?? 0) ? a : b)).key
      : null;
  const tooLong = marks.some(
    (entry, index) =>
      index > 0 && entry === null && runs[index].status === "done" && baseText,
  );

  return (
    <section
      aria-label="Results side by side"
      className="bg-card overflow-hidden rounded-xl border"
    >
      <div
        className={cn(
          "grid divide-y md:divide-x md:divide-y-0",
          runs.length === 2 ? "md:grid-cols-2" : "md:grid-cols-3",
        )}
      >
        {runs.map((run, index) => {
          const text = run.result?.raw_transcript ?? "";
          return (
            <div key={run.key} className="flex min-w-0 flex-col">
              <header className="flex items-start gap-2.5 border-b px-4 py-3">
                <EngineLogo engine={run.engine} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{run.label}</p>
                  <p
                    key={run.status}
                    className="text-muted-foreground animate-in fade-in slide-in-from-bottom-1 flex items-center gap-1.5 text-xs tabular-nums duration-200 motion-reduce:animate-none"
                  >
                    {run.status === "running" && (
                      <>
                        <Loader2 className="size-3 animate-spin" aria-hidden />
                        {run.where} · {seconds(now - run.startedAt)}
                      </>
                    )}
                    {run.status === "done" && (
                      <>
                        {run.where} · {seconds(run.ms ?? 0)} · {wordCount(text)}{" "}
                        words
                        {fastest === run.key && (
                          <span className="text-primary font-medium">
                            fastest
                          </span>
                        )}
                      </>
                    )}
                    {run.status === "error" && (
                      <span className="text-destructive">Failed</span>
                    )}
                  </p>
                </div>
              </header>

              <div className="max-h-96 flex-1 overflow-y-auto px-4 py-3 text-sm leading-6">
                {run.status === "running" && (
                  <div className="space-y-2" aria-hidden>
                    {[92, 78, 85, 60].map((width) => (
                      <div
                        key={width}
                        className="bg-muted h-3 animate-pulse rounded"
                        style={{ width: `${width}%` }}
                      />
                    ))}
                  </div>
                )}
                {run.status === "error" && (
                  <p className="text-destructive flex gap-2">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    {run.error}
                  </p>
                )}
                {run.status === "done" && (
                  <div className="animate-in fade-in slide-in-from-bottom-2 duration-300 motion-reduce:animate-none">
                    {run.result?.used_fallback && (
                      <p className="mb-2 text-xs text-amber-700">
                        The HH server could not be reached, so OpenAI wrote
                        this.
                      </p>
                    )}
                    <MarkedText text={text} marks={marks[index]} />
                  </div>
                )}
              </div>

              {run.status === "done" && (
                <div className="border-t px-4 py-2">
                  <button
                    type="button"
                    onClick={() => onOpen(run.key)}
                    aria-pressed={openKey === run.key}
                    className={cn(
                      "rounded-md px-2 py-1 text-xs font-medium transition-[color,background-color,transform] active:scale-[0.97]",
                      openKey === run.key
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {openKey === run.key
                      ? "Shown below"
                      : "Open with the player"}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {base.status === "done" && runs.length > 1 && (
        <p className="text-muted-foreground border-t px-4 py-2 text-xs">
          {tooLong
            ? "The texts are too long to mark where they differ."
            : `Words that differ from ${base.label} are marked.`}
        </p>
      )}
    </section>
  );
}
