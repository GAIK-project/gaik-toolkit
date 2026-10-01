"use client";

import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { FileSearch, FileText, Play, ScrollText, Wand2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { ExampleOverview } from "./components/example-overview";
import { ReportResults } from "./components/report-results";
import { StageStepper } from "./components/stage-stepper";
import type { useReportWriter } from "./use-report-writer";

type ReportWriter = ReturnType<typeof useReportWriter>;

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: FileSearch,
    title: "Look at the sources",
    text: "Play the three site recordings and open the customer documents. This is all the report is written from.",
  },
  {
    icon: ScrollText,
    title: "See the plan",
    text: "The report has seven sections. Each one lists what it must cover, and the last ones are written from the others.",
  },
  {
    icon: Play,
    title: "Write the report",
    text: "Press Run all three stages. Recordings are transcribed, facts are collected with quotes, and the sections are written and reviewed.",
  },
  {
    icon: FileText,
    title: "Check the evidence",
    text: "Read the report, then open any section to see the quoted facts, their sources, the conflicts and what is missing. Download the Word file.",
  },
];
const GUIDE_NOTES = [
  "The example is fictional: a 1970s timber-frame house, three recordings from a site visit and five customer documents. Running it uses AI models and takes about two minutes: it transcribes the recordings, collects the facts and writes seven sections.",
];

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
      <SectionGuide
        heading="How to try the example"
        steps={GUIDE_STEPS}
        notes={GUIDE_NOTES}
      />

      <ExampleOverview rw={rw} />

      <StageStepper
        artifacts={rw.artifacts}
        stale={rw.stale}
        running={rw.running}
        ready={rw.ready}
        progress={rw.progress}
        error={rw.error}
        onRun={rw.run}
        onCancel={() => rw.abortRef.current?.abort()}
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
