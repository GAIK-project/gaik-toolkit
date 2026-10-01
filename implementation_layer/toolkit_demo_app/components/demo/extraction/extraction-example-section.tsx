"use client";

import { SectionGuide } from "@/components/demo/section-guide";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { FileAudio, FileText, Loader2, Sparkles, Wand2 } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import type { ExtractionConfig } from "./config";
import { ExtractionResults } from "./extraction-results";
import { RunProgress } from "./run-progress";
import {
  useExtractionPipeline,
  type ExtractionInput,
} from "./use-extraction-pipeline";

/** Ready-made reports: pick one, see what is read from it, process it, explore the result. */
export function ExtractionExampleSection({
  config,
  onCreate,
}: {
  config: ExtractionConfig;
  onCreate: () => void;
}) {
  const [selectedId, setSelectedId] = useState(config.examples[0].id);
  const [loadingAudio, setLoadingAudio] = useState(false);
  const pipeline = useExtractionPipeline(config);
  const example =
    config.examples.find((item) => item.id === selectedId) ??
    config.examples[0];

  // One saved schema for all examples. The first run generates it and saves it; later
  // runs reuse it.
  const run = {
    prompt: config.examplePrompt,
    schemaKey: config.exampleSchemaKey,
    enhanced: config.enhancedDefault,
    generatePdf: true,
  };

  const process = async () => {
    let input: ExtractionInput;
    if (example.kind === "text") {
      input = { kind: "text", text: example.text ?? "" };
    } else {
      setLoadingAudio(true);
      try {
        const response = await fetch(example.audioUrl ?? "");
        if (!response.ok) throw new Error("Could not load the example audio");
        const blob = await response.blob();
        input = {
          kind: "audio",
          file: new File(
            [blob],
            example.audioUrl?.split("/").pop() ?? "audio",
            {
              type: blob.type || "audio/mp4",
            },
          ),
        };
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed");
        return;
      } finally {
        setLoadingAudio(false);
      }
    }
    await pipeline.run(input, run);
  };

  const busy = pipeline.isLoading || loadingAudio;

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to try the example"
        steps={config.exampleGuide.steps}
        notes={config.exampleGuide.notes}
      />

      <Card>
        <CardContent className="space-y-6 pt-6">
          <CardDescription>{config.exampleGuide.intro}</CardDescription>

          <div
            role="radiogroup"
            aria-label="Example report"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {config.examples.map((item) => {
              const Icon = item.kind === "audio" ? FileAudio : FileText;
              const selected = item.id === selectedId;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={busy}
                  onClick={() => {
                    setSelectedId(item.id);
                    pipeline.reset();
                  }}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border-2 p-4 text-left transition-all",
                    selected
                      ? "border-primary bg-primary/5"
                      : "bg-card hover:border-primary/40",
                  )}
                >
                  <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                    <Icon className="size-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold">{item.title}</span>
                    <span className="text-muted-foreground block text-sm">
                      {item.summary}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">
                {example.kind === "audio" ? "The recording" : "The report"}
              </h3>
              {example.kind === "audio" ? (
                <audio
                  key={example.id}
                  controls
                  src={example.audioUrl}
                  className="w-full"
                />
              ) : (
                <pre className="bg-muted/30 max-h-72 overflow-auto rounded-lg border p-3 font-sans text-sm leading-6 whitespace-pre-wrap">
                  {example.text}
                </pre>
              )}
            </div>
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">Extracted by AI</h3>
              <div className="flex flex-wrap gap-1.5">
                {config.exampleFieldLabels.map((label) => (
                  <span
                    key={label}
                    className="bg-primary/10 text-primary rounded-md px-2 py-1 text-sm"
                  >
                    {label}
                  </span>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">
                {config.exampleFieldsHint}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 border-t pt-4">
            <Button size="lg" onClick={process} disabled={busy}>
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {busy ? "Processing..." : "Process the example"}
            </Button>
            <button
              type="button"
              onClick={onCreate}
              className="text-primary flex items-center gap-2 text-sm font-medium hover:underline"
            >
              <Wand2 className="size-4" />
              {config.createLinkText}
            </button>
          </div>
        </CardContent>
      </Card>

      {pipeline.isLoading && <RunProgress steps={pipeline.steps} />}
      {pipeline.result && !pipeline.isLoading && (
        <ExtractionResults
          config={config}
          result={pipeline.result}
          seconds={pipeline.seconds}
          busy={busy}
          onRerun={(text) => pipeline.run({ kind: "text", text }, run)}
        />
      )}
    </div>
  );
}
