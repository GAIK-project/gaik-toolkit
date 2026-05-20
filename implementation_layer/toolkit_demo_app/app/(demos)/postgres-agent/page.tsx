"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
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
import { AlertTriangle, Database, Sparkles } from "lucide-react";
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

interface SchemaColumn {
  name: string;
  data_type: string;
  is_primary_key: boolean;
  references: string | null;
}

interface SchemaTable {
  name: string;
  columns: SchemaColumn[];
}

interface SchemaResponse {
  schema_name: string;
  schema_text: string;
  tables: SchemaTable[];
}

interface StatusResponse {
  database_configured: boolean;
  llm_configured: boolean;
  demo_schema: string;
  demo_tables: string[];
}

const EXAMPLE_QUESTIONS = [
  "How many orders did each customer place?",
  "Which customer has spent the most money in total?",
  "List all customers from Helsinki.",
  "What is the average order amount?",
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

export default function PostgresAgentPage() {
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function loadInfo(): Promise<void> {
      try {
        const statusRes = await apiFetch("/api/postgres-agent/status");
        if (statusRes.ok) setStatus(await statusRes.json());

        const schemaRes = await apiFetch("/api/postgres-agent/schema");
        if (schemaRes.ok) {
          setSchema(await schemaRes.json());
        } else {
          const e = await schemaRes.json().catch(() => null);
          setLoadError(e?.detail ?? "Could not load the demo database schema.");
        }
      } catch {
        setLoadError("Could not reach the backend.");
      }
    }
    void loadInfo();
  }, []);

  async function handleAsk(override?: string): Promise<void> {
    if (isLoading) return;
    const finalQuestion = (override ?? question).trim();
    if (!finalQuestion) {
      toast.error("Please enter a question");
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const response = await apiFetch("/api/postgres-agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: finalQuestion }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to query the database");
      }

      const data: AskResponse = await response.json();
      setResult(data);

      posthog.capture("postgres_agent_query", {
        succeeded: data.succeeded,
        attempts: data.attempts,
        row_count: data.row_count,
      });

      if (data.succeeded) {
        toast.success("Query completed");
      }
    } catch (error) {
      if (error instanceof RateLimitError) {
        return;
      }
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  function handleExample(q: string): void {
    setQuestion(q);
    void handleAsk(q);
  }

  return (
    <PageTransition>
      <DemoPageHeader
        icon={Database}
        title="PostgreSQL Agent"
        description="Ask a database questions in plain language — the agent writes and runs read-only SQL"
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Ask the demo database</CardTitle>
              <CardDescription>
                A fixed sample database of customers and orders. Your question is
                turned into a safe, read-only SQL query — no writes, one schema.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {schema && (
                <div className="flex flex-wrap gap-2">
                  {schema.tables.map((t) => (
                    <Badge key={t.name} variant="secondary">
                      {t.name} · {t.columns.length} columns
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
                  placeholder="e.g. Which customer spent the most?"
                  disabled={isLoading}
                />
                <Button
                  onClick={() => void handleAsk()}
                  disabled={isLoading || !question.trim()}
                >
                  <Sparkles className="mr-2 h-4 w-4" />
                  {isLoading ? "Asking..." : "Ask"}
                </Button>
              </div>

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
                      onClick={() => !isLoading && handleExample(q)}
                    >
                      {q}
                    </Badge>
                  ))}
                </div>
              </div>

              {status && !status.database_configured && (
                <p className="text-destructive flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  The demo database is not configured on this server.
                </p>
              )}
              {status && status.database_configured && !status.llm_configured && (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  No LLM API key configured — questions cannot be answered.
                </p>
              )}
              {loadError && (
                <p className="text-muted-foreground text-sm">{loadError}</p>
              )}
            </CardContent>
          </Card>

          {schema && (
            <ResultCard
              title="Demo database schema"
              description="The tables and columns the agent can query"
              copyContent={schema.schema_text}
            >
              <ResultText content={schema.schema_text} maxHeight="240px" />
            </ResultCard>
          )}

          <HowItWorksCard description="The agent introspects the schema, generates validated read-only SQL, runs it, and explains the result.">
            <p>
              <strong>1. Pick or type a question:</strong> Ask anything about the
              customers and orders in the demo database.
            </p>
            <p>
              <strong>2. Schema introspection:</strong> The agent reads the
              database structure — tables, columns, primary and foreign keys.
            </p>
            <p>
              <strong>3. SQL generation:</strong> An LLM turns your question into
              a single read-only <code>SELECT</code> query.
            </p>
            <p>
              <strong>4. Safe execution:</strong> The SQL is validated (read-only
              only, no writes or DDL) and run. If it fails, the agent feeds the
              error back and retries.
            </p>
            <p>
              <strong>5. Plain-language answer:</strong> The result rows are
              summarized into a natural-language answer you can read directly.
            </p>
          </HowItWorksCard>
        </div>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && (
            <LoadingCard
              message="Querying the database..."
              subMessage="Generating and running SQL"
            />
          )}

          {result && !isLoading && (
            <>
              <ResultCard
                title="Answer"
                description={`Question: ${result.question}`}
                copyContent={result.answer}
                feedbackSlot={<FeedbackButton demoType="postgres-agent" />}
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

          {!result && !isLoading && (
            <EmptyStateCard
              icon={Database}
              title="No query yet"
              description="Ask a question to see the answer, the generated SQL, and the result rows."
              feedbackSlot={<FeedbackButton demoType="postgres-agent" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
