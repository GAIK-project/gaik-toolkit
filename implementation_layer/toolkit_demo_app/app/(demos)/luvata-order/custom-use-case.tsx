"use client";

import { FileUpload } from "@/components/demo/file-upload";
import {
  appendVisionSettings,
  DEFAULT_VISION_SETTINGS,
  resolveVisionModel,
  UsageStats,
  type VerificationEntry,
  type VisionUsage,
  VisionSettingsFields,
  useVisionModels,
} from "@/components/demo/vision-settings";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api-client";
import { cn, formatFileSize } from "@/lib/utils";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import {
  FileCode2,
  FileUp,
  ListChecks,
  SearchCheck,
  FileText,
  ScanEye,
  Files,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import posthog from "posthog-js";
import { useState } from "react";
import toast from "react-hot-toast";
import {
  type CustomField,
  composeFromFields,
  FIELD_GROUPS,
  type FieldGroupKey,
  type FieldSelection,
  groupsFor,
  hasEnoughFields,
  initialFieldSelection,
  MAX_BOMS,
  MAX_CUSTOM_FIELDS,
} from "./custom-fields";
import { EXAMPLE_DIR, SINGLE_EXAMPLE_DIR } from "./example-data";
import { PromptEditor } from "./prompt-editor";
import {
  composePrompt,
  initialPromptState,
  type PromptState,
  type UseCaseMode,
} from "./prompt-template";

interface SchemaField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  children?: SchemaField[];
}

interface GeneratedSchema {
  schema_id: string;
  schema_name: string;
  fields: SchemaField[];
}

type Engine = "text" | "vision";

type ExtractedData = Record<string, unknown>;

interface CustomResult {
  data: ExtractedData;
  documents: string[];
  /** Set by vision extraction: */
  usage?: VisionUsage | null;
  model?: string;
}

// What the vision extractor reads: PDFs and images.
const VISION_ACCEPT = ".pdf,.png,.jpg,.jpeg,.gif,.webp,.tiff,.bmp";
const GUIDE_STEPS: GuideStep[] = [
  {
    icon: FileUp,
    title: "Add your documents",
    text: "One purchase order, or one with up to 10 BOMs (PDF, 10 MB each). Or press Use example PO.",
  },
  {
    icon: ListChecks,
    title: "Decide what to extract",
    text: "Tick fields, edit the highlighted prompt, or write your own prompt.",
  },
  {
    icon: FileCode2,
    title: "Generate the schema",
    text: "Press Generate schema. It lasts for this session and updates when you change the fields or prompt.",
  },
  {
    icon: Sparkles,
    title: "Extract",
    text: "Press Extract data. For scans or odd layouts, turn on vision extraction first.",
  },
  {
    icon: SearchCheck,
    title: "Review and refine",
    text: "Check the values, adjust the fields or prompt and extract again, or Reset.",
  },
];
const GUIDE_NOTES = [
  "This section extracts only: there is no price list, no fee calculation and no order draft.",
  "With vision extraction and verification switched on, every value also gets a confidence score, so you can see which ones to check.",
  "Nothing you upload is kept as a use case: the schema lives for this session.",
];

const VISION_MAX_MB = 20;

type Source = "fields" | "prompt" | "own";

const MAX_OWN_PROMPT = 8000;

const MODES: {
  value: UseCaseMode;
  title: string;
  description: string;
  icon: typeof FileText;
}[] = [
  {
    value: "single",
    title: "Single-file purchase order",
    description: "Extract data from a single PO PDF.",
    icon: FileText,
  },
  {
    value: "multi",
    title: "Purchase order + BOMs",
    description:
      "Extract from a PO and its BOMs, and align each PO item with its BOM.",
    icon: Files,
  },
];

const EXAMPLE_BOMS = ["BOM1.pdf", "BOM2.pdf", "BOM3.pdf"];

async function errorMessage(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON: keep the fallback.
  }
  return fallback;
}

function FieldPicker({
  group,
  picked,
  custom,
  disabled,
  onToggle,
  onAdd,
  onRemove,
}: {
  group: FieldGroupKey;
  picked: string[];
  custom: CustomField[];
  disabled: boolean;
  onToggle: (label: string) => void;
  onAdd: (field: CustomField) => void;
  onRemove: (name: string) => void;
}) {
  const { title, hint, choices } = FIELD_GROUPS[group];
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const add = () => {
    if (name.trim()) {
      onAdd({ name: name.trim(), description: description.trim() });
      setName("");
      setDescription("");
    }
  };
  const onEnter = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-sm font-semibold">{title}</h4>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {choices.map((choice) => {
          const checked = picked.includes(choice.label);
          return (
            <label
              key={choice.label}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 text-sm transition-colors",
                checked
                  ? "border-primary/50 bg-primary/5"
                  : "hover:bg-muted/50",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => onToggle(choice.label)}
                className="accent-primary mt-0.5 size-4 shrink-0"
              />
              <span>
                <span className="font-medium">{choice.label}</span>
                <span className="text-muted-foreground block text-xs">
                  {choice.description}
                </span>
              </span>
            </label>
          );
        })}
        {custom.map((field) => (
          <div
            key={field.name}
            className="border-primary/50 bg-primary/5 flex items-start gap-2.5 rounded-lg border p-2.5 text-sm"
          >
            <span className="min-w-0 flex-1">
              <span className="font-medium">{field.name}</span>
              <span className="text-muted-foreground block text-xs">
                {field.description || "Your own field"}
              </span>
            </span>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onRemove(field.name)}
              className="hover:bg-primary/10 rounded-full p-1"
              aria-label={`Remove ${field.name}`}
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={name}
          disabled={disabled}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={onEnter}
          placeholder="Your own field, e.g. Project code"
          maxLength={80}
          className="sm:w-64"
        />
        <Input
          value={description}
          disabled={disabled}
          onChange={(e) => setDescription(e.target.value)}
          onKeyDown={onEnter}
          placeholder="What it means (optional)"
          maxLength={300}
          className="flex-1"
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled || !name.trim()}
          onClick={add}
        >
          <Plus className="mr-1 size-4" />
          Add field
        </Button>
      </div>
    </div>
  );
}

function SchemaPreview({ schema }: { schema: GeneratedSchema }) {
  const rows = schema.fields.flatMap((field) => [
    { ...field, indent: false },
    ...(field.children ?? []).map((child) => ({ ...child, indent: true })),
  ]);
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <p className="text-sm font-semibold">Generated schema</p>
      <ul className="space-y-1 text-xs">
        {rows.map((field, index) => (
          <li key={index} className={cn(field.indent && "ml-5")}>
            <span className="font-mono">{field.name}</span>
            <span className="text-muted-foreground"> : {field.type}</span>
            {field.required && <span className="ml-1 text-orange-500">*</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const ACRONYMS = new Set(["po", "bom", "id"]);

/** "po_number" -> "PO number". */
const label = (key: string) =>
  key
    .split("_")
    .map((word, i) =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : i === 0
          ? word.charAt(0).toUpperCase() + word.slice(1)
          : word,
    )
    .join(" ");

/** With per-field verification the vision extractor returns {value, confidence...}. */
function asVerified(value: unknown): VerificationEntry | null {
  if (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    "value" in value &&
    "confidence_score" in value
  )
    return value as VerificationEntry;
  return null;
}

function Confidence({ entry }: { entry: VerificationEntry }) {
  return (
    <span
      title={entry.confidence_reason}
      className="bg-primary/10 text-primary ml-2 rounded px-1.5 py-0.5 font-mono text-xs font-normal"
    >
      {Math.round((entry.confidence_score ?? 0) * 100)}%
    </span>
  );
}

function Value({ value }: { value: unknown }) {
  const verified = asVerified(value);
  if (verified) {
    return (
      <>
        <Value value={verified.value} />
        <Confidence entry={verified} />
      </>
    );
  }
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted-foreground">—</span>;
  }
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (typeof value === "object") return <>{JSON.stringify(value)}</>;
  return <>{String(value)}</>;
}

function DataView({ data }: { data: ExtractedData }) {
  const entries = Object.entries(data);
  const scalars = entries.filter(([, v]) => !Array.isArray(v));
  const lists = entries.filter(([, v]) => Array.isArray(v));
  return (
    <div className="space-y-4">
      {scalars.length > 0 && (
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {scalars.map(([key, value]) => (
            <div key={key} className="flex flex-col">
              <dt className="text-muted-foreground text-xs">{label(key)}</dt>
              <dd className="font-medium break-words">
                <Value value={value} />
              </dd>
              {asVerified(value)?.confidence_reason && (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {asVerified(value)?.confidence_reason}
                </p>
              )}
            </div>
          ))}
        </dl>
      )}
      {lists.map(([key, value]) => {
        const rows = (value as unknown[]).filter(
          (row): row is Record<string, unknown> =>
            typeof row === "object" && row !== null,
        );
        const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
        return (
          <div key={key} className="space-y-1.5">
            <p className="text-xs font-medium">
              {label(key)} ({(value as unknown[]).length})
            </p>
            {columns.length > 0 ? (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columns.map((column) => (
                        <TableHead key={column}>{label(column)}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row, index) => (
                      <TableRow key={index}>
                        {columns.map((column) => (
                          <TableCell key={column}>
                            <Value value={row[column]} />
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">
                <Value value={value} />
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Extract other data than the standard flow does, from one PO or from a PO with its
 * BOMs. What to extract comes from ticked and own fields or from an editable prompt;
 * either way the schema is generated for this session only and never saved.
 */
export function CustomUseCase() {
  const [mode, setMode] = useState<UseCaseMode>("single");
  const [source, setSource] = useState<Source>("fields");
  const [poFile, setPoFile] = useState<File | null>(null);
  const [bomFiles, setBomFiles] = useState<File[]>([]);
  const [selection, setSelection] = useState<FieldSelection>(
    initialFieldSelection,
  );
  const [prompts, setPrompts] = useState<Record<UseCaseMode, PromptState>>(
    () => ({
      single: initialPromptState("single"),
      multi: initialPromptState("multi"),
    }),
  );
  // The prompts users write themselves, one per case.
  const [ownPrompts, setOwnPrompts] = useState<Record<UseCaseMode, string>>({
    single: "",
    multi: "",
  });
  // Advanced options: read the documents as images with the Vision Extractor.
  const [vision, setVision] = useState(false);
  const [visionSettings, setVisionSettings] = useState(DEFAULT_VISION_SETTINGS);
  const catalogue = useVisionModels();
  const [schema, setSchema] = useState<{
    prompt: string;
    engine: Engine;
    data: GeneratedSchema;
  } | null>(null);
  const [result, setResult] = useState<CustomResult | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [loadingExample, setLoadingExample] = useState(false);

  const multi = mode === "multi";
  const prompt =
    source === "fields"
      ? composeFromFields(mode, selection)
      : source === "prompt"
        ? composePrompt(mode, prompts[mode])
        : ownPrompts[mode].trim();
  const promptValid =
    source === "fields"
      ? hasEnoughFields(mode, selection)
      : prompt.length >= 10;
  const engine: Engine = vision ? "vision" : "text";
  const schemaReady = schema?.prompt === prompt && schema.engine === engine;
  const filesReady = poFile !== null && (!multi || bomFiles.length > 0);
  const busy = generating || extracting || loadingExample;

  const changeMode = (next: UseCaseMode) => {
    setMode(next);
    if (next === "single") setBomFiles([]);
    setResult(null);
  };

  const toggle = (group: FieldGroupKey, choice: string) =>
    setSelection((prev) => ({
      ...prev,
      picked: {
        ...prev.picked,
        [group]: prev.picked[group].includes(choice)
          ? prev.picked[group].filter((c) => c !== choice)
          : [...prev.picked[group], choice],
      },
    }));

  const addCustom = (group: FieldGroupKey, field: CustomField) => {
    const taken = [
      ...FIELD_GROUPS[group].choices.map((c) => c.label),
      ...selection.custom[group].map((c) => c.name),
    ].map((n) => n.toLowerCase());
    if (taken.includes(field.name.toLowerCase())) {
      toast.error(`"${field.name}" is already in the list`);
      return;
    }
    if (selection.custom[group].length >= MAX_CUSTOM_FIELDS) {
      toast.error(`At most ${MAX_CUSTOM_FIELDS} own fields per list`);
      return;
    }
    setSelection((prev) => ({
      ...prev,
      custom: { ...prev.custom, [group]: [...prev.custom[group], field] },
    }));
  };

  const removeCustom = (group: FieldGroupKey, name: string) =>
    setSelection((prev) => ({
      ...prev,
      custom: {
        ...prev.custom,
        [group]: prev.custom[group].filter((c) => c.name !== name),
      },
    }));

  const addBoms = (files: File[]) => {
    const next = [...bomFiles, ...files];
    if (next.length > MAX_BOMS) toast.error(`At most ${MAX_BOMS} BOMs`);
    setBomFiles(next.slice(0, MAX_BOMS));
  };

  const loadExample = async () => {
    setLoadingExample(true);
    try {
      const fetchFile = async (name: string) => {
        const dir = multi ? EXAMPLE_DIR : SINGLE_EXAMPLE_DIR;
        const response = await fetch(`${dir}/${name}`);
        if (!response.ok) throw new Error(`Failed to fetch ${name}`);
        return new File([await response.blob()], name, {
          type: "application/pdf",
        });
      };
      const [po, ...boms] = await Promise.all([
        fetchFile("PO.pdf"),
        ...(multi ? EXAMPLE_BOMS.map(fetchFile) : []),
      ]);
      setPoFile(po);
      setBomFiles(boms);
      setResult(null);
      toast.success(multi ? "Example PO and BOMs loaded" : "Example PO loaded");
    } catch (error) {
      toast.error("Failed to load example files");
      console.error(error);
    } finally {
      setLoadingExample(false);
    }
  };

  const generateSchema = async () => {
    setGenerating(true);
    setResult(null);
    try {
      // The vision extractor makes its own schemas, exactly as its demo does.
      const response = vision
        ? await apiFetch("/api/extract-vision/generate-schema", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_requirements: prompt }),
          })
        : await apiFetch("/api/luvata-order/custom/schema", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              requirements: prompt,
              regenerate: schemaReady,
            }),
          });
      if (!response.ok) {
        throw new Error(
          await errorMessage(response, "Failed to generate schema"),
        );
      }
      setSchema({
        prompt,
        engine,
        data: (await response.json()) as GeneratedSchema,
      });
      toast.success(schemaReady ? "Schema regenerated" : "Schema generated");
      posthog.capture("luvata_custom_schema_generated", {
        mode,
        source,
        vision,
      });
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to generate schema",
      );
    } finally {
      setGenerating(false);
    }
  };

  const extract = async () => {
    if (!poFile) return;
    setExtracting(true);
    setResult(null);
    const started = performance.now();
    try {
      const formData = new FormData();
      const documents = [poFile, ...(multi ? bomFiles : [])];
      if (vision && schema) {
        // One call that reads every document as images, as in the Vision Extractor demo.
        documents.forEach((file) => formData.append("files", file));
        formData.append("user_requirements", prompt);
        formData.append("schema_id", schema.data.schema_id);
        appendVisionSettings(
          formData,
          visionSettings,
          resolveVisionModel(visionSettings, catalogue),
        );
      } else {
        formData.append("po_file", poFile);
        formData.append("requirements", prompt);
        if (multi)
          bomFiles.forEach((file) => formData.append("bom_files", file));
      }
      const response = await apiFetch(
        vision ? "/api/extract-vision" : "/api/luvata-order/custom/extract",
        { method: "POST", body: formData },
      );
      if (!response.ok) {
        throw new Error(await errorMessage(response, "Extraction failed"));
      }
      const body = await response.json();
      setResult({
        ...body,
        documents: vision ? documents.map((file) => file.name) : body.documents,
      } as CustomResult);
      setElapsed((performance.now() - started) / 1000);
      toast.success("Extraction complete");
      posthog.capture("luvata_custom_extraction_completed", {
        mode,
        source,
        vision,
        bom_count: bomFiles.length,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const reset = () => {
    setPoFile(null);
    setBomFiles([]);
    setSelection(initialFieldSelection());
    setPrompts({
      single: initialPromptState("single"),
      multi: initialPromptState("multi"),
    });
    setOwnPrompts({ single: "", multi: "" });
    setVision(false);
    setVisionSettings(DEFAULT_VISION_SETTINGS);
    setSchema(null);
    setResult(null);
  };

  const hint = !promptValid
    ? source === "fields"
      ? "Choose at least one field to extract."
      : source === "own"
        ? "Write your extraction prompt."
        : "Describe what to extract."
    : !schemaReady
      ? "Generate the schema first. It updates whenever you change the fields or the prompt."
      : !filesReady
        ? multi
          ? "Add a purchase order PDF and at least one BOM PDF."
          : "Add a purchase order PDF to extract from."
        : "The schema is ready. It is reused for every file until you change the fields or the prompt.";

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to test your own use case"
        steps={GUIDE_STEPS}
        notes={GUIDE_NOTES}
      />
      <Card
        id="custom-use-case"
        className="border-primary/30 scroll-mt-24 border-2"
      >
        <CardHeader>
          <CardDescription className="text-base">
            Test purchase order processing with your own example document and
            specified fields. This demo does not include price calculating. For
            building an extraction+price calculation PoC, use the solution
            configuration wizard.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Advanced options */}
          <section className="rounded-lg border">
            <h3 className="flex items-center gap-2 px-4 py-3 text-sm font-semibold">
              Advanced options
              {vision && (
                <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs font-medium">
                  Vision extraction on
                </span>
              )}
            </h3>
            <div className="space-y-4 border-t px-4 py-4">
              <label
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
                  vision
                    ? "border-primary/50 bg-primary/5"
                    : "hover:bg-muted/50",
                  busy && "cursor-not-allowed opacity-60",
                )}
              >
                <input
                  type="checkbox"
                  checked={vision}
                  disabled={busy}
                  onChange={(e) => {
                    setVision(e.target.checked);
                    setResult(null);
                  }}
                  className="accent-primary mt-1 size-4 shrink-0"
                />
                <span className="flex items-start gap-3">
                  <ScanEye className="text-primary mt-0.5 size-5 shrink-0" />
                  <span>
                    <span className="block font-medium">
                      Vision extraction for complex documents
                    </span>
                    <span className="text-muted-foreground block text-sm">
                      Suitable for scans, stamps, unusual layouts and tables
                      that do not parse well. The demo accepts PDFs and images
                      up to {VISION_MAX_MB} MB and can take longer.
                    </span>
                  </span>
                </span>
              </label>
              {vision && (
                <VisionSettingsFields
                  settings={visionSettings}
                  catalogue={catalogue}
                  disabled={busy}
                  idPrefix="luvata-vision"
                  onChange={setVisionSettings}
                />
              )}
            </div>
          </section>

          {/* Case */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">
              Which documents do you have?
            </h3>
            <div
              role="radiogroup"
              aria-label="Documents"
              className="grid gap-3 sm:grid-cols-2"
            >
              {MODES.map(({ value, title, description, icon: Icon }) => (
                <label
                  key={value}
                  className={cn(
                    "has-checked:border-primary has-checked:bg-primary/5 flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors",
                    mode !== value && "hover:bg-muted/50",
                    busy && "cursor-not-allowed opacity-60",
                  )}
                >
                  <input
                    type="radio"
                    name="use-case-mode"
                    value={value}
                    checked={mode === value}
                    disabled={busy}
                    onChange={() => changeMode(value)}
                    className="sr-only"
                  />
                  <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                    <Icon className="size-4" />
                  </span>
                  <span>
                    <span className="block font-semibold">{title}</span>
                    <span className="text-muted-foreground block text-sm">
                      {description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* 1. Documents */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">1. Documents</h3>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={loadExample}
              >
                {loadingExample ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <FileText className="mr-2 size-4" />
                )}
                {multi ? "Use example PO and BOMs" : "Use example PO"}
              </Button>
            </div>
            <div
              className={cn(
                "grid gap-4 md:items-start",
                multi && "md:grid-cols-2",
              )}
            >
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">
                  Purchase Order PDF
                </label>
                <FileUpload
                  accept={vision ? VISION_ACCEPT : ".pdf"}
                  maxSize={vision ? VISION_MAX_MB : undefined}
                  file={poFile}
                  onFileSelect={(file) => {
                    setPoFile(file);
                    setResult(null);
                  }}
                  onFileRemove={() => setPoFile(null)}
                  disabled={busy}
                />
              </div>
              {multi && (
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium">BOM PDFs</label>
                  {bomFiles.map((file, index) => (
                    <div
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-3 rounded-lg border p-2.5"
                    >
                      <FileText className="text-muted-foreground size-4 shrink-0" />
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {file.name}
                        <span className="text-muted-foreground ml-2 text-xs">
                          {formatFileSize(file.size)}
                        </span>
                      </span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          setBomFiles(bomFiles.filter((_, i) => i !== index))
                        }
                        className="hover:bg-muted rounded-full p-1"
                        aria-label={`Remove ${file.name}`}
                      >
                        <X className="size-4" />
                      </button>
                    </div>
                  ))}
                  <label className="border-muted-foreground/25 text-muted-foreground hover:border-primary/50 hover:bg-muted/50 flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-3 text-sm font-medium transition-colors">
                    <Upload className="size-4" />
                    {bomFiles.length > 0 ? "Add more BOM PDFs" : "Add BOM PDFs"}
                    <input
                      type="file"
                      accept={vision ? VISION_ACCEPT : ".pdf"}
                      multiple
                      disabled={busy}
                      onChange={(e) => {
                        addBoms(Array.from(e.target.files ?? []));
                        e.target.value = "";
                      }}
                      className="sr-only"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* 2. What to extract */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">2. What to extract</h3>
            <Tabs value={source} onValueChange={(v) => setSource(v as Source)}>
              <TabsList className="h-auto flex-wrap justify-start">
                <TabsTrigger value="fields" disabled={busy}>
                  Choose fields
                </TabsTrigger>
                <TabsTrigger value="prompt" disabled={busy}>
                  Edit the extraction prompt
                </TabsTrigger>
                <TabsTrigger value="own" disabled={busy}>
                  Create your own extraction prompt
                </TabsTrigger>
              </TabsList>
              <TabsContent value="fields" className="space-y-5 pt-3">
                {groupsFor(mode).map((group) => (
                  <FieldPicker
                    key={group}
                    group={group}
                    picked={selection.picked[group]}
                    custom={selection.custom[group]}
                    disabled={busy}
                    onToggle={(choice) => toggle(group, choice)}
                    onAdd={(field) => addCustom(group, field)}
                    onRemove={(name) => removeCustom(group, name)}
                  />
                ))}
                <details className="text-sm">
                  <summary className="text-primary cursor-pointer font-medium">
                    Show the prompt built from these fields
                  </summary>
                  <pre className="bg-muted/50 mt-2 max-h-64 overflow-auto rounded-lg border p-3 text-xs whitespace-pre-wrap">
                    {composeFromFields(mode, selection)}
                  </pre>
                </details>
              </TabsContent>
              <TabsContent value="prompt" className="pt-3">
                <PromptEditor
                  mode={mode}
                  state={prompts[mode]}
                  disabled={busy}
                  onChange={(next) =>
                    setPrompts((prev) => ({ ...prev, [mode]: next }))
                  }
                  onReset={() =>
                    setPrompts((prev) => ({
                      ...prev,
                      [mode]: initialPromptState(mode),
                    }))
                  }
                />
              </TabsContent>
              <TabsContent value="own" className="space-y-3 pt-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <p className="text-muted-foreground">
                    Write the prompt yourself. Name the fields you want and, if
                    it matters, how to write them.
                    {multi &&
                      " Say how each PO item is linked to its BOM, for example by material number."}
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      setOwnPrompts((prev) => ({
                        ...prev,
                        [mode]: composePrompt(mode, prompts[mode]),
                      }))
                    }
                    className="h-7"
                  >
                    Start from the extraction prompt
                  </Button>
                </div>
                <Textarea
                  value={ownPrompts[mode]}
                  disabled={busy}
                  maxLength={MAX_OWN_PROMPT}
                  rows={12}
                  onChange={(e) =>
                    setOwnPrompts((prev) => ({
                      ...prev,
                      [mode]: e.target.value,
                    }))
                  }
                  placeholder={
                    multi
                      ? "Extract the PO number and, for every PO item, its material number, quantity and the part dimension from the matching BOM. ..."
                      : "Extract the purchase order number, the supplier and, for every line item, the material number and quantity. ..."
                  }
                  className="bg-primary/5 border-primary/30 text-sm"
                />
                <p className="text-muted-foreground text-right text-xs">
                  {ownPrompts[mode].length} / {MAX_OWN_PROMPT}
                </p>
              </TabsContent>
            </Tabs>
          </div>

          {/* 3. Schema and extraction */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">
              3. Generate schema and extract
            </h3>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={busy || !promptValid}
                onClick={generateSchema}
              >
                {generating ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Generating schema...
                  </>
                ) : (
                  <>
                    <FileCode2 className="mr-2 size-4" />
                    {schemaReady ? "Regenerate schema" : "Generate schema"}
                  </>
                )}
              </Button>
              <Button
                type="button"
                disabled={busy || !schemaReady || !filesReady}
                onClick={extract}
              >
                {extracting ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Extracting...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 size-4" />
                    Extract data
                  </>
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={reset}
              >
                <RotateCcw className="mr-2 size-4" />
                Reset
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">{hint}</p>
            {schemaReady && schema && <SchemaPreview schema={schema.data} />}
          </div>

          {result && (
            <div className="space-y-3 border-t pt-6">
              <h3 className="text-sm font-semibold">
                Extracted data
                {elapsed !== null && (
                  <span className="text-muted-foreground ml-2 text-xs font-normal">
                    {result.documents.length} document
                    {result.documents.length > 1 ? "s" : ""} in{" "}
                    {elapsed.toFixed(1)} s
                    {result.model ? ` · ${result.model}` : ""}
                  </span>
                )}
              </h3>
              <div className="rounded-lg border p-4">
                {result.usage && <UsageStats usage={result.usage} />}
                <DataView data={result.data} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
