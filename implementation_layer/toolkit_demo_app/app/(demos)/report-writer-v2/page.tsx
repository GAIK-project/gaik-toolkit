"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream } from "@/lib/sse";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { EmptyStateCard } from "@/components/demo/result-card";
import { PageTransition } from "@/components/demo/page-transition";
import { FeedbackButton } from "@/components/feedback";
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
import { Alert, AlertDescription } from "@/components/ui/alert";
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
  DEFAULT_SETTINGS,
  FRESH,
  MODEL_KEYS,
  STAGES,
  type ModelKey,
  type ReportSpec,
  type Stage,
  type Staleness,
  parseArtifacts,
  parseSpec,
  staleAfterEdit,
  staleAfterStage,
  staleHint,
  stageReady,
  DOCX_PATH,
} from "@/lib/report-writer/workspace";
import { strToU8, zipSync } from "fflate";
import {
  AlertTriangle,
  Download,
  FileArchive,
  FilePen,
  Loader2,
  RotateCcw,
  Sparkles,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

import {
  SectionEditor,
  type SectionRow,
  effectiveId,
} from "../report-writer/components/section-editor";
import { ProgressStream } from "../report-writer/components/progress-stream";
import { ArtifactBrowser, downloadBlob } from "./components/artifact-browser";
import { FinalReportCard } from "./components/final-report-card";
import { SettingsForm } from "./components/settings-form";
import { SourceList, type SampleRow, type SourceRow } from "./components/source-list";

interface ExampleInfo {
  id: string;
  title: string;
  description: string;
}

interface StageResult {
  stage: string;
  artifacts: unknown;
  docx_b64: string | null;
  usage: Record<string, number>;
}

const API = "/api/report-writer-v2";

const STAGE_LABELS: Record<Stage, string> = {
  normalize: "1. Normalize",
  curate: "2. Curate",
  synthesize: "3. Synthesize",
  rebuild: "Rebuild report",
};

const DEFAULT_SECTIONS: SectionRow[] = [
  {
    key: "s1",
    id: "",
    title: "Findings",
    instructions: "Describe the key findings drawn from the evidence.",
    depends_on: [],
    required_items: [],
  },
];

const NO_MODELS = Object.fromEntries(MODEL_KEYS.map((k) => [k, null])) as Record<
  ModelKey,
  string | null
>;

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function getOk(url: string): Promise<Response> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} failed (${res.status}): ${await res.text()}`);
  return res;
}

async function httpError(res: Response): Promise<Error> {
  const text = await res.text();
  let detail: unknown = text;
  try {
    const body = JSON.parse(text);
    detail = body.error ?? body.detail ?? text;
  } catch {
    // Not JSON: show the raw body.
  }
  return new Error(
    `Run failed (${res.status}): ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
  );
}

export default function ReportWriterV2Page() {
  // Spec
  const [examples, setExamples] = useState<ExampleInfo[]>([]);
  const [exampleId, setExampleId] = useState("");
  const [loadingExample, setLoadingExample] = useState(false);
  const [title, setTitle] = useState("My Report");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("English");
  const [sections, setSections] = useState<SectionRow[]>(DEFAULT_SECTIONS);
  const [instructions, setInstructions] = useState("");
  const [models, setModels] = useState(NO_MODELS);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [sample, setSample] = useState<SampleRow | null>(null);
  const specInputRef = useRef<HTMLInputElement>(null);

  // Workspace
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [docx, setDocx] = useState<Uint8Array<ArrayBuffer> | null>(null);
  const [stale, setStale] = useState<Staleness>(FRESH);
  const [usage, setUsage] = useState<Partial<Record<Stage, Record<string, number>>>>({});

  // Runs
  const [running, setRunning] = useState<Stage | null>(null);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    getOk(`${API}/examples`)
      .then((r) => r.json())
      .then((data) => {
        if (!Array.isArray(data?.examples))
          throw new Error("The examples response has no examples list.");
        setExamples(data.examples);
        // ?example=<id> opens an example, e.g. from the Condition Assessment use case.
        const id = new URLSearchParams(window.location.search).get("example");
        if (!id) return;
        const ex = (data.examples as ExampleInfo[]).find((e) => e.id === id);
        if (!ex) throw new Error(`Unknown example "${id}" in the URL.`);
        setExampleId(id);
        return loadExample(ex);
      })
      .catch((e) => toast.error(`Loading examples failed: ${message(e)}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on mount; the URL example loads once
  }, []);

  // -- Spec --

  function buildSpec(): ReportSpec {
    return {
      title,
      description,
      language,
      sections: sections.map((s) => ({
        id: effectiveId(s),
        title: s.title,
        instructions: s.instructions,
        required_items: (s.required_items ?? []).map((x) => x.trim()).filter(Boolean),
        depends_on: s.depends_on,
      })),
      instructions,
      sources: {
        primary: sources.filter((r) => r.sourceClass === "primary").map((r) => r.name),
        secondary: sources.filter((r) => r.sourceClass === "secondary").map((r) => r.name),
      },
      sample_report: sample?.name ?? null,
      models,
      settings,
    };
  }

  /** Apply a spec; files it names are taken from `files` when present. */
  function applySpec(spec: ReportSpec, files: Record<string, File>) {
    setTitle(spec.title);
    setDescription(spec.description);
    setLanguage(spec.language);
    setSections(spec.sections.map((s, i) => ({ key: `spec-${i}-${Date.now()}`, ...s })));
    setInstructions(spec.instructions);
    setModels(spec.models);
    setSettings(spec.settings);
    setSources(
      (["primary", "secondary"] as const).flatMap((sourceClass) =>
        spec.sources[sourceClass].map((name) => ({
          name,
          sourceClass,
          file: files[name] ?? null,
        })),
      ),
    );
    setSample(
      spec.sample_report
        ? { name: spec.sample_report, file: files[spec.sample_report] ?? null }
        : null,
    );
  }

  function resetWorkspace() {
    setArtifacts({});
    setDocx(null);
    setStale(FRESH);
    setUsage({});
    setProgress([]);
    setError(null);
  }

  /** Reset the page to its state on load. */
  function clearAll() {
    if (
      Object.keys(artifacts).length > 0 &&
      !window.confirm("Clearing the form also clears the current workspace. Continue?")
    )
      return;
    setExampleId("");
    setTitle("My Report");
    setDescription("");
    setLanguage("English");
    setSections(DEFAULT_SECTIONS);
    setInstructions("");
    setModels(NO_MODELS);
    setSettings(DEFAULT_SETTINGS);
    setSources([]);
    setSample(null);
    resetWorkspace();
  }

  async function loadExample(ex: ExampleInfo) {
    if (
      Object.keys(artifacts).length > 0 &&
      !window.confirm("Loading an example clears the current workspace. Continue?")
    )
      return;
    setLoadingExample(true);
    try {
      const base = `${API}/examples/${encodeURIComponent(ex.id)}`;
      const spec = parseSpec(await (await getOk(`${base}/spec`)).json());
      const names = [
        ...spec.sources.primary,
        ...spec.sources.secondary,
        ...(spec.sample_report ? [spec.sample_report] : []),
      ];
      const files = await Promise.all(
        names.map(async (name) => {
          const res = await getOk(`${base}/files/${encodeURIComponent(name)}`);
          return new File([await res.blob()], name);
        }),
      );
      applySpec(spec, Object.fromEntries(files.map((f) => [f.name, f])));
      resetWorkspace();
      toast.success(`Example loaded: ${ex.title}`);
    } catch (e) {
      toast.error(`Loading the example failed: ${message(e)}`);
    } finally {
      setLoadingExample(false);
    }
  }

  async function uploadSpec(file: File) {
    try {
      let json: unknown;
      try {
        json = JSON.parse(await file.text());
      } catch (e) {
        throw new Error(`${file.name} is not valid JSON: ${message(e)}`);
      }
      const spec = parseSpec(json);
      const rows = [...sources, ...(sample ? [sample] : [])];
      const have = Object.fromEntries(
        rows.filter((r) => r.file).map((r) => [r.name, r.file as File]),
      );
      applySpec(spec, have);
      toast.success("Spec loaded. Add any source files marked missing.");
    } catch (e) {
      toast.error(message(e), { duration: 8000 });
    }
  }

  async function downloadAllZip() {
    const rows = [...sources, ...(sample ? [sample] : [])];
    const missing = rows.filter((r) => !r.file).map((r) => r.name);
    if (missing.length) {
      toast.error(`Add the missing files first: ${missing.join(", ")}`);
      return;
    }
    const entries: Record<string, Uint8Array> = {
      "report_spec.json": strToU8(JSON.stringify(buildSpec(), null, 2)),
    };
    for (const r of rows) entries[r.name] = new Uint8Array(await r.file!.arrayBuffer());
    downloadBlob(new Uint8Array(zipSync(entries)), `${exampleId || "report_spec"}.zip`, "application/zip");
  }

  // -- Stages --

  const hasSample = sample !== null;
  const ready: Record<Stage, boolean> = {
    normalize:
      sources.length > 0 &&
      sources.every((r) => r.file) &&
      (!sample || sample.file !== null) &&
      sections.length > 0,
    curate: stageReady("curate", artifacts, hasSample),
    synthesize: stageReady("synthesize", artifacts, hasSample),
    rebuild: stageReady("rebuild", artifacts, hasSample),
  };
  const paths = [...Object.keys(artifacts), ...(docx ? [DOCX_PATH] : [])];
  const hints = [...new Set(paths.map((p) => staleHint(stale, p)).filter(Boolean))];

  /** Run one stage on the workspace `ws`; returns the new workspace or throws. */
  async function runStage(
    stage: Stage,
    ws: Record<string, string>,
    signal: AbortSignal,
  ): Promise<Record<string, string>> {
    setRunning(stage);
    setProgress((p) => [...p, `Phase ${STAGE_LABELS[stage]}`]);
    const form = new FormData();
    form.append("stage", stage);
    form.append("spec", JSON.stringify(buildSpec()));
    form.append("artifacts", JSON.stringify(ws));
    if (stage === "normalize") {
      // Spec order, as in buildSpec: the backend pairs uploads with spec names by position.
      for (const sourceClass of ["primary", "secondary"])
        for (const r of sources.filter((r) => r.sourceClass === sourceClass))
          form.append("files", r.file!, r.name);
      if (sample) form.append("sample_report", sample.file!, sample.name);
    }

    const response = await apiFetch(`${API}/run`, { method: "POST", body: form, signal });
    if (!response.ok) throw await httpError(response);

    const results: StageResult[] = [];
    const errors: string[] = [];
    await processSSEStream<StageResult>(response, {
      onResult: (data) => results.push(data),
      onError: (msg) => errors.push(msg),
      onCustomEvent: (event) => {
        if (event.type === "progress")
          setProgress((p) => [...p, String(event.data.message)]);
        else errors.push(`Unexpected "${event.type}" event from the backend.`);
      },
    });

    const result = results.at(-1);
    let next = ws;
    if (result) {
      if (result.stage !== stage)
        throw new Error(`Expected a ${stage} result, got "${result.stage}".`);
      next = parseArtifacts(result.artifacts);
      const builds = stage === "synthesize" || stage === "rebuild";
      if (builds && settings.docx && typeof result.docx_b64 !== "string")
        throw new Error(`The ${stage} result has no report.docx.`);
      if (!result.usage || typeof result.usage !== "object")
        throw new Error(`The ${stage} result has no usage.`);
      setArtifacts(next);
      if (builds)
        setDocx(
          result.docx_b64 === null
            ? null
            : Uint8Array.from(atob(result.docx_b64), (c) => c.charCodeAt(0)),
        );
      else if (!("report/report.md" in next)) setDocx(null); // the stage dropped the report
      if (stage !== "rebuild") setUsage((u) => ({ ...u, [stage]: result.usage }));
      setStale((s) => staleAfterStage(s, stage));
    }
    if (errors.length) throw new Error(errors.join("\n"));
    if (!result) throw new Error(`${STAGE_LABELS[stage]} ended without a result.`);
    return next;
  }

  async function run(stages: Stage[]) {
    if (running) return;
    if (
      stages.includes("synthesize") &&
      stale.editedSections &&
      !window.confirm(
        "Stage 3 rewrites every section and overwrites your section edits. Continue?",
      )
    )
      return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setProgress([]);
    let ws = artifacts;
    try {
      for (const stage of stages) ws = await runStage(stage, ws, controller.signal);
      if (stages.includes("synthesize") || stages.includes("rebuild"))
        toast.success("Report ready");
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (e instanceof RateLimitError) return; // apiFetch already showed a toast
      setError(message(e));
    } finally {
      setRunning(null);
    }
  }

  function saveArtifact(path: string, text: string) {
    setArtifacts((a) => ({ ...a, [path]: text }));
    setStale((s) => staleAfterEdit(s, path));
    toast.success(`Saved ${path}`);
  }

  const busy = running !== null;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FilePen}
        title="Report Writer"
        description="Write a report in stages: normalize the sources, curate facts per section, then synthesize and review. Inspect and edit every file in between."
        className="mb-6"
      >
        <p className="mt-1 text-xs text-muted-foreground">
          Note: The workspace lives in this browser tab. Reloading or closing
          the tab loses it, so download the .zip first.
        </p>
      </DemoPageHeader>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── LEFT COLUMN ── */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Use Case</CardTitle>
              <CardDescription>Start from an example or your own spec</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Select value={exampleId} onValueChange={setExampleId} disabled={busy}>
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
                  onClick={() => loadExample(examples.find((e) => e.id === exampleId)!)}
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
                <p className="text-xs text-muted-foreground">
                  {examples.find((e) => e.id === exampleId)?.description}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    downloadBlob(JSON.stringify(buildSpec(), null, 2), "report_spec.json", "application/json")
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
                <Button size="sm" variant="outline" onClick={clearAll} disabled={busy}>
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
              <CardDescription>Guidance that applies to every section</CardDescription>
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

        {/* ── RIGHT COLUMN ── */}
        <div className="space-y-4">
          <HowItWorksCard description="The three stages and the workspace">
            <p>
              <strong>1. Normalize</strong> parses every source (documents,
              spreadsheets, images, audio) and the sample report to text.
            </p>
            <p>
              <strong>2. Curate</strong> picks the facts each section needs from
              the normalized sources into <code>knowledge/</code>.
            </p>
            <p>
              <strong>3. Synthesize</strong> writes and reviews each section from
              its knowledge file, then assembles <code>report.md</code> and{" "}
              <code>report.docx</code>.
            </p>
            <p>
              Between stages you can edit the knowledge and section files. After
              editing sections, <strong>Rebuild report</strong> reassembles the
              report without calling a model.
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

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Stages</CardTitle>
              <CardDescription>
                Run all three stages, or one at a time once its inputs exist.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Button
                  size="lg"
                  className="flex-1"
                  onClick={() => run(["normalize", "curate", "synthesize"])}
                  disabled={busy || !ready.normalize}
                >
                  {busy ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  Run all
                </Button>
                {busy && (
                  <Button variant="outline" size="lg" onClick={() => abortRef.current?.abort()}>
                    <X className="mr-2 h-4 w-4" />
                    Cancel
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {STAGES.map((stage) => (
                  <Button
                    key={stage}
                    size="sm"
                    variant="outline"
                    onClick={() => run([stage])}
                    disabled={busy || !ready[stage]}
                  >
                    {running === stage && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {STAGE_LABELS[stage]}
                  </Button>
                ))}
              </div>
              {hints.length > 0 && (
                <p className="text-xs text-amber-600">Stale files: {hints.join(" · ")}</p>
              )}
            </CardContent>
          </Card>

          <FinalReportCard
            title={title}
            markdown={artifacts["report/report.md"]}
            docx={docx}
            sectionCount={Object.keys(artifacts).filter((p) => p.startsWith("report/sections/")).length}
            stale={stale}
            running={running}
            onRebuild={() => run(["rebuild"])}
          />

          {progress.length > 0 && (
            <ProgressStream messages={progress} isRunning={busy} className="w-full" />
          )}

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="whitespace-pre-wrap text-xs">{error}</AlertDescription>
            </Alert>
          )}

          {Object.keys(usage).length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Token usage</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs">
                {STAGES.filter((s) => usage[s]).map((s) => (
                  <p key={s}>
                    <span className="font-medium">{STAGE_LABELS[s]}:</span>{" "}
                    {Object.entries(usage[s]!)
                      .map(([k, v]) => `${k} ${v.toLocaleString()}`)
                      .join(" · ") || "no token counts reported"}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}

          {paths.length > 0 ? (
            <ArtifactBrowser
              artifacts={artifacts}
              docx={docx}
              stale={stale}
              disabled={busy}
              onSave={saveArtifact}
            />
          ) : (
            <EmptyStateCard
              icon={FilePen}
              title="No workspace yet"
              description="Load an example or add sources, then click Run all."
              feedbackSlot={<FeedbackButton demoType="report-writer-v2" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
