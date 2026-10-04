"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { cn } from "@/lib/utils";
import {
  FileText,
  Gavel,
  ListChecks,
  Scale,
  ScrollText,
  Sparkles,
  Users,
} from "lucide-react";
import { useState } from "react";
import { HallucinationsTab } from "./hallucinations-tab";
import { PanelTab } from "./panel-tab";
import { TextPairTab } from "./text-pair-tab";
import { ValidatePdfTab } from "./validate-tab";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: ListChecks,
    title: "Pick a mode",
    text: "Four ways to check an extractor: compare two texts, find invented fields, validate against a PDF, or ask a panel of judges.",
  },
  {
    icon: Sparkles,
    title: "Start from a case",
    text: "Each mode has ready-made cases that say what a person would expect the judge to find.",
  },
  {
    icon: Gavel,
    title: "Run the judge",
    text: "A model reads the case and gives a verdict, a 1 to 5 score and the reason.",
  },
  {
    icon: Scale,
    title: "Read the verdict",
    text: "See whether it matches the expectation, which words or fields it is about, and what to correct.",
  },
];
const GUIDE_NOTES = [
  "A judge is a model that decides whether an extracted value is right. It handles paraphrases, word forms and date formats that an exact comparison calls wrong, but it can be wrong too: read the reason, not only the verdict.",
  "The score reads: 1 is clearly wrong, 2 to 3 is suspect and worth a look, 4 to 5 looks correct. Several judges together (the panel) show how sure the verdict is.",
];

type Mode = "text-pair" | "hallucinations" | "validate" | "panel";

const MODES: {
  id: Mode;
  title: string;
  icon: typeof Scale;
  summary: string;
  when: string;
}[] = [
  {
    id: "text-pair",
    title: "Text pair",
    icon: Scale,
    summary: "Two texts in, one verdict out.",
    when: "Use it when an extractor words values differently from the ground truth.",
  },
  {
    id: "hallucinations",
    title: "Hallucinations",
    icon: ScrollText,
    summary: "A source and a JSON object: which fields are invented?",
    when: "Use it when you have the source text and want to catch made-up values.",
  },
  {
    id: "validate",
    title: "Validate PDF",
    icon: FileText,
    summary:
      "A PDF and the extracted JSON: which fields do not match the page?",
    when: "Use it when the truth is on a page, in a table or a form.",
  },
  {
    id: "panel",
    title: "Panel",
    icon: Users,
    summary: "The same text pair, judged by several models.",
    when: "Use it when one judge is not enough and you want to see how sure they are.",
  },
];

export default function LlmJudgePage() {
  const [mode, setMode] = useState<Mode>("text-pair");

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Scale}
        title="LLM-as-Judge"
        description="Score extractor output, detect hallucinations, compare texts, and run a multi-model judge panel."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the LLM-as-Judge"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <div
          role="radiogroup"
          aria-label="Judge mode"
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        >
          {MODES.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="radio"
              aria-checked={mode === entry.id}
              onClick={() => setMode(entry.id)}
              className={cn(
                "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                mode === entry.id
                  ? "border-primary bg-primary/5"
                  : "bg-card hover:border-primary/40",
              )}
            >
              <span className="flex items-center gap-2 font-semibold">
                <entry.icon className="text-primary size-4" />
                {entry.title}
              </span>
              <span className="text-sm">{entry.summary}</span>
              <span className="text-muted-foreground text-xs">
                {entry.when}
              </span>
            </button>
          ))}
        </div>

        <div>
          {mode === "text-pair" && <TextPairTab />}
          {mode === "hallucinations" && <HallucinationsTab />}
          {mode === "validate" && <ValidatePdfTab />}
          {mode === "panel" && <PanelTab />}
        </div>
      </div>
    </PageTransition>
  );
}
