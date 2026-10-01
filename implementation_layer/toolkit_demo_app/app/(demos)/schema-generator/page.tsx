"use client";

import { CodeBlock } from "@/components/code-block";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { useModelSettings } from "@/lib/model-settings-store";
import { cn } from "@/lib/utils";
import {
  Braces,
  Download,
  Eye,
  FileCode2,
  Loader2,
  ListChecks,
  PenLine,
  Sparkles,
  Table2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { FieldsTable } from "@/components/demo/schema-fields-table";
import {
  GALLERY,
  STRUCTURE_ORDER,
  STRUCTURE_TEXT,
  STRUCTURE_TITLES,
  composeBuilderTask,
  diffFields,
  hasChanges,
  initialBuilder,
  type BuilderState,
  type SchemaField,
} from "./schema-data";
import { TaskBuilder } from "./task-builder";

interface SchemaUsage {
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  thinking_tokens?: number | null;
  total_tokens?: number | null;
  cost_usd?: number | null;
}

interface GeneratedSchema {
  schema_name: string;
  structure_type: string;
  field_count: number;
  schema_code: string;
  requirements_json: string;
  archive_filename: string;
  archive_base64: string;
  model: string;
  duration_s: number;
  usage: SchemaUsage | null;
  /** Added by newer servers: the schema as a field table, and as JSON Schema. */
  fields?: SchemaField[];
  json_schema?: string;
}

type Generated = GeneratedSchema & { task: string };
type TaskTab = "words" | "builder";

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: PenLine,
    title: "Describe the data",
    text: "Start from a ready-made task, build one from fields, or write it in your own words.",
  },
  {
    icon: Sparkles,
    title: "Generate the schema",
    text: "The model finds the structure and defines every field: its type, whether it is required, and any allowed values.",
  },
  {
    icon: Table2,
    title: "Check the fields",
    text: "Read the field table. Change the task and generate again, and you see what changed.",
  },
  {
    icon: FileCode2,
    title: "Use it in code",
    text: "Download the ZIP, copy the Pydantic model or the JSON Schema, and use them with DataExtractor.",
  },
];
const GUIDE_NOTES = [
  "Nothing is saved: the task goes to the schema model and the result comes back to your browser. To try a schema on a document, use the Extractor demo.",
];

const DEFAULT_TASK = GALLERY[0].task;

function downloadArchive(result: GeneratedSchema): void {
  const binary = window.atob(result.archive_base64);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  const url = URL.createObjectURL(
    new Blob([buffer], { type: "application/zip" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = result.archive_filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function extractorExample(schemaName: string): string {
  return `import json
from pathlib import Path

from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor import (
    CompositeExtractionRequirements,
    DataExtractor,
    ExtractionRequirements,
)
from schema import ${schemaName}

metadata = json.loads(Path("requirements.json").read_text(encoding="utf-8"))
RequirementsModel = (
    CompositeExtractionRequirements
    if metadata["requirements_type"] == "parent_with_nested_list"
    else ExtractionRequirements
)
requirements = RequirementsModel.model_validate(metadata["requirements"])

extractor = DataExtractor(
    config=get_openai_config(use_azure=True),
    model="gpt-6-luna",
    temperature=None,
    reasoning_effort="medium",
)
results = extractor.extract(
    extraction_model=${schemaName},
    requirements=requirements,
    user_requirements=metadata["user_requirements"],
    documents=["Your parsed document text"],
)
print(results)`;
}

function SchemaChanges({
  previous,
  next,
}: {
  previous: SchemaField[];
  next: SchemaField[];
}) {
  const changes = diffFields(previous, next);
  if (!hasChanges(changes))
    return (
      <p className="text-muted-foreground text-sm">
        The new schema has the same fields as the last one.
      </p>
    );
  return (
    <div className="space-y-2 text-sm">
      {changes.added.length > 0 && (
        <p>
          <Badge className="mr-2 bg-green-600 hover:bg-green-600">added</Badge>
          {changes.added.map((path) => (
            <code key={path} className="mr-2">
              {path}
            </code>
          ))}
        </p>
      )}
      {changes.removed.length > 0 && (
        <p>
          <Badge variant="destructive" className="mr-2">
            removed
          </Badge>
          {changes.removed.map((path) => (
            <code key={path} className="mr-2">
              {path}
            </code>
          ))}
        </p>
      )}
      {changes.changed.length > 0 && (
        <ul className="space-y-1">
          {changes.changed.map((change, index) => (
            <li key={index}>
              <Badge variant="outline" className="mr-2">
                changed
              </Badge>
              <code>{change.path}</code>{" "}
              <span className="text-muted-foreground">{change.what}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SchemaGeneratorPage() {
  const [tab, setTab] = useState<TaskTab>("words");
  const [task, setTask] = useState<string>(DEFAULT_TASK);
  const [galleryId, setGalleryId] = useState<string | null>(GALLERY[0].id);
  const [builder, setBuilder] = useState<BuilderState>(initialBuilder);
  const [result, setResult] = useState<Generated | null>(null);
  /** The fields of the schema before the last regeneration, to show what changed. */
  const [previousFields, setPreviousFields] = useState<SchemaField[] | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const ownModel = useModelSettings();

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  const builtTask = useMemo(() => composeBuilderTask(builder), [builder]);
  const effectiveTask = (tab === "words" ? task : (builtTask ?? "")).trim();
  const outOfDate = result !== null && result.task !== effectiveTask;

  function pickExample(id: string): void {
    const example = GALLERY.find((item) => item.id === id);
    if (!example) return;
    setTab("words");
    setTask(example.task);
    setGalleryId(id);
  }

  async function generateSchema(): Promise<void> {
    if (!effectiveTask) {
      toast.error("Describe the extraction task first");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    const before = result?.fields ?? null;

    try {
      const response = await apiFetch("/api/schema-generator", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: effectiveTask }),
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }

      const generated = (await response.json()) as GeneratedSchema;
      setPreviousFields(before);
      setResult({ ...generated, task: effectiveTask });
      posthog.capture("schema_generator_schema_generated", {
        structure_type: generated.structure_type,
        field_count: generated.field_count,
        model: generated.model,
        from: tab === "builder" ? "builder" : (galleryId ?? "own"),
      });
      toast.success("Schema generated");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return;
      toast.error(
        error instanceof Error ? error.message : "Failed to generate schema",
      );
    } finally {
      setIsLoading(false);
    }
  }

  const fields = result?.fields ?? [];

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Braces}
        title="Schema Generator"
        description="Turn plain-language extraction requirements into a reusable, type-safe data contract for GAIK workflows."
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Schema Generator"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold">
              Start from a ready-made task
            </h2>
            <p className="text-muted-foreground text-sm">
              The Schema Generator finds one of three structures. Each has two
              examples; the types on a card are the kinds of field it asks for.
            </p>
          </div>
          <div
            role="radiogroup"
            aria-label="Ready-made tasks"
            className="space-y-4"
          >
            {STRUCTURE_ORDER.map((structure) => (
              <div key={structure} className="space-y-2">
                <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                  {STRUCTURE_TITLES[structure]}
                  <Badge variant="secondary" className="font-mono font-normal">
                    {structure}
                  </Badge>
                  <span className="text-muted-foreground font-normal">
                    {STRUCTURE_TEXT[structure]}
                  </span>
                </h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {GALLERY.filter((item) => item.structure === structure).map(
                    (item) => {
                      const selected = tab === "words" && galleryId === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          disabled={isLoading}
                          onClick={() => pickExample(item.id)}
                          className={cn(
                            "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                            selected
                              ? "border-primary bg-primary/5"
                              : "bg-card hover:border-primary/40",
                          )}
                        >
                          <span className="font-semibold">{item.title}</span>
                          <span className="text-muted-foreground text-sm">
                            {item.summary}
                          </span>
                          <span className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            <Badge variant="secondary" className="font-normal">
                              {STRUCTURE_TITLES[item.structure]}
                            </Badge>
                            {item.types.map((type) => (
                              <Badge
                                key={type}
                                variant="outline"
                                className="font-normal"
                              >
                                {type}
                              </Badge>
                            ))}
                          </span>
                        </button>
                      );
                    },
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-6 md:gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Card className="self-start">
            <CardHeader>
              <CardTitle>The extraction task</CardTitle>
              <CardDescription>
                Name the fields, their types, repeated records, allowed values,
                formats, and what to return when a value is missing.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Tabs value={tab} onValueChange={(v) => setTab(v as TaskTab)}>
                <TabsList>
                  <TabsTrigger value="words">Describe in words</TabsTrigger>
                  <TabsTrigger value="builder">Build from fields</TabsTrigger>
                </TabsList>

                <TabsContent value="words" className="space-y-2 pt-3">
                  <Label htmlFor="schema-task">Extraction task</Label>
                  <Textarea
                    id="schema-task"
                    value={task}
                    onChange={(event) => {
                      setTask(event.target.value);
                      setGalleryId(null);
                    }}
                    placeholder="Describe the structured data you want to extract..."
                    disabled={isLoading}
                    rows={16}
                    maxLength={20000}
                    className="font-mono text-sm"
                  />
                  <p className="text-muted-foreground flex gap-2 text-xs">
                    <ListChecks className="mt-0.5 size-3.5 shrink-0" />A good
                    task names the fields, their types, any lists of repeated
                    records, formats such as dates, allowed values, and what to
                    return when a value is missing.
                  </p>
                </TabsContent>

                <TabsContent value="builder" className="space-y-3 pt-3">
                  <TaskBuilder
                    state={builder}
                    onChange={setBuilder}
                    disabled={isLoading}
                  />
                  <details className="rounded-lg border">
                    <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
                      <Eye className="size-4" />
                      Show the task this builds
                    </summary>
                    <pre className="bg-muted/30 border-t p-3 font-mono text-xs whitespace-pre-wrap">
                      {builtTask ?? "Add at least one field with a name."}
                    </pre>
                  </details>
                </TabsContent>
              </Tabs>

              <Button
                onClick={generateSchema}
                disabled={isLoading || !effectiveTask}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating schema…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    {result ? "Generate again" : "Generate schema"}
                  </>
                )}
              </Button>
              <p className="text-muted-foreground text-center text-xs">
                Model:{" "}
                {ownModel
                  ? `your own (${ownModel.model})`
                  : "the server's model"}
              </p>
            </CardContent>
          </Card>

          <div className="space-y-6">
            {isLoading && (
              <LoadingCard
                message="Designing the extraction schema…"
                subMessage="The model first determines the structure, then defines each field."
              />
            )}

            {!result && !isLoading && (
              <EmptyStateCard
                icon={Braces}
                title="No schema generated yet"
                description="Choose a ready-made task, build one from fields or write your own, then generate the schema."
              />
            )}

            {result && !isLoading && (
              <>
                <Card>
                  <CardHeader>
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <CardTitle>Generated schema</CardTitle>
                        <CardDescription className="mt-1 font-mono">
                          {result.schema_name}
                        </CardDescription>
                      </div>
                      <Button
                        type="button"
                        onClick={() => downloadArchive(result)}
                        className="shrink-0"
                      >
                        <Download className="mr-2 h-4 w-4" />
                        Download ZIP
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2 pt-2">
                      <Badge variant="secondary">{result.structure_type}</Badge>
                      <Badge variant="outline">
                        {result.field_count} field
                        {result.field_count === 1 ? "" : "s"}
                      </Badge>
                      <Badge variant="outline">{result.model}</Badge>
                      <Badge variant="outline">
                        {result.duration_s.toFixed(2)} s
                      </Badge>
                      {result.usage?.total_tokens != null && (
                        <Badge variant="outline">
                          {result.usage.total_tokens.toLocaleString()} tokens
                        </Badge>
                      )}
                      {outOfDate && (
                        <Badge
                          variant="outline"
                          className="border-amber-500 text-amber-700"
                        >
                          The task changed: generate again
                        </Badge>
                      )}
                    </div>
                    {STRUCTURE_TEXT[result.structure_type] && (
                      <p className="text-muted-foreground pt-1 text-sm">
                        {STRUCTURE_TEXT[result.structure_type]}
                      </p>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {previousFields && fields.length > 0 && (
                      <div className="space-y-2 rounded-lg border p-3">
                        <h4 className="text-sm font-semibold">
                          Changes since the last schema
                        </h4>
                        <SchemaChanges
                          previous={previousFields}
                          next={fields}
                        />
                      </div>
                    )}

                    <Tabs defaultValue={fields.length > 0 ? "fields" : "code"}>
                      <TabsList>
                        {fields.length > 0 && (
                          <TabsTrigger value="fields">Fields</TabsTrigger>
                        )}
                        <TabsTrigger value="code">Code and data</TabsTrigger>
                        <TabsTrigger value="use">Use in code</TabsTrigger>
                      </TabsList>

                      {fields.length > 0 && (
                        <TabsContent value="fields" className="pt-3">
                          <FieldsTable fields={fields} />
                        </TabsContent>
                      )}

                      <TabsContent value="code" className="space-y-3 pt-3">
                        <CodeBlock
                          language="python"
                          contentHeight="32rem"
                          tabs={[
                            {
                              name: "schema.py",
                              code: result.schema_code,
                              language: "python",
                            },
                            {
                              name: "requirements.json",
                              code: result.requirements_json,
                              language: "json",
                            },
                            ...(result.json_schema
                              ? [
                                  {
                                    name: "JSON Schema",
                                    code: result.json_schema,
                                    language: "json",
                                  },
                                ]
                              : []),
                          ]}
                        />
                        <p className="text-muted-foreground text-xs">
                          <strong>schema.py</strong> is the Pydantic model, the
                          structured-output contract.{" "}
                          <strong>requirements.json</strong> keeps the parsed
                          extraction intent for DataExtractor.{" "}
                          {result.json_schema && (
                            <>
                              <strong>JSON Schema</strong> is the same contract
                              for tools outside Python.{" "}
                            </>
                          )}
                          The ZIP holds the first two inside a{" "}
                          <span className="font-mono">
                            {result.schema_name}
                          </span>{" "}
                          folder.
                        </p>
                      </TabsContent>

                      <TabsContent value="use" className="space-y-3 pt-3">
                        <p className="text-muted-foreground text-sm">
                          Extract the ZIP, place this script beside its
                          generated folder contents, and replace the sample
                          document text.
                        </p>
                        <CodeBlock
                          language="python"
                          filename="extract_with_schema.py"
                          code={extractorExample(result.schema_name)}
                        />
                      </TabsContent>
                    </Tabs>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </div>
      </div>
    </PageTransition>
  );
}
