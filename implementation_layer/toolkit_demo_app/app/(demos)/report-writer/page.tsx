"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { processSSEStream } from "@/lib/sse";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import {
  EmptyStateCard,
  ResultCard,
} from "@/components/demo/result-card";
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
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn, formatFileSize } from "@/lib/utils";
import posthog from "posthog-js";
import {
  Download,
  FileText,
  Loader2,
  Sparkles,
  Upload,
  X,
  AlertTriangle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

import {
  SectionEditor,
  type SectionRow,
  slugifyTitle,
} from "./components/section-editor";
import { OptionsForm, type ReportOptions } from "./components/options-form";
import { ProgressStream } from "./components/progress-stream";
import { ConfigActions } from "./components/config-actions";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SectionResult {
  title: string;
  content_markdown: string;
  revision_warnings: string[];
}

interface ReportResult {
  markdown: string;
  sections: SectionResult[];
  usage: Record<string, number>;
  docx_b64: string | null;
}

// ---------------------------------------------------------------------------
// Default state
// ---------------------------------------------------------------------------

const DEFAULT_SECTIONS: SectionRow[] = [
  {
    key: "s1",
    id: "",
    title: "Findings",
    instructions: "Describe the key findings drawn from the evidence.",
    depends_on: [],
  },
  {
    key: "s2",
    id: "",
    title: "Recommendations",
    instructions: "Give practical, evidence-based recommendations for next steps.",
    depends_on: [],
  },
];

const DEFAULT_OPTIONS: ReportOptions = {
  parserChoice: "auto",
  transcriptionModel: "gpt-4o-transcribe",
  language: "",
  enhancedTranscript: false,
  diarization: false,
  speakerCount: "",
  initialPrompt: "",
  imageMode: "parse",
  imageRequirements: "",
  writerModel: "gpt-5.4",
  temperature: 0,
  reasoningEffort: "medium",
  additionalInstructions: "",
  agentic: true,
  curate: true,
  polish: true,
  strictReview: true,
  reviewModel: "gpt-5.5-deployment",
  reportLanguage: "English",
  includeSourceRefs: false,
  outputDocx: true,
  maxEvidenceChars: "",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildConfig(
  reportTitle: string,
  reportDescription: string,
  sections: SectionRow[],
  options: ReportOptions,
): Record<string, unknown> {
  const secs = sections.map((s) => ({
    id: s.id || slugifyTitle(s.title),
    title: s.title,
    instructions: s.instructions,
    depends_on: s.depends_on,
  }));

  const transcriber_options: Record<string, unknown> = {};
  const ctor: Record<string, unknown> = {};
  if (options.transcriptionModel) ctor.transcription_model = options.transcriptionModel;
  if (options.language) ctor.language = options.language;
  if (options.enhancedTranscript) ctor.enhanced_transcript = true;
  if (options.diarization) {
    ctor.diarization = true;
    if (options.speakerCount) ctor.speaker_count = Number(options.speakerCount);
  }
  if (options.initialPrompt) ctor.initial_prompt = options.initialPrompt;
  if (Object.keys(ctor).length) transcriber_options.ctor = ctor;

  const image_options: Record<string, unknown> = { mode: options.imageMode };
  if (options.imageMode === "structured" && options.imageRequirements)
    image_options.user_requirements = options.imageRequirements;

  const writer_options: Record<string, unknown> = { model: options.writerModel || "gpt-5.4" };
  if (options.temperature !== 0) writer_options.temperature = options.temperature;
  if (options.reasoningEffort) writer_options.reasoning_effort = options.reasoningEffort;

  const review_options =
    options.reviewModel ? { model: options.reviewModel } : null;

  return {
    version: "1",
    report_title: reportTitle,
    report_description: reportDescription || null,
    report_language: options.reportLanguage || "English",
    sections: secs,
    input_paths: [],
    output_dir: null,
    output_docx: options.outputDocx,
    include_source_references: options.includeSourceRefs,
    max_evidence_chars: options.maxEvidenceChars ? Number(options.maxEvidenceChars) : null,
    parser_choice: options.parserChoice,
    parser_options: {},
    transcriber_options,
    image_options,
    writer_options,
    agentic: options.agentic,
    review_options,
    polish: options.polish,
    strict_review: options.strictReview,
    curate_evidence: options.curate,
    additional_instructions: options.additionalInstructions || null,
  };
}

function applyConfig(
  config: Record<string, unknown>,
  setTitle: (v: string) => void,
  setDesc: (v: string) => void,
  setSections: (v: SectionRow[]) => void,
  setOptions: (v: ReportOptions) => void,
) {
  if (typeof config.report_title === "string") setTitle(config.report_title);
  if (typeof config.report_description === "string")
    setDesc(config.report_description);

  if (Array.isArray(config.sections)) {
    setSections(
      config.sections.map((s: Record<string, unknown>, i: number) => ({
        key: `loaded-${i}-${Date.now()}`,
        id: (s.id as string) || "",
        title: (s.title as string) || "",
        instructions: (s.instructions as string) || "",
        depends_on: Array.isArray(s.depends_on) ? (s.depends_on as string[]) : [],
      })),
    );
  }

  const tc = (config.transcriber_options as Record<string, unknown>) || {};
  const ctor = (tc.ctor as Record<string, unknown>) || {};
  const img = (config.image_options as Record<string, unknown>) || {};
  const wr = (config.writer_options as Record<string, unknown>) || {};
  const rev = (config.review_options as Record<string, unknown>) || {};

  setOptions({
    parserChoice: (config.parser_choice as string) || "auto",
    transcriptionModel: (ctor.transcription_model as string) || "",
    language: (ctor.language as string) || "",
    enhancedTranscript: Boolean(ctor.enhanced_transcript),
    diarization: Boolean(ctor.diarization),
    speakerCount: ctor.speaker_count != null ? String(ctor.speaker_count) : "",
    initialPrompt: (ctor.initial_prompt as string) || "",
    imageMode: (img.mode as string) || "parse",
    imageRequirements: (img.user_requirements as string) || "",
    writerModel: (wr.model as string) || "gpt-5.4",
    temperature: typeof wr.temperature === "number" ? wr.temperature : 0,
    reasoningEffort: (wr.reasoning_effort as string) || "",
    additionalInstructions: (config.additional_instructions as string) || "",
    agentic: config.agentic !== false,
    curate: Boolean(config.curate_evidence),
    polish: Boolean(config.polish),
    strictReview: Boolean(config.strict_review),
    reviewModel: (rev.model as string) || "",
    reportLanguage: (config.report_language as string) || "English",
    includeSourceRefs: config.include_source_references !== false,
    outputDocx: Boolean(config.output_docx),
    maxEvidenceChars:
      config.max_evidence_chars != null ? String(config.max_evidence_chars) : "",
  });
}

// ---------------------------------------------------------------------------
// Multi-file upload widget (inline)
// ---------------------------------------------------------------------------

const ACCEPTED_EXTS =
  ".txt,.md,.markdown,.pdf,.docx,.csv,.xlsx,.xls,.mp3,.wav,.m4a,.aac,.flac,.ogg,.mp4,.mov,.mkv,.avi,.webm,.png,.jpg,.jpeg,.webp,.tiff,.tif,.bmp,.gif";

function MultiFileUpload({
  files,
  onChange,
  disabled,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function addFiles(incoming: File[]) {
    const names = new Set(files.map((f) => f.name));
    const fresh = incoming.filter((f) => !names.has(f.name));
    if (fresh.length) onChange([...files, ...fresh]);
  }

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "rounded-lg border-2 border-dashed p-6 text-center transition-colors cursor-pointer",
          dragging
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50",
          disabled && "pointer-events-none opacity-50",
        )}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <Upload className="mx-auto h-7 w-7 text-muted-foreground mb-2" />
        <p className="text-sm font-medium">Drop files or click to browse</p>
        <p className="text-xs text-muted-foreground mt-1">
          PDF · DOCX · Audio/Video · XLSX · Images · Text · CSV
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTS}
          className="sr-only"
          disabled={disabled}
          onChange={(e) => addFiles(Array.from(e.target.files || []))}
        />
      </div>
      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li
              key={i}
              className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-xs text-muted-foreground shrink-0">
                {formatFileSize(f.size)}
              </span>
              {!disabled && (
                <button
                  onClick={() => onChange(files.filter((_, j) => j !== i))}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ReportWriterPage() {
  // Use case
  const [reportTitle, setReportTitle] = useState("My Report");
  const [reportDescription, setReportDescription] = useState("");
  const [sections, setSections] = useState<SectionRow[]>(DEFAULT_SECTIONS);
  const [options, setOptions] = useState<ReportOptions>(DEFAULT_OPTIONS);

  // Files
  const [files, setFiles] = useState<File[]>([]);
  const [sampleReport, setSampleReport] = useState<File | null>(null);
  const [isExampleLoaded, setIsExampleLoaded] = useState(false);
  const [additionalContext, setAdditionalContext] = useState("");

  // Generation
  const [isLoading, setIsLoading] = useState(false);
  const [progressMessages, setProgressMessages] = useState<string[]>([]);
  const [result, setResult] = useState<ReportResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // -- Config helpers --

  function getConfig() {
    return buildConfig(reportTitle, reportDescription, sections, options);
  }

  function loadConfig(config: Record<string, unknown>): boolean {
    const errors: string[] = [];

    if (config.version !== undefined && config.version !== "1")
      errors.push(`Unsupported config version "${config.version}" (expected "1").`);

    if (!Array.isArray(config.sections) || config.sections.length === 0)
      errors.push('Config must include a non-empty "sections" array.');
    else {
      (config.sections as unknown[]).forEach((s, i) => {
        if (!s || typeof s !== "object")
          errors.push(`Section ${i + 1}: must be an object.`);
        else {
          const sec = s as Record<string, unknown>;
          if (!sec.title || typeof sec.title !== "string" || !sec.title.trim())
            errors.push(`Section ${i + 1}: missing required "title" string.`);
          if (!sec.instructions || typeof sec.instructions !== "string" || !sec.instructions.trim())
            errors.push(`Section ${i + 1}: missing required "instructions" string.`);
          if (sec.depends_on !== undefined && !Array.isArray(sec.depends_on))
            errors.push(`Section ${i + 1}: "depends_on" must be an array.`);
        }
      });
    }

    if (errors.length > 0) {
      toast.error(
        <div>
          <p className="font-medium mb-1">Invalid config file</p>
          <ul className="list-disc pl-4 space-y-0.5">
            {errors.map((e, i) => <li key={i} className="text-xs">{e}</li>)}
          </ul>
        </div>,
        { duration: 8000 },
      );
      return false;
    }

    applyConfig(
      config,
      setReportTitle,
      setReportDescription,
      setSections,
      setOptions,
    );
    const sectionCount = (config.sections as unknown[]).length;
    toast.success(`Config loaded — ${sectionCount} section${sectionCount !== 1 ? "s" : ""} applied.`);
    return true;
  }

  function downloadConfig() {
    const blob = new Blob([JSON.stringify(getConfig(), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "report_config.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function loadExample() {
    try {
      // Load config
      const cfgRes = await fetch("/api/report-writer/example/config");
      if (!cfgRes.ok) throw new Error("Example config not available");
      const { config } = await cfgRes.json();
      loadConfig(config);

      // Load input files
      const filesRes = await fetch("/api/report-writer/example/files");
      if (filesRes.ok) {
        const { files: fileList } = await filesRes.json();
        const loadedFiles: File[] = [];
        for (const info of fileList) {
          const r = await fetch(
            `/api/report-writer/example/file/${encodeURIComponent(info.name)}`,
          );
          if (r.ok) {
            const blob = await r.blob();
            loadedFiles.push(new File([blob], info.name));
          }
        }
        setFiles(loadedFiles);
      }

      // Load sample report
      const srRes = await fetch("/api/report-writer/example/sample-report");
      if (srRes.ok) {
        const blob = await srRes.blob();
        setSampleReport(new File([blob], "sample_report.md", { type: "text/markdown" }));
      }

      setIsExampleLoaded(true);
      toast.success("Example loaded");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load example");
    }
  }

  // -- Generate --

  async function handleGenerate() {
    if (isLoading) return;
    if (files.length === 0 && !additionalContext.trim()) {
      toast.error("Add at least one input file or provide additional context");
      return;
    }
    if (sections.filter((s) => s.title.trim()).length === 0) {
      toast.error("Add at least one section");
      return;
    }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setIsLoading(true);
    setProgressMessages([]);
    setResult(null);

    const formData = new FormData();
    for (const f of files) formData.append("files", f);
    if (additionalContext.trim()) {
      formData.append(
        "files",
        new Blob([additionalContext], { type: "text/plain" }),
        "additional_context.txt",
      );
    }
    if (sampleReport) formData.append("sample_report", sampleReport);
    formData.append("config", JSON.stringify(getConfig()));

    try {
      const response = await apiFetch("/api/report-writer/run", {
        method: "POST",
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => null);
        const message = err?.error ?? err?.detail ?? "Generation failed";
        if (response.status === 401 || response.status === 403) {
          toast.error(message, { duration: 6000 });
          setIsLoading(false);
          return;
        }
        throw new Error(message);
      }

      await processSSEStream<ReportResult>(response, {
        onResult: (data) => {
          setResult(data as unknown as ReportResult);
          setIsLoading(false);
          posthog.capture("report_written", {
            agentic: options.agentic,
            sections_count: sections.length,
            files_count: files.length,
          });
        },
        onError: (message) => {
          toast.error(message || "Generation failed");
          setIsLoading(false);
        },
        onCustomEvent: (event) => {
          if (event.type === "progress") {
            setProgressMessages((prev) => [...prev, event.data.message as string]);
          }
        },
      });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (err instanceof RateLimitError) return;
      toast.error(err instanceof Error ? err.message : "An error occurred");
      setIsLoading(false);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    setIsLoading(false);
  }

  // -- Download results --

  function downloadMarkdown() {
    if (!result) return;
    const blob = new Blob([result.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slugifyTitle(reportTitle) || "report"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadDocx() {
    if (!result?.docx_b64) return;
    const bytes = Uint8Array.from(atob(result.docx_b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slugifyTitle(reportTitle) || "report"}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const hasInput = (files.length > 0 || additionalContext.trim().length > 0) && sections.some((s) => s.title.trim());

  return (
    <PageTransition>
      <DemoPageHeader
        icon={FileText}
        title="Report Writer"
        description="Generate structured reports from any mix of documents, audio, images, and spreadsheets"
        className="mb-6"
      />

      {/* Config actions toolbar */}
      <div className="mb-6">
        <ConfigActions
          onLoadExample={loadExample}
          onUploadConfig={loadConfig}
          onDownloadConfig={downloadConfig}
          disabled={isLoading}
          isExampleLoaded={isExampleLoaded}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ── LEFT COLUMN ── */}
        <div className="space-y-5">
          {/* Use Case */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Use Case</CardTitle>
              <CardDescription>Define what report to generate</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label htmlFor="rw-title">Report title</Label>
                <Input
                  id="rw-title"
                  placeholder="e.g. Q2 Product Planning Meeting Report"
                  value={reportTitle}
                  onChange={(e) => setReportTitle(e.target.value)}
                  disabled={isLoading}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rw-desc">Report description</Label>
                <Textarea
                  id="rw-desc"
                  placeholder="Optional high-level context passed to the writer and reviewer"
                  value={reportDescription}
                  onChange={(e) => setReportDescription(e.target.value)}
                  disabled={isLoading}
                  className="min-h-[72px] resize-none text-sm"
                />
              </div>
            </CardContent>
          </Card>

          {/* Sections */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Sections</CardTitle>
              <CardDescription>
                Define the report sections. Use depends_on (Advanced) to write
                summary/conclusions sections after their dependencies.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SectionEditor
                sections={sections}
                onChange={setSections}
                disabled={isLoading}
              />
            </CardContent>
          </Card>

          {/* Input Files */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Input Files</CardTitle>
              <CardDescription>
                Evidence sources — PDF, DOCX, audio/video, XLSX, images, text, CSV
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <MultiFileUpload
                files={files}
                onChange={setFiles}
                disabled={isLoading}
              />

              {/* Additional text context */}
              <div className="space-y-1">
                <Label className="text-sm">
                  Other context / input{" "}
                  <span className="text-muted-foreground font-normal">(optional — plain text)</span>
                </Label>
                <Textarea
                  placeholder="Paste any additional context, notes, or instructions here…"
                  value={additionalContext}
                  onChange={(e) => setAdditionalContext(e.target.value)}
                  disabled={isLoading}
                  className="text-sm min-h-[80px] resize-y"
                />
              </div>

              {/* Optional sample report */}
              <div className="space-y-1">
                <Label className="text-sm">
                  Sample report{" "}
                  <span className="text-muted-foreground font-normal">(optional — format reference)</span>
                </Label>
                {sampleReport ? (
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 truncate">{sampleReport.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatFileSize(sampleReport.size)}
                    </span>
                    {!isLoading && (
                      <button
                        onClick={() => setSampleReport(null)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ) : (
                  <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground hover:border-muted-foreground/50 transition-colors">
                    <Upload className="h-4 w-4" />
                    Upload .md / .txt / .pdf / .docx
                    <input
                      type="file"
                      accept=".md,.txt,.markdown,.pdf,.docx"
                      className="sr-only"
                      disabled={isLoading}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) setSampleReport(f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Options */}
          <OptionsForm
            options={options}
            onChange={(patch) => setOptions((o) => ({ ...o, ...patch }))}
            disabled={isLoading}
          />

          {/* Generate button */}
          <div className="flex gap-2">
            <Button
              size="lg"
              className="flex-1"
              onClick={handleGenerate}
              disabled={isLoading || !hasInput}
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Generate Report
                </>
              )}
            </Button>
            {isLoading && (
              <Button variant="outline" size="lg" onClick={handleCancel}>
                <X className="mr-2 h-4 w-4" />
                Cancel
              </Button>
            )}
          </div>

          <HowItWorksCard description="How to create your report use case">
            <p>
              <strong>1. Set the report title and description.</strong> The title
              becomes the H1 heading of your report. The description is optional
              but recommended — it is passed to the writer, reviewer, and polish
              pass as shared context, helping the model stay on topic throughout.
              Example: <em>&quot;A structured summary of the Q2 product planning meeting,
              documenting decisions, action items, and open questions.&quot;</em>
            </p>
            <p>
              <strong>2. Define your sections.</strong> Each section needs a{" "}
              <strong>title</strong> (the heading that appears in the report) and{" "}
              <strong>instructions</strong> (what the section should contain). Write
              instructions as a clear prompt to the writer — the more specific, the
              better. For example:
            </p>
            <ul className="list-disc pl-5 space-y-1 text-sm">
              <li>
                <em>Title:</em> <strong>Action Items</strong> ·{" "}
                <em>Instructions:</em> &quot;List all action items from the meeting in a
                table with columns: Action Item, Owner, Due Date, and Priority. Use
                only items explicitly stated in the evidence.&quot;
              </li>
              <li>
                <em>Title:</em> <strong>Executive Summary</strong> ·{" "}
                <em>Instructions:</em> &quot;Summarize the purpose, key decisions, and
                outcome of the meeting in two concise paragraphs.&quot;
              </li>
            </ul>
            <p>
              <strong>3. Use section dependencies for hierarchical reports.</strong>{" "}
              Open the <em>Advanced</em> panel on any section to see the dependency
              chips. Click a chip to mark that section as a dependency — it turns
              solid to show it is selected. A section with dependencies is written{" "}
              <em>after</em> its dependencies are finalized and receives their
              content as additional context. Use this when a section needs to
              synthesize or summarize earlier sections — for example, an{" "}
              <em>Executive Summary</em> that should reflect the already-written{" "}
              <em>Findings</em> and <em>Decisions Made</em>, or a{" "}
              <em>Recommendations</em> section that builds on a{" "}
              <em>Risk Assessment</em>. Sections without dependencies all run in
              parallel, which is faster.
            </p>
            <p>
              <strong>4. Upload evidence files.</strong> Any mix of PDF, Word,
              audio/video, images, spreadsheets, or plain text is accepted. The
              module normalizes every file to Markdown evidence before writing.
              Audio files are transcribed automatically.
            </p>
            <p>
              <strong>5. Choose the workflow.</strong> Agentic mode drafts each
              section independently and then fact-checks and repairs it with a
              diff-editor reviewer before assembling the report. It is slower but
              produces more accurate, grounded output. Single-call writes the
              entire report in one LLM call — faster and cheaper, but without
              per-section review.
            </p>
            <p>
              <strong>6. Save and reuse your configuration.</strong> Click{" "}
              <em>Download Config</em> to save all your settings — title,
              description, sections, options — as a JSON file. Next time, click{" "}
              <em>Upload Config</em> to restore everything instantly, or share the
              file with a colleague so they can run the same report on different
              evidence.
            </p>
          </HowItWorksCard>
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="space-y-4">
          {/* Progress stream (shown while loading) */}
          {isLoading && (
            <ProgressStream
              messages={progressMessages}
              isRunning={isLoading}
              className="w-full"
            />
          )}

          {/* Result */}
          {result && !isLoading && (
            <ResultCard
              title="Generated Report"
              description={`${result.sections.length} section(s) · ${
                result.usage?.total_tokens != null
                  ? `${result.usage.total_tokens.toLocaleString()} tokens`
                  : ""
              }`}
              feedbackSlot={<FeedbackButton demoType="report-writer" />}
              delay={0}
            >
              {/* Warnings */}
              {result.sections.some((s) => s.revision_warnings.length > 0) && (
                <Alert variant="default" className="mb-3">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription className="text-xs space-y-0.5">
                    {result.sections
                      .filter((s) => s.revision_warnings.length > 0)
                      .map((s) =>
                        s.revision_warnings.map((w, i) => (
                          <p key={`${s.title}-${i}`}>
                            <strong>{s.title}:</strong> {w}
                          </p>
                        )),
                      )}
                  </AlertDescription>
                </Alert>
              )}

              {/* Section summary */}
              <div className="mb-3 flex flex-wrap gap-1.5">
                {result.sections.map((s) => (
                  <Badge
                    key={s.title}
                    variant={
                      s.revision_warnings.length > 0 ? "destructive" : "secondary"
                    }
                    className="text-xs"
                  >
                    {s.title}
                    {s.revision_warnings.length > 0 && (
                      <AlertTriangle className="ml-1 h-3 w-3" />
                    )}
                  </Badge>
                ))}
              </div>

              {/* Markdown preview */}
              <pre className="max-h-72 overflow-y-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-words font-mono leading-relaxed mb-3">
                {result.markdown.slice(0, 3000)}
                {result.markdown.length > 3000 && "\n\n[… truncated for preview …]"}
              </pre>

              {/* Download buttons */}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={downloadMarkdown}>
                  <Download className="mr-2 h-3.5 w-3.5" />
                  Download .md
                </Button>
                {result.docx_b64 ? (
                  <Button size="sm" variant="outline" onClick={downloadDocx}>
                    <Download className="mr-2 h-3.5 w-3.5" />
                    Download .docx
                  </Button>
                ) : (
                  options.outputDocx && (
                    <Button size="sm" variant="outline" disabled title="DOCX requires Pandoc">
                      <Download className="mr-2 h-3.5 w-3.5" />
                      .docx (Pandoc not available)
                    </Button>
                  )
                )}
              </div>
            </ResultCard>
          )}

          {/* Progress log after result (collapsed) */}
          {result && progressMessages.length > 0 && (
            <ProgressStream
              messages={progressMessages}
              isRunning={false}
              className="opacity-60"
            />
          )}

          {/* Empty state */}
          {!result && !isLoading && (
            <EmptyStateCard
              icon={FileText}
              title="No report yet"
              description="Upload evidence files, define sections, and click Generate Report."
              feedbackSlot={<FeedbackButton demoType="report-writer" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
