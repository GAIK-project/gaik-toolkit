"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream } from "@/lib/sse";
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
  settingsForSpec,
  type SpecSettings,
  staleAfterEdit,
  staleAfterStage,
  staleHint,
  stageReady,
  DOCX_PATH,
} from "@/lib/report-writer/workspace";
import { strToU8, zipSync } from "fflate";
import { createContext, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  type SectionRow,
  effectiveId,
} from "../report-writer/components/section-editor";
import { downloadBlob } from "./components/artifact-browser";
import type { SampleRow, SourceRow } from "./components/source-list";

export interface ExampleFile {
  name: string;
  source_class: "primary" | "secondary";
  size: number;
}

export interface ExampleInfo {
  id: string;
  title: string;
  description: string;
  files?: ExampleFile[];
  sample_report?: { name: string; size: number } | null;
}

interface StageResult {
  stage: string;
  artifacts: unknown;
  docx_b64: string | null;
  usage: Record<string, number>;
}

export const API = "/api/report-writer-v2";

export const STAGE_LABELS: Record<Stage, string> = {
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

const NO_MODELS = Object.fromEntries(
  MODEL_KEYS.map((k) => [k, null]),
) as Record<ModelKey, string | null>;

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function getOk(url: string): Promise<Response> {
  const res = await fetch(url);
  if (!res.ok)
    throw new Error(`GET ${url} failed (${res.status}): ${await res.text()}`);
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

/** All the state and actions of the Report Writer: the spec, the workspace and the runs. */
export function useReportWriter() {
  // Spec
  const [examples, setExamples] = useState<ExampleInfo[]>([]);
  const [exampleId, setExampleId] = useState("");
  /** The example whose spec and files are loaded into the form. */
  const [loadedExampleId, setLoadedExampleId] = useState<string | null>(null);
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
  const [usage, setUsage] = useState<
    Partial<Record<Stage, Record<string, number>>>
  >({});

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
        // ?example=<id> opens an example, e.g. from the Construction Report Writing use case.
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

  function buildSpec(): Omit<ReportSpec, "settings"> & {
    settings: SpecSettings;
  } {
    return {
      title,
      description,
      language,
      sections: sections.map((s) => ({
        id: effectiveId(s),
        title: s.title,
        instructions: s.instructions,
        required_items: (s.required_items ?? [])
          .map((x) => x.trim())
          .filter(Boolean),
        depends_on: s.depends_on,
      })),
      instructions,
      sources: {
        primary: sources
          .filter((r) => r.sourceClass === "primary")
          .map((r) => r.name),
        secondary: sources
          .filter((r) => r.sourceClass === "secondary")
          .map((r) => r.name),
      },
      sample_report: sample?.name ?? null,
      models,
      settings: settingsForSpec(settings),
    };
  }

  /** Apply a spec; files it names are taken from `files` when present. */
  function applySpec(spec: ReportSpec, files: Record<string, File>) {
    setTitle(spec.title);
    setDescription(spec.description);
    setLanguage(spec.language);
    setSections(
      spec.sections.map((s, i) => ({ key: `spec-${i}-${Date.now()}`, ...s })),
    );
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
      !window.confirm(
        "Clearing the form also clears the current workspace. Continue?",
      )
    )
      return;
    setExampleId("");
    setLoadedExampleId(null);
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
      !window.confirm(
        "Loading an example clears the current workspace. Continue?",
      )
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
      setLoadedExampleId(ex.id);
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
    for (const r of rows)
      entries[r.name] = new Uint8Array(await r.file!.arrayBuffer());
    downloadBlob(
      new Uint8Array(zipSync(entries)),
      `${exampleId || "report_spec"}.zip`,
      "application/zip",
    );
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
  const hints = [
    ...new Set(paths.map((p) => staleHint(stale, p)).filter(Boolean)),
  ];

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

    const response = await apiFetch(`${API}/run`, {
      method: "POST",
      body: form,
      signal,
    });
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
      if (stage !== "rebuild")
        setUsage((u) => ({ ...u, [stage]: result.usage }));
      setStale((s) => staleAfterStage(s, stage));
    }
    if (errors.length) throw new Error(errors.join("\n"));
    if (!result)
      throw new Error(`${STAGE_LABELS[stage]} ended without a result.`);
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
      for (const stage of stages)
        ws = await runStage(stage, ws, controller.signal);
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

  return {
    // spec
    examples,
    exampleId,
    setExampleId,
    loadedExampleId,
    loadingExample,
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
    models,
    setModels,
    settings,
    setSettings,
    sources,
    setSources,
    sample,
    setSample,
    specInputRef,
    // workspace
    artifacts,
    docx,
    stale,
    usage,
    paths,
    hints,
    ready,
    // runs
    running,
    busy,
    progress,
    error,
    abortRef,
    // actions
    buildSpec,
    loadExample,
    uploadSpec,
    downloadAllZip,
    clearAll,
    run,
    saveArtifact,
  };
}

/** Gives the sections of the page the one Report Writer that the page owns. */
export const ReportWriterContext = createContext<ReturnType<
  typeof useReportWriter
> | null>(null);
