"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FileUpload } from "@/components/demo/file-upload";
import { PageTransition } from "@/components/demo/page-transition";
import { EmptyStateCard, LoadingCard } from "@/components/demo/result-card";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch, RateLimitError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Database,
  Loader2,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  Table2,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { AnswerCard, type Asked, type AskResponse } from "./answer-card";
import {
  EXAMPLES,
  percent,
  type ExampleQuestion,
  type TabularExample,
} from "./tabular-data";

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

const GUIDE_STEPS: GuideStep[] = [
  {
    icon: Upload,
    title: "Load a file",
    text: "A CSV, Excel, Parquet or JSON file, or one of the examples. Each Excel sheet becomes its own table.",
  },
  {
    icon: Database,
    title: "Check what the agent sees",
    text: "The agent profiles every column: its type, its gaps and the values it really holds.",
  },
  {
    icon: MessageSquareText,
    title: "Ask in plain language",
    text: "Ask about totals, rankings, comparisons or trends, in any language the model reads.",
  },
  {
    icon: ShieldCheck,
    title: "Check the answer",
    text: "Read the answer, then the SQL behind it and the rows it came from. Sort them, chart them, download them.",
  },
];
const GUIDE_NOTES = [
  "The agent writes read-only SQL and runs it on your file in memory. It cannot change the file, and it does no calculations outside SQL. If the SQL fails it sees the error and tries again.",
  "Every question is answered on its own: the agent does not remember the earlier ones, so name what you mean. Your file is deleted when you close the session or leave the page.",
];

const OWN_FILE_QUESTIONS: ExampleQuestion[] = [
  { question: "How many rows are there in total?", shows: "counts" },
  {
    question: "Which category has the highest total?",
    shows: "groups and ranks",
  },
  { question: "Show the top 5 rows by value.", shows: "sorts and limits" },
  { question: "Are there any missing values?", shows: "checks the gaps" },
];

/** What the agent knows of each column of each table. */
function Profile({ tables }: { tables: TableInfo[] }) {
  return (
    <Tabs defaultValue={tables[0]?.name}>
      {tables.length > 1 && (
        <TabsList className="h-auto flex-wrap">
          {tables.map((table) => (
            <TabsTrigger key={table.name} value={table.name}>
              {table.name}
              <span className="text-muted-foreground ml-1.5 text-xs">
                {table.row_count}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
      )}
      {tables.map((table) => (
        <TabsContent
          key={table.name}
          value={table.name}
          className={cn(tables.length > 1 && "mt-3")}
        >
          <p className="text-muted-foreground mb-2 text-xs">
            {table.name}: {table.row_count.toLocaleString()} rows,{" "}
            {table.columns.length} columns
          </p>
          <div className="max-h-72 overflow-auto rounded-md border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted sticky top-0">
                <tr>
                  <th className="px-2.5 py-2 font-medium">Column</th>
                  <th className="px-2.5 py-2 font-medium">Type</th>
                  <th className="px-2.5 py-2 font-medium">Empty</th>
                  <th className="px-2.5 py-2 font-medium">Holds</th>
                </tr>
              </thead>
              <tbody>
                {table.columns.map((column) => (
                  <tr key={column.name} className="border-t align-top">
                    <td className="px-2.5 py-1.5 font-mono">{column.name}</td>
                    <td className="px-2.5 py-1.5">
                      <Badge
                        variant="secondary"
                        className="font-mono text-[10px] font-normal"
                      >
                        {column.data_type}
                      </Badge>
                    </td>
                    <td
                      className={cn(
                        "px-2.5 py-1.5",
                        column.null_fraction > 0 && "text-amber-700",
                      )}
                    >
                      {column.null_fraction > 0
                        ? percent(column.null_fraction)
                        : "–"}
                    </td>
                    <td className="text-muted-foreground px-2.5 py-1.5">
                      {column.min_value !== null && column.max_value !== null
                        ? `${column.min_value} … ${column.max_value}`
                        : column.top_values.length > 0
                          ? column.top_values.slice(0, 4).join(", ")
                          : column.samples.slice(0, 3).join(", ")}
                      <span className="ml-1 opacity-70">
                        · {column.distinct_count} distinct
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </TabsContent>
      ))}
    </Tabs>
  );
}

export default function TabularAgentPage() {
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [asked, setAsked] = useState<Asked[]>([]);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [example, setExample] = useState<TabularExample | null>(null);
  const uploadRequest = useRef(0);
  const counter = useRef(0);

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

  function discardSession(sessionId: string): void {
    void apiFetch(`/api/tabular-agent/session/${sessionId}`, {
      method: "DELETE",
    }).catch(() => undefined);
  }

  async function handleUpload(
    selected: File,
    fromExample: TabularExample | null = null,
  ): Promise<void> {
    // Only the latest upload may update the page; an older one that finishes
    // later drops its server session instead of overwriting the newer file.
    const request = ++uploadRequest.current;
    if (upload) discardSession(upload.session_id);
    setFile(selected);
    setExample(fromExample);
    setUpload(null);
    setAsked([]);
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
      if (request !== uploadRequest.current) {
        discardSession(data.session_id);
        return;
      }
      setUpload(data);
      posthog.capture("tabular_agent_upload", {
        tables: data.tables.length,
        rows: data.tables.reduce((n, t) => n + t.row_count, 0),
        example: fromExample?.id ?? null,
      });
    } catch (error) {
      if (error instanceof RateLimitError || request !== uploadRequest.current)
        return;
      setFile(null);
      setExample(null);
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      if (request === uploadRequest.current) setIsUploading(false);
    }
  }

  async function pickExample(next: TabularExample): Promise<void> {
    if (isUploading || isAsking) return;
    setIsUploading(true); // disables the drop zone and the cards during the fetch
    try {
      const response = await fetch(next.url);
      if (!response.ok) throw new Error("Could not load the example file");
      const blob = await response.blob();
      await handleUpload(
        new File([blob], next.fileName, { type: blob.type }),
        next,
      );
    } catch (error) {
      setIsUploading(false);
      toast.error(error instanceof Error ? error.message : "An error occurred");
    }
  }

  function handleRemove(): void {
    uploadRequest.current += 1; // an upload still in flight must not reappear
    if (upload) discardSession(upload.session_id);
    setIsUploading(false);
    setFile(null);
    setExample(null);
    setUpload(null);
    setAsked([]);
  }

  async function handleAsk(override?: string): Promise<void> {
    if (isAsking || !upload) return;
    const finalQuestion = (override ?? question).trim();
    if (!finalQuestion) {
      toast.error("Please enter a question");
      return;
    }

    setIsAsking(true);
    const started = performance.now();

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
      counter.current += 1;
      setAsked((previous) => [
        {
          id: counter.current,
          response: data,
          seconds: (performance.now() - started) / 1000,
        },
        ...previous,
      ]);
      setQuestion("");

      posthog.capture("tabular_agent_query", {
        succeeded: data.succeeded,
        attempts: data.attempts,
        row_count: data.row_count,
        example: example?.id ?? null,
      });
    } catch (error) {
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsAsking(false);
    }
  }

  const accept = status?.allowed_extensions.join(",") ?? ".csv,.xlsx,.xls";
  const maxSize = status?.max_file_size_mb ?? 20;
  const questions = example?.questions ?? OWN_FILE_QUESTIONS;
  const busy = isUploading || isAsking;

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Table2}
        title="Tabular Agent"
        description="Ask your own CSV or Excel file questions in plain language — the agent writes and runs read-only SQL"
        className="mb-6"
      />

      <div className="space-y-6">
        <SectionGuide
          heading="How to use the Tabular Agent"
          steps={GUIDE_STEPS}
          notes={GUIDE_NOTES}
        />

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Start from an example file</h2>
          <div
            role="radiogroup"
            aria-label="Example files"
            className="grid gap-3 md:grid-cols-3"
          >
            {EXAMPLES.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="radio"
                aria-checked={example?.id === entry.id}
                disabled={busy}
                onClick={() => void pickExample(entry)}
                className={cn(
                  "flex flex-col gap-1.5 rounded-xl border-2 p-3 text-left transition-all",
                  example?.id === entry.id
                    ? "border-primary bg-primary/5"
                    : "bg-card hover:border-primary/40",
                )}
              >
                <span className="font-semibold">{entry.title}</span>
                <span className="text-muted-foreground text-sm">
                  {entry.summary}
                </span>
                <span className="flex flex-wrap gap-1">
                  {entry.tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="font-normal">
                      {tag}
                    </Badge>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </section>

        <div className="grid items-start gap-6 md:gap-8 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>1. The data</CardTitle>
              <CardDescription>
                Upload your own file, or use an example above. Messy report
                sheets (title rows, subtotals, notes) are cleaned up.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FileUpload
                compact
                accept={accept}
                maxSize={maxSize}
                file={file}
                onFileSelect={(f) => void handleUpload(f)}
                onFileRemove={handleRemove}
                disabled={busy}
              />

              {isUploading && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading, cleaning up and profiling the columns…
                </p>
              )}

              {upload && (
                <div className="space-y-2">
                  <p className="text-sm font-semibold">What the agent sees</p>
                  <Profile tables={upload.tables} />
                  <p className="text-muted-foreground text-xs">
                    Types, gaps and real values stop the model from inventing
                    filters. A column with many empty cells is marked.
                  </p>
                </div>
              )}

              {status && !status.component_available && (
                <p className="text-destructive flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  The tabular agent is not available in this build.
                </p>
              )}
              {status &&
                status.component_available &&
                !status.llm_configured && (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    No LLM API key configured — questions cannot be answered.
                  </p>
                )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. Ask a question</CardTitle>
              <CardDescription>
                {upload
                  ? "Type your own, or click one of the questions below."
                  : "Load a file first."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
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
                    upload ? "Ask about your data…" : "Load a file first"
                  }
                  aria-label="Your question"
                  disabled={!upload || busy}
                />
                <Button
                  onClick={() => void handleAsk()}
                  disabled={!upload || busy || !question.trim()}
                >
                  {isAsking ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  {isAsking ? "Asking…" : "Ask"}
                </Button>
              </div>

              {upload && (
                <div className="space-y-2">
                  <p className="text-sm font-semibold">
                    {example ? "Questions to try" : "Some questions to start"}
                  </p>
                  <ul className="space-y-1.5">
                    {questions.map((entry) => (
                      <li key={entry.question}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleAsk(entry.question)}
                          className="hover:border-primary/40 hover:bg-muted/40 flex w-full flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-50"
                        >
                          <span className="text-sm">{entry.question}</span>
                          <span className="text-muted-foreground text-xs">
                            {entry.shows}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4" aria-live="polite">
          {isAsking && (
            <LoadingCard
              message="Answering your question…"
              subMessage="Generating and running SQL"
            />
          )}

          {asked.length > 0 && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold">Answers</h2>
                <Badge variant="outline" className="font-normal">
                  {asked.length}
                </Badge>
                <span className="text-muted-foreground text-xs">
                  The newest is first.
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => setAsked([])}
                >
                  <Trash2 />
                  Remove all
                </Button>
                <FeedbackButton demoType="tabular-agent" />
              </div>
              {asked.map((entry) => (
                <AnswerCard
                  key={entry.id}
                  asked={entry}
                  onRemove={() =>
                    setAsked((previous) =>
                      previous.filter((item) => item.id !== entry.id),
                    )
                  }
                />
              ))}
            </>
          )}

          {asked.length === 0 && !isAsking && (
            <EmptyStateCard
              icon={Wand2}
              title={upload ? "No question yet" : "No file yet"}
              description={
                upload
                  ? "Ask a question to see the answer, the SQL behind it, and the rows it came from."
                  : "Pick an example file, or upload a CSV or Excel file, to get started."
              }
              feedbackSlot={<FeedbackButton demoType="tabular-agent" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
