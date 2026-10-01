"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Staleness, Stage } from "@/lib/report-writer/workspace";
import {
  AlertTriangle,
  Check,
  FileText,
  Layers,
  Loader2,
  Mic,
  PenLine,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { ProgressStream } from "../../report-writer/components/progress-stream";

type StageId = "normalize" | "curate" | "synthesize";

const STAGE_INFO: {
  id: StageId;
  title: string;
  text: string;
  folder: string;
  icon: LucideIcon;
}[] = [
  {
    id: "normalize",
    title: "1. Normalize",
    text: "Turns every source into text: documents are parsed, tables read, images described and recordings transcribed.",
    folder: "normalized/",
    icon: Mic,
  },
  {
    id: "curate",
    title: "2. Curate",
    text: "Collects facts for each section, each with the exact quote, the file and the place it came from. Flags missing items and conflicts.",
    folder: "knowledge/",
    icon: Layers,
  },
  {
    id: "synthesize",
    title: "3. Synthesize",
    text: "Writes each section from its own facts, has a second model review it, and builds the report.",
    folder: "report/sections/",
    icon: PenLine,
  },
];

function filesIn(artifacts: Record<string, string>, folder: string) {
  return Object.keys(artifacts).filter((path) => path.startsWith(folder))
    .length;
}

/** The three stages as a pipeline: what each does, where it stands, and how to run it. */
export function StageStepper({
  artifacts,
  stale,
  running,
  ready,
  progress,
  error,
  onRun,
  onCancel,
  runAllHint,
  stacked = false,
}: {
  artifacts: Record<string, string>;
  stale: Staleness;
  running: Stage | null;
  ready: Record<Stage, boolean>;
  progress: string[];
  error: string | null;
  onRun: (stages: Stage[]) => void;
  onCancel: () => void;
  /** Says what is missing, when Run all is not possible yet. */
  runAllHint?: string;
  /** One stage under the other, for a narrow column. */
  stacked?: boolean;
}) {
  const busy = running !== null;
  const status = (id: StageId) => {
    if (running === id) return "running" as const;
    const done = filesIn(
      artifacts,
      STAGE_INFO.find((s) => s.id === id)!.folder,
    );
    if (done === 0) return "todo" as const;
    if (id === "curate" && stale.knowledge) return "stale" as const;
    if (id === "synthesize" && stale.report) return "stale" as const;
    return "done" as const;
  };

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="text-base">Write the report</CardTitle>
        <div className="flex gap-2">
          <Button
            size="lg"
            onClick={() => onRun(["normalize", "curate", "synthesize"])}
            disabled={busy || !ready.normalize}
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            Run all three stages
          </Button>
          {busy && (
            <Button variant="outline" size="lg" onClick={onCancel}>
              <X className="size-4" />
              Cancel
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!ready.normalize && !busy && runAllHint && (
          <p className="text-muted-foreground text-sm">{runAllHint}</p>
        )}

        <ol className={cn("grid gap-3", !stacked && "md:grid-cols-3")}>
          {STAGE_INFO.map((stage, index) => {
            const state = status(stage.id);
            const count = filesIn(artifacts, stage.folder);
            return (
              <li
                key={stage.id}
                className={cn(
                  "bg-card relative flex flex-col gap-2 rounded-xl border p-4",
                  state === "running" &&
                    "border-primary ring-primary/20 ring-2",
                  state === "done" && "border-green-600/50",
                  state === "stale" && "border-amber-500/60",
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-full",
                      state === "done"
                        ? "bg-green-600 text-white"
                        : state === "running"
                          ? "bg-primary text-primary-foreground"
                          : "bg-primary/10 text-primary",
                    )}
                  >
                    {state === "done" ? (
                      <Check className="size-4" />
                    ) : state === "running" ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <stage.icon className="size-4" />
                    )}
                  </span>
                  <h4 className="font-semibold">{stage.title}</h4>
                  {index < STAGE_INFO.length - 1 && !stacked && (
                    <span className="text-muted-foreground ml-auto hidden text-lg md:block">
                      →
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground flex-1 text-sm leading-5">
                  {stage.text}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {state === "todo" && (
                    <Badge variant="outline" className="text-muted-foreground">
                      Not run yet
                    </Badge>
                  )}
                  {state === "running" && <Badge>Running…</Badge>}
                  {state === "done" && (
                    <Badge className="bg-green-600 text-white hover:bg-green-600">
                      Done · {count} {count === 1 ? "file" : "files"}
                    </Badge>
                  )}
                  {state === "stale" && (
                    <Badge
                      variant="outline"
                      className="border-amber-500 text-amber-700"
                    >
                      Out of date
                    </Badge>
                  )}
                  <Button
                    size="xs"
                    variant="outline"
                    className="ml-auto"
                    onClick={() => onRun([stage.id])}
                    disabled={busy || !ready[stage.id]}
                  >
                    {state === "todo" ? "Run" : "Run again"}
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>

        {stale.assembled && !busy && "report/report.md" in artifacts && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-amber-700">
            <FileText className="size-4" />
            You edited a section after the report was built.
            <Button
              size="xs"
              variant="outline"
              onClick={() => onRun(["rebuild"])}
            >
              Rebuild report
            </Button>
          </div>
        )}

        {progress.length > 0 && (
          <ProgressStream
            messages={progress}
            isRunning={busy}
            className="w-full"
          />
        )}

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertDescription className="text-xs whitespace-pre-wrap">
              {error}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
