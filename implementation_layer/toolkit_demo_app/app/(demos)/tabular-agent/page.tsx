"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { HowItWorksCard } from "@/components/demo/how-it-works-card";
import { PageTransition } from "@/components/demo/page-transition";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
  ResultText,
} from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { AlertTriangle, Sparkles, Table2 } from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useState } from "react";
import toast from "react-hot-toast";

interface AskResponse {
  question: string;
  answer: string;
  succeeded: boolean;
  sql: string | null;
  reasoning: string | null;
  rows: Record<string, unknown>[];
  row_count: number;
  attempts: number;
  error: string | null;
}

interface ColumnInfo {
  name: string;
  data_type: string;
  null_fraction: number;
  distinct_count: number;
  min_value: string | null;
  max_value: string | null;
  top_values: string[];
  samples: string[];
}

interface TableInfo {
  name: string;
  source: string;
  row_count: number;
  columns: ColumnInfo[];
}

interface UploadResponse {
  session_id: string;
  filename: string;
  tables: TableInfo[];
  schema_text: string;
}

interface StatusResponse {
  component_available: boolean;
  llm_configured: boolean;
  allowed_extensions: string[];
  max_file_size_mb: number;
  detail: string | null;
}

const EXAMPLE_QUESTIONS = [
  "How many rows are there in total?",
  "Which category has the highest total?",
  "Show the top 5 rows by value.",
  "Are there any missing values?",
];

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  const columns = Object.keys(rows[0] ?? {});
  return (
    <div
      className="overflow-auto rounded-md border"
      style={{ maxHeight: "320px" }}
    >
      <table className="w-full text-sm">
        <thead className="bg-muted sticky top-0">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 text-left font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t">
              {columns.map((c) => (
                <td key={c} className="px-3 py-2 font-mono text-xs">
                  {row[c] === null || row[c] === undefined
                    ? "—"
                    : String(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function TabularAgentPage() {
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);

  useEffect(() => {
    async function loadStatus(): Promise<void> {
      try {
        const res = await apiFetch("/api/tabular-agent/status");
        if (res.ok) setStatus(await res.json());
      } catch {
        // The status banner is a nicety; the page still works without it.
      }
    }
    void loadStatus();
  }, []);

  async function handleUpload(selected: File): Promise<void> {
    setFile(selected);
    setUpload(null);
    setResult(null);
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", selected);

      // No Content-Type header: the browser sets the multipart boundary.
      const response = await apiFetch("/api/tabular-agent/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Could not read the file");
      }

      const data: UploadResponse = await response.json();
      setUpload(data);
      posthog.capture("tabular_agent_upload", {
        tables: data.tables.length,
        rows: data.tables.reduce((n, t) => n + t.row_count, 0),
      });
      toast.success(
        data.tables.length === 1
          ? `Loaded ${data.tables[0].row_count} rows`
          : `Loaded ${data.tables.length} tables`,
      );
    } catch (error) {
      if (error instanceof RateLimitError) return;
      setFile(null);
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsUploading(false);
    }
  }

  function handleRemove(): void {
    if (upload) {
      void apiFetch(`/api/tabular-agent/session/${upload.session_id}`, {
        method: "DELETE",
      }).catch(() => undefined);
    }
    setFile(null);
    setUpload(null);
    setResult(null);
  }

  async function handleAsk(override?: string): Promise<void> {
    if (isAsking || !upload) return;
    const finalQuestion = (override ?? question).trim();
    if (!finalQuestion) {
      toast.error("Please enter a question");
      return;
    }

    setIsAsking(true);
    setResult(null);

    try {
      const response = await apiFetch("/api/tabular-agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: upload.session_id,
          question: finalQuestion,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to answer the question");
      }

      const data: AskResponse = await response.json();
      setResult(data);

      posthog.capture("tabular_agent_query", {
        succeeded: data.succeeded,
        attempts: data.attempts,
        row_count: data.row_count,
      });

      if (data.succeeded) {
        toast.success("Query completed");
      }
    } catch (error) {
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsAsking(false);
    }
  }

  function handleExample(q: string): void {
    setQuestion(q);
    void handleAsk(q);
  }

  const accept = status?.allowed_extensions.join(",") ?? ".csv,.xlsx,.xls";
  const maxSize = status?.max_file_size_mb ?? 20;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Table2}
        title="Tabular Agent"
        description="Ask your own CSV or Excel file questions in plain language — the agent writes and runs read-only SQL"
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Upload a spreadsheet</CardTitle>
              <CardDescription>
                Your file is loaded into an in-memory database, profiled, and
                queried with validated read-only SQL. Report-style sheets with
                title rows, subtotals and trailing notes are cleaned up
                automatically. The file is deleted when you close the session.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FileUpload
                accept={accept}
                maxSize={maxSize}
                file={file}
                onFileSelect={(f) => void handleUpload(f)}
                onFileRemove={handleRemove}
                disabled={isUploading || isAsking}
              />

              {!upload && (
                <p className="text-muted-foreground text-xs">
                  No spreadsheet handy? Try{" "}
                  <a
                    href="/gaik_tabular_demo_sales.csv"
                    download
                    className="underline underline-offset-2"
                  >
                    a tidy sales CSV
                  </a>{" "}
                  or{" "}
                  <a
                    href="/gaik_tabular_demo_report.xlsx"
                    download
                    className="underline underline-offset-2"
                  >
                    a messy Excel report
                  </a>{" "}
                  — both are synthetic sample data.
                </p>
              )}

              {upload && (
                <div className="flex flex-wrap gap-2">
                  {upload.tables.map((t) => (
                    <Badge key={t.name} variant="secondary">
                      {t.name} · {t.row_count} rows · {t.columns.length} columns
                    </Badge>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleAsk();
                    }
                  }}
                  placeholder={
                    upload
                      ? "e.g. Which region had the highest total?"
                      : "Upload a file first"
                  }
                  disabled={!upload || isAsking || isUploading}
                />
                <Button
                  onClick={() => void handleAsk()}
                  disabled={!upload || isAsking || !question.trim()}
                >
                  <Sparkles className="mr-2 h-4 w-4" />
                  {isAsking ? "Asking..." : "Ask"}
                </Button>
              </div>

              {upload && (
                <div className="space-y-2">
                  <p className="text-muted-foreground text-xs font-medium">
                    Example questions
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {EXAMPLE_QUESTIONS.map((q) => (
                      <Badge
                        key={q}
                        variant="outline"
                        className="hover:bg-muted cursor-pointer transition-colors"
                        onClick={() => !isAsking && handleExample(q)}
                      >
                        {q}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {status && !status.component_available && (
                <p className="text-destructive flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  The tabular agent is not available in this build.
                </p>
              )}
              {status && status.component_available && !status.llm_configured && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  No LLM API key configured — questions cannot be answered.
                </p>
              )}
            </CardContent>
          </Card>

          {upload && (
            <ResultCard
              title="What the model sees"
              description="Column types, ranges and the values each column actually holds"
              copyContent={upload.schema_text}
            >
              <ResultText content={upload.schema_text} maxHeight="240px" />
            </ResultCard>
          )}

          <HowItWorksCard description="The agent loads your file into DuckDB, profiles every column, generates validated read-only SQL, runs it, and explains the result.">
            <p>
              <strong>1. Upload:</strong> CSV, Excel, Parquet or JSON. Each Excel
              sheet becomes its own table, so questions can span sheets.
            </p>
            <p>
              <strong>2. Clean-up:</strong> Title rows, blank spacers, subtotal
              lines and trailing notes are removed. Nordic number formats
              (<code>1 234,56</code>) become real numbers.
            </p>
            <p>
              <strong>3. Profiling:</strong> Every column is described — its
              type, how many values are missing, and which values it actually
              contains. This is what stops the model inventing filters.
            </p>
            <p>
              <strong>4. Safe execution:</strong> The SQL is validated as
              read-only and the engine is locked so it cannot reach the
              filesystem. If a query fails, the error is fed back and retried.
            </p>
            <p>
              <strong>5. Plain-language answer:</strong> The rows are summarized
              into an answer — with the SQL shown, so you can check it.
            </p>
          </HowItWorksCard>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isUploading && (
            <LoadingCard
              message="Reading your file..."
              subMessage="Loading, cleaning up and profiling the columns"
            />
          )}

          {isAsking && (
            <LoadingCard
              message="Answering your question..."
              subMessage="Generating and running SQL"
            />
          )}

          {result && !isAsking && !isUploading && (
            <>
              <ResultCard
                title="Answer"
                description={`Question: ${result.question}`}
                copyContent={result.answer}
                feedbackSlot={<FeedbackButton demoType="tabular-agent" />}
                delay={0}
              >
                <p className="text-sm leading-relaxed">{result.answer}</p>
                {result.attempts > 1 && (
                  <p className="text-muted-foreground mt-2 text-xs">
                    The agent corrected its SQL — {result.attempts} attempts.
                  </p>
                )}
              </ResultCard>

              {result.sql && (
                <ResultCard
                  title="Generated SQL"
                  description="The read-only query the agent ran"
                  copyContent={result.sql}
                  delay={0.1}
                >
                  <ResultText content={result.sql} maxHeight="200px" />
                </ResultCard>
              )}

              {result.succeeded && result.rows.length > 0 && (
                <ResultCard title={`Rows (${result.row_count})`} delay={0.15}>
                  <RowsTable rows={result.rows} />
                </ResultCard>
              )}

              {result.succeeded && result.rows.length === 0 && (
                <ResultCard title="Rows" delay={0.15}>
                  <p className="text-muted-foreground text-sm">
                    The query ran successfully but returned no rows.
                  </p>
                </ResultCard>
              )}

              {!result.succeeded && result.error && (
                <ResultCard title="Query error" delay={0.1}>
                  <p className="text-destructive text-sm">{result.error}</p>
                </ResultCard>
              )}
            </>
          )}

          {!result && !isAsking && !isUploading && (
            <EmptyStateCard
              icon={Table2}
              title={upload ? "No question yet" : "No file yet"}
              description={
                upload
                  ? "Ask a question to see the answer, the generated SQL, and the result rows."
                  : "Upload a CSV or Excel file to get started."
              }
              feedbackSlot={<FeedbackButton demoType="tabular-agent" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
