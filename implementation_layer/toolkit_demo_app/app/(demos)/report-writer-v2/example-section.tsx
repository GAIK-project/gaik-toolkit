"use client";

import { Wand2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { ExampleOverview } from "./components/example-overview";
import { ReportResults } from "./components/report-results";
import { StageStepper } from "./components/stage-stepper";
import type { useReportWriter } from "./use-report-writer";

type ReportWriter = ReturnType<typeof useReportWriter>;

/** The ready-made construction report: look at its sources, run it, check the evidence. */
export function ReportWriterExampleSection({
  rw,
  onCreate,
}: {
  rw: ReportWriter;
  onCreate: () => void;
}) {
  const { examples, loadedExampleId, loadExample } = rw;

  // Load the first example once, as soon as the list is there.
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || examples.length === 0 || loadedExampleId) return;
    asked.current = true;
    void loadExample(examples[0]);
  }, [examples, loadedExampleId, loadExample]);

  return (
    <div className="space-y-6">
      <ExampleOverview rw={rw} />

      <p className="text-muted-foreground text-sm">
        Running the example uses AI models and takes about two minutes.
      </p>
      <StageStepper
        artifacts={rw.artifacts}
        stale={rw.stale}
        running={rw.running}
        ready={rw.ready}
        progress={rw.progress}
        error={rw.error}
        onRun={rw.run}
        onStop={rw.stop}
        runAllHint="The example is loading."
      />

      <ReportResults rw={rw} />

      <button
        type="button"
        onClick={onCreate}
        className="text-primary flex items-center gap-2 text-sm font-medium hover:underline"
      >
        <Wand2 className="size-4" />
        Want your own sources, sections and rules? Test on your own data
      </button>
    </div>
  );
}
