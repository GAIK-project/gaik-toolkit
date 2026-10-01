"use client";

import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Download,
  FileArchive,
  FileText,
  ListChecks,
  Loader2,
  Play,
  RotateCcw,
  Sparkles,
  Upload,
  Zap,
  FilePlus2,
  ScrollText,
} from "lucide-react";
import Link from "next/link";
import { SectionEditor } from "../report-writer/components/section-editor";
import { downloadBlob } from "./components/artifact-browser";
import { ReportResults } from "./components/report-results";
import { SettingsForm } from "./components/settings-form";
import { SourceList } from "./components/source-list";
import { StageStepper } from "./components/stage-stepper";
import type { useReportWriter } from "./use-report-writer";

type ReportWriter = ReturnType<typeof useReportWriter>;

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: ScrollText,
    title: "Define the report",
    text: "Give it a title, a language and the sections it should have. Or load the example and change it.",
  },
  {
    icon: FilePlus2,
    title: "Add your sources",
    text: "Add documents, spreadsheets, images or recordings. Mark each as primary (your own evidence) or secondary (background).",
  },
  {
    icon: ListChecks,
    title: "Set the rules",
    text: "Write the report instructions: which sources win a disagreement, how to cite, the tone. A sample report can set the layout.",
  },
  {
    icon: Play,
    title: "Run the stages",
    text: "Run all three, or one at a time. Between stages you can read and correct the files that were produced.",
  },
  {
    icon: FileText,
    title: "Review and download",
    text: "Read the report with the evidence behind every section, then download it as Word or Markdown.",
  },
];
const GUIDE_NOTES = [
  "Your files and the workspace live in this browser tab only. Reloading or closing it loses them, so download the .zip first. Files are 100 MB together at most.",
  "Each stage is also available on its own: Source Normalizer, Knowledge Curator and Knowledge Synthesis.",
];

/** Build a report from your own sources and template, with every stage open to editing. */
export function ReportWriterCreateSection({ rw }: { rw: ReportWriter }) {
  const {
    busy,
    examples,
    exampleId,
    setExampleId,
    loadExample,
    loadingExample,
    buildSpec,
    specInputRef,
    uploadSpec,
    clearAll,
    title,
    setTitle,
    description,
    setDescription,
    language,
    setLanguage,
    sections,
    setSections,
    instructions,
    setInstructions,
    sources,
    setSources,
    sample,
    setSample,
    downloadAllZip,
    models,
    setModels,
    settings,
    setSettings,
  } = rw;

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to test your own report"
        steps={GUIDE_STEPS}
        notes={GUIDE_NOTES}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* The report you define */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Use Case</CardTitle>
              <CardDescription>
                Start from an example or your own spec
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Select
                  value={exampleId}
                  onValueChange={setExampleId}
                  disabled={busy}
                >
                  <SelectTrigger className="h-8 flex-1 text-sm">
                    <SelectValue placeholder="Choose an example" />
                  </SelectTrigger>
                  <SelectContent>
                    {examples.map((ex) => (
                      <SelectItem key={ex.id} value={ex.id}>
                        {ex.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  onClick={() =>
                    loadExample(examples.find((e) => e.id === exampleId)!)
                  }
                  disabled={busy || loadingExample || !exampleId}
                >
                  {loadingExample ? (
                    <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Zap className="mr-2 h-3.5 w-3.5" />
                  )}
                  Load
                </Button>
              </div>
              {exampleId && (
                <p className="text-muted-foreground text-xs">
                  {examples.find((e) => e.id === exampleId)?.description}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    downloadBlob(
                      JSON.stringify(buildSpec(), null, 2),
                      "report_spec.json",
                      "application/json",
                    )
                  }
                >
                  <Download className="mr-2 h-3.5 w-3.5" />
                  Download spec
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => specInputRef.current?.click()}
                  disabled={busy}
                >
                  <Upload className="mr-2 h-3.5 w-3.5" />
                  Upload spec
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={clearAll}
                  disabled={busy}
                >
                  <RotateCcw className="mr-2 h-3.5 w-3.5" />
                  Clear
                </Button>
                <input
                  ref={specInputRef}
                  type="file"
                  accept=".json"
                  className="sr-only"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadSpec(f);
                    e.target.value = "";
                  }}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rw2-title">Report title</Label>
                <Input
                  id="rw2-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rw2-desc">Report description</Label>
                <Textarea
                  id="rw2-desc"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={busy}
                  className="min-h-[72px] resize-none text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rw2-lang">Language</Label>
                <Input
                  id="rw2-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={busy}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Sections</CardTitle>
              <CardDescription>
                Under Advanced, list the items a section must cover. A section
                that depends on others is derived: it is written from their
                drafts.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SectionEditor
                sections={sections}
                onChange={setSections}
                disabled={busy}
                withRequiredItems
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Report instructions</CardTitle>
              <CardDescription>
                Guidance that applies to every section
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                disabled={busy}
                className="min-h-[80px] resize-y text-sm"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-3">
              <div>
                <CardTitle className="text-base">Sources</CardTitle>
                <CardDescription>
                  Primary sources are the evidence; secondary sources give
                  background. Click the badge to switch.
                </CardDescription>
              </div>
              <Button size="sm" variant="outline" onClick={downloadAllZip}>
                <FileArchive className="mr-1 h-3.5 w-3.5" />
                Download all (.zip)
              </Button>
            </CardHeader>
            <CardContent>
              <SourceList
                sources={sources}
                onSourcesChange={setSources}
                sample={sample}
                onSampleChange={setSample}
                disabled={busy}
              />
            </CardContent>
          </Card>
        </div>

        {/* Running it and what comes out */}
        <div className="space-y-4">
          <HowItWorksCard description="What you define, what each stage does, and how to edit in between">
            <p>
              <strong>Purpose.</strong> Writes a report from mixed sources
              (documents, spreadsheets, images and recordings) that follows a
              template you define, so that every statement can be traced to a
              source. The work runs in three stages. Each stage saves its result
              as files in a <em>workspace</em>, so you can read and correct them
              before the next stage runs.
            </p>

            <p>
              <strong>What you define (the spec).</strong> Load an example, or
              fill in the cards on the left. You can also download the whole
              spec as JSON and upload it again later.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>
                <strong>Title, description and language.</strong> The title
                heads the report and the language is the language it is written
                in. The description is for people only and is never sent to a
                model.
              </li>
              <li>
                <strong>Sections.</strong> The template, in report order. Each
                has a title, instructions on what to write, and optional{" "}
                <em>required items</em>: things it must cover. A required item
                that no source covers becomes a <em>(missing: …)</em> marker in
                the report instead of a guess. At most 12 sections.
              </li>
              <li>
                <strong>Dependencies.</strong> A section that depends on others
                is <em>derived</em>. It is written only from the finished text
                of those sections, never from the sources, so use it for
                summaries and recommendations. A fact that none of its
                prerequisite sections mentions cannot appear in it. A section
                without dependencies is written from the sources.
              </li>
              <li>
                <strong>Report instructions.</strong> Rules for every section:
                which sources to trust when they disagree, how to cite, tone,
                and what to do with missing data.
              </li>
              <li>
                <strong>Sources.</strong> Each file is <em>primary</em> (your
                own first-hand evidence, such as site notes or recordings) or{" "}
                <em>secondary</em> (background, such as older reports). Click
                the label to switch it. It only matters through the report
                instructions: if they say primary outranks secondary, a conflict
                is decided that way.
              </li>
              <li>
                <strong>Sample report (optional).</strong> A finished report
                whose structure, length and tone the new one copies. It
                contributes no facts.
              </li>
            </ul>

            <p>
              <strong>Stage 1: Normalize.</strong> Converts every source and the
              sample report to Markdown text into <code>normalized/</code>. PDFs
              and Word files are parsed locally, spreadsheets become tables,
              recordings are transcribed and images are described by a vision
              model. A file that cannot be read fully, such as a scanned PDF or
              an unsupported type, stops the stage and is named in the error.
              Files are 100 MB together at most: compress long recordings first.
            </p>
            <p>
              <strong>Stage 2: Curate.</strong> For every section that is not
              derived, a model reads the normalized sources and collects{" "}
              <em>facts</em> into <code>knowledge/</code>: a short summary, the
              exact quote it came from, the file and a location such as a page
              or a sheet row. It also lists the required items no source covers
              and the conflicts between sources. Every quote is checked against
              its source; a section that fails is asked again once, and a fact
              whose quote is still not in the source is dropped (the progress
              log says so). Together the normalized texts may hold about 200,000
              characters.
            </p>
            <p>
              <strong>Stage 3: Synthesize.</strong> A writer drafts each section
              from its own facts only. A second model reviews the draft against
              the same facts and proposes small corrections, which are applied;{" "}
              <code>review_log.json</code> records them. Derived sections are
              written last, from the reviewed text of their prerequisites. The
              result is in <code>report/</code>: one file per section,{" "}
              <code>report.md</code> and, if switched on,{" "}
              <code>report.docx</code>. The report follows the order of your
              sections, not the writing order.
            </p>

            <p>
              <strong>Running.</strong> <em>Run all</em> does the three stages
              in turn. You can also run one stage at a time once its inputs
              exist, and cancel a run. Progress and the token usage of each
              stage are shown as it goes.
            </p>
            <p>
              <strong>Editing between stages.</strong> The Workspace card lists
              every file. The normalized texts can only be read.{" "}
              <strong>Knowledge files</strong> (JSON) and{" "}
              <strong>section texts</strong> can be edited. When a file is out
              of date because something before it changed, it is marked{" "}
              <em>stale</em> with the stage to rerun. Running a stage again
              replaces its files, so Synthesize asks before it overwrites your
              section edits. After editing section texts,{" "}
              <strong>Rebuild report</strong> rebuilds <code>report.md</code>{" "}
              and the .docx without calling a model.
            </p>

            <p>
              <strong>Settings.</strong> Under Settings you can choose, for each
              stage, the model (blank means the server default), the reasoning
              effort and the temperature, plus:
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>
                the language of the recordings (default: detected
                automatically);
              </li>
              <li>how many sections are curated in parallel;</li>
              <li>how many attempts the reviewer gets per section;</li>
              <li>
                <em>Strict review</em>: stop the run if a reviewer correction
                cannot be applied, instead of logging it;
              </li>
              <li>
                <em>Citations</em>: cite the source file and place of each fact,
                or write plain statements even if the instructions ask for
                citations;
              </li>
              <li>whether to build the .docx.</li>
            </ul>

            <p>
              <strong>Keeping your work.</strong> The workspace lives in this
              browser tab. Before you close it, download the workspace .zip (all
              stage files, in the Workspace card) and, if you changed the
              template, the spec. Each stage is also available on its own, to
              try in isolation:{" "}
              <Link href="/source-normalizer" className="underline">
                Source Normalizer
              </Link>
              ,{" "}
              <Link href="/knowledge-curator" className="underline">
                Knowledge Curator
              </Link>{" "}
              and{" "}
              <Link href="/knowledge-synthesis" className="underline">
                Knowledge Synthesis
              </Link>
              .
            </p>
          </HowItWorksCard>
          <Card>
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="settings" className="border-none">
                <AccordionTrigger className="text-muted-foreground hover:text-foreground px-6 py-4 text-left text-sm font-medium hover:no-underline">
                  <div>
                    Settings
                    <p className="text-muted-foreground mt-1 text-sm font-normal">
                      Models and options per stage, saved in the spec
                    </p>
                  </div>
                </AccordionTrigger>
                <AccordionContent className="px-6 pb-5">
                  <SettingsForm
                    models={models}
                    onModelsChange={setModels}
                    settings={settings}
                    onSettingsChange={setSettings}
                    disabled={busy}
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </Card>

          <StageStepper
            artifacts={rw.artifacts}
            stale={rw.stale}
            running={rw.running}
            ready={rw.ready}
            progress={rw.progress}
            error={rw.error}
            onRun={rw.run}
            onCancel={() => rw.abortRef.current?.abort()}
            stacked
            runAllHint="Add at least one source file, and a file for every source listed, to run the stages."
          />
          <ReportResults
            rw={rw}
            emptyText="Add your sources and press Run all three stages. The report and the evidence behind it appear here."
          />
        </div>
      </div>
    </div>
  );
}
