"use client";

import { Badge } from "@/components/ui/badge";
import { Openai } from "@/components/ui/svgs/openai";
import { GitHubIcon } from "@/components/github-icon";
import { cn } from "@/lib/utils";
import Image from "next/image";
import { useState } from "react";
import {
  DIALECT_AVERAGES,
  DIALECT_CLIPS,
  DIALECT_LINKS,
  DIALECT_MODELS,
  clipAudio,
  clipWer,
  type Maker,
} from "./dialect-data";

export function MakerLogo({
  maker,
  className,
}: {
  maker: Maker;
  className?: string;
}) {
  const size = cn("size-5 shrink-0", className);
  if (maker === "openai")
    return <Openai className={cn(size, "dark:invert")} aria-hidden />;
  const src = {
    gaik: "/logos/gaik-logo-letter-only.png",
    huggingface: "/icons/hugging-face.svg",
    google: "/icons/google.svg",
  }[maker];
  return (
    <Image
      src={src}
      alt=""
      width={20}
      height={20}
      className={cn(size, "object-contain")}
    />
  );
}

const EXTERNAL = { target: "_blank", rel: "noopener noreferrer" } as const;

const LINKS: { href: string; label: string; logo: "hf" | "github" }[] = [
  {
    href: DIALECT_LINKS.model,
    label: "The model on Hugging Face",
    logo: "hf",
  },
  {
    href: DIALECT_LINKS.organisation,
    label: "GAIK on Hugging Face",
    logo: "hf",
  },
  {
    href: DIALECT_LINKS.source,
    label: "Training and evaluations",
    logo: "github",
  },
  {
    href: DIALECT_LINKS.toolkitDocs,
    label: "The evaluation in the toolkit",
    logo: "github",
  },
];

const BY_WER = [...DIALECT_MODELS].sort(
  (a, b) => DIALECT_AVERAGES[a.id].wer - DIALECT_AVERAGES[b.id].wer,
);

/**
 * Six dialect clips and what five models wrote for each, then the word error
 * rate over all 600 test clips. Precomputed: nothing runs and nothing costs.
 */
export function DialectComparison() {
  const [clipId, setClipId] = useState(DIALECT_CLIPS[0].id);
  const clip =
    DIALECT_CLIPS.find((entry) => entry.id === clipId) ?? DIALECT_CLIPS[0];

  return (
    <section
      id="dialect-comparison"
      aria-labelledby="dialect-comparison-heading"
      className="scroll-mt-24 space-y-3"
    >
      <div className="space-y-1">
        <h2 id="dialect-comparison-heading" className="text-sm font-semibold">
          Finnish dialects: how the models compare
        </h2>
        <p className="text-muted-foreground max-w-3xl text-sm">
          Interview clips from municipalities that no model was trained on.
          Listen, then read what each model wrote. Words it got wrong or added
          are marked.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="bg-card overflow-hidden rounded-xl border">
          <div className="space-y-3 border-b p-4">
            <div
              role="radiogroup"
              aria-label="Dialect clip"
              className="flex flex-wrap gap-1.5"
            >
              {DIALECT_CLIPS.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  role="radio"
                  aria-checked={entry.id === clip.id}
                  onClick={() => setClipId(entry.id)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-sm transition-[color,background-color,border-color,transform] active:scale-[0.97]",
                    entry.id === clip.id
                      ? "border-primary bg-primary/10 text-primary font-medium"
                      : "hover:border-primary/40",
                  )}
                >
                  {entry.place}
                </button>
              ))}
            </div>
            <audio
              key={clip.id}
              src={clipAudio(clip)}
              controls
              preload="none"
              className="h-9 w-full"
              aria-label={`Listen to the clip from ${clip.place}`}
            />
            <div className="bg-muted/50 rounded-lg px-3 py-2">
              <p className="text-muted-foreground text-xs font-medium">
                Human transcript
              </p>
              <p className="text-sm leading-6">{clip.reference}</p>
              {clip.gloss && (
                <p className="text-muted-foreground mt-1 text-xs">
                  In English: {clip.gloss}
                </p>
              )}
            </div>
          </div>

          <div className="text-muted-foreground flex justify-between px-4 pt-3 text-xs">
            <span>Model</span>
            <span>Words wrong</span>
          </div>
          <ul
            key={clip.id}
            className="animate-in fade-in slide-in-from-bottom-1 divide-y duration-300 motion-reduce:animate-none"
          >
            {DIALECT_MODELS.map((model) => {
              const result = clip.results[model.id];
              return (
                <li
                  key={model.id}
                  className={cn(
                    "grid grid-cols-[1.25rem_minmax(0,1fr)_auto] items-start gap-x-3 gap-y-1 px-4 py-3",
                    model.ours && "bg-primary/5",
                  )}
                >
                  <MakerLogo maker={model.maker} className="mt-0.5" />
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-x-2 text-sm font-medium">
                      {model.name}
                      {model.ours && (
                        <Badge variant="outline" className="font-normal">
                          Coming soon
                        </Badge>
                      )}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {model.note}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "text-sm font-semibold tabular-nums",
                      model.ours && "text-primary",
                    )}
                  >
                    {clipWer(result)} %
                  </span>
                  <p className="col-span-2 col-start-2 text-sm leading-6 break-words">
                    {result.words.length === 0 ? (
                      <span className="text-muted-foreground">(no text)</span>
                    ) : (
                      result.words.map(([word, wrong], index) => (
                        <span key={index}>
                          {index > 0 && " "}
                          {wrong ? (
                            <mark className="text-destructive decoration-destructive/50 bg-transparent font-medium underline underline-offset-4">
                              {word}
                            </mark>
                          ) : (
                            word
                          )}
                        </span>
                      ))
                    )}
                  </p>
                </li>
              );
            })}
          </ul>
          <p className="text-muted-foreground border-t px-4 py-3 text-xs">
            Missing words count as wrong too.{" "}
            <a
              href={DIALECT_LINKS.moreClips}
              {...EXTERNAL}
              className="text-primary underline-offset-4 hover:underline"
            >
              More clips and models
            </a>
          </p>
        </div>

        <div className="space-y-4">
          <div className="bg-card rounded-xl border p-4">
            <h3 className="text-sm font-semibold">All 600 test clips</h3>
            <p className="text-muted-foreground text-xs">
              Share of words wrong, from 10 municipalities
            </p>
            <ul className="mt-3 space-y-2.5">
              {BY_WER.map((model) => {
                const wer = DIALECT_AVERAGES[model.id].wer;
                return (
                  <li key={model.id} className="space-y-1">
                    <div className="flex items-center gap-2 text-xs">
                      <MakerLogo maker={model.maker} className="size-3.5" />
                      <span
                        className={cn(
                          "min-w-0 flex-1 truncate",
                          model.ours && "font-medium",
                        )}
                        title={model.name}
                      >
                        {model.short ?? model.name}
                      </span>
                      <span
                        className={cn(
                          "font-semibold tabular-nums",
                          model.ours && "text-primary",
                        )}
                      >
                        {wer.toFixed(1)} %
                      </span>
                    </div>
                    <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                      <div
                        className={cn(
                          "h-full origin-left rounded-full transition-[width] duration-500",
                          model.ours ? "bg-primary" : "bg-muted-foreground/40",
                        )}
                        style={{ width: `${wer}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <ul className="space-y-1">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  {...EXTERNAL}
                  className="hover:bg-muted flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors"
                >
                  {link.logo === "hf" ? (
                    <MakerLogo maker="huggingface" className="size-4" />
                  ) : (
                    <GitHubIcon className="size-4" />
                  )}
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-muted-foreground text-xs">
        Audio and human transcripts: Suomen kielen näytteitä (SKN), Kotus, via{" "}
        <a
          href={DIALECT_LINKS.kielipankki}
          {...EXTERNAL}
          className="underline-offset-4 hover:underline"
        >
          Kielipankki
        </a>
        , CC BY 4.0, from the test split of{" "}
        <a
          href={DIALECT_LINKS.dataset}
          {...EXTERNAL}
          className="underline-offset-4 hover:underline"
        >
          GAIK-project/skn-finnish-dialects-asr
        </a>
        .
      </p>
    </section>
  );
}
