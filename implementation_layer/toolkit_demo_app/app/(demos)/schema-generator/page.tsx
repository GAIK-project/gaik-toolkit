"use client";

import { CodeBlock } from "@/components/code-block";
import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
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
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import {
  Braces,
  Download,
  FileCode2,
  FileJson2,
  Loader2,
  Sparkles,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

const EXAMPLE_TASKS = [
  {
    label: "Invoice",
    task: `Extract invoice information.

Header fields:
- Invoice number
- Invoice date (DD/MM/YYYY)
- Supplier name
- Customer name
- Total amount (numeric)
- Currency

For each line item, extract:
- Description
- Quantity (integer)
- Unit price (numeric)
- Line total (numeric)

Only return information explicitly stated in the document. Return null when a value is missing.`,
  },
  {
    label: "Meeting minutes",
    task: `Extract the meeting title, date, start time, end time, location, chairperson, and summary.

Return a list of participants containing each participant's name, organization, and role. Return a separate list of action items with task, responsible person, deadline, priority, and status.

Priority must be low, medium, or high. Status must be not_started, in_progress, completed, or unknown. Return null for missing values and do not infer information.`,
  },
  {
    label: "Maintenance ticket",
    task: `Extract a maintenance ticket with reporter name, asset identifier, location, fault description, urgency, observation date, observation time, and actions taken.

Urgency must be low, medium, or high. Format observation date as DD/MM/YYYY and observation time as HH:MM. Return null for unstated values. Do not infer or fabricate information.`,
  },
] as const;

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
}

const DEFAULT_TASK = EXAMPLE_TASKS[0].task;

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

export default function SchemaGeneratorPage() {
  const [task, setTask] = useState<string>(DEFAULT_TASK);
  const [result, setResult] = useState<GeneratedSchema | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  function updateTask(value: string): void {
    setTask(value);
    setResult(null);
  }

  async function generateSchema(): Promise<void> {
    if (!task.trim()) {
      toast.error("Describe the extraction task first");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    setResult(null);

    try {
      const response = await apiFetch("/api/schema-generator", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_requirements: task }),
        signal: abortControllerRef.current.signal,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate schema");
      }

      const generated = (await response.json()) as GeneratedSchema;
      setResult(generated);
      posthog.capture("schema_generator_schema_generated", {
        structure_type: generated.structure_type,
        field_count: generated.field_count,
        model: generated.model,
      });
      toast.success("Schema artifacts generated");
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

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Braces}
        title="Schema Generator"
        description="Turn plain-language extraction requirements into a reusable, type-safe data contract for GAIK workflows."
        className="mb-8"
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Describe the extraction task</CardTitle>
              <CardDescription>
                Name the fields, their types, repeated records, allowed values,
                formats, and missing-value behavior.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_TASKS.map((example) => (
                  <Button
                    key={example.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => updateTask(example.task)}
                    disabled={isLoading}
                  >
                    {example.label}
                  </Button>
                ))}
              </div>

              <div className="space-y-2">
                <Label htmlFor="schema-task">Extraction task</Label>
                <Textarea
                  id="schema-task"
                  value={task}
                  onChange={(event) => updateTask(event.target.value)}
                  placeholder="Describe the structured data you want to extract..."
                  disabled={isLoading}
                  rows={18}
                  className="font-mono text-sm"
                />
                <p className="text-muted-foreground text-xs">
                  The task is sent to the configured schema-generation model.
                  Generated artifacts are returned to your browser and are not
                  saved by this demo.
                </p>
              </div>

              <Button
                onClick={generateSchema}
                disabled={isLoading || !task.trim()}
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
                    Generate schema
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Two artifacts</CardTitle>
              <CardDescription>
                Extraction needs both a structural contract and semantic
                instructions.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="bg-muted/40 rounded-lg border p-4">
                <FileCode2 className="text-primary mb-3 h-5 w-5" />
                <h3 className="font-medium">schema.py</h3>
                <p className="text-muted-foreground mt-1 text-sm leading-6">
                  Defines the Pydantic model used as the structured-output
                  contract. It controls field names, Python types, nullability,
                  enums, defaults, and validation.
                </p>
              </div>
              <div className="bg-muted/40 rounded-lg border p-4">
                <FileJson2 className="text-primary mb-3 h-5 w-5" />
                <h3 className="font-medium">requirements.json</h3>
                <p className="text-muted-foreground mt-1 text-sm leading-6">
                  Preserves the parsed extraction intent: descriptions, formats,
                  required-field policy, nesting, and the original task used by
                  DataExtractor.
                </p>
              </div>
            </CardContent>
          </Card>

          <HowItWorksCard description="Describe once, review both artifacts, then reuse them for extraction.">
            <p>
              <strong>1. Describe the target data.</strong> Include field names,
              expected types, repeated sections, formats, allowed values, and
              how missing information should be represented.
            </p>
            <p>
              <strong>2. Generate and review.</strong> SchemaGenerator detects
              the output structure and creates the Pydantic model plus parsed
              extraction requirements.
            </p>
            <p>
              <strong>3. Download the pair.</strong> The ZIP keeps both files in
              one folder so they can be versioned and reviewed together.
            </p>
            <p>
              <strong>4. Use them with DataExtractor.</strong> Import the model,
              load the correct requirements type, and pass both to the extractor
              with the original task and parsed document text.
            </p>
          </HowItWorksCard>
        </div>

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
              description="Choose an example or describe your own extraction task, then generate the artifacts."
            />
          )}

          {result && !isLoading && (
            <>
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <CardTitle>Generated artifacts</CardTitle>
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
                  </div>
                </CardHeader>
                <CardContent>
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
                    ]}
                  />
                  <p className="text-muted-foreground mt-3 text-xs">
                    The downloaded ZIP contains these exact files inside a
                    single{" "}
                    <span className="font-mono">{result.schema_name}</span>{" "}
                    folder.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Use with GAIK DataExtractor</CardTitle>
                  <CardDescription>
                    Extract the ZIP, place this script beside its generated
                    folder contents, and replace the sample document text.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <CodeBlock
                    language="python"
                    filename="extract_with_schema.py"
                    code={extractorExample(result.schema_name)}
                  />
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </PageTransition>
  );
}
