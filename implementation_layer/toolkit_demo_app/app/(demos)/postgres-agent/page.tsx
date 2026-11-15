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
        description="Ask a database in plain language. The agent writes and runs read-only SQL."
      />

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        {/* Input Section */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Ask the demo database</CardTitle>
              <CardDescription>
                A sample database of customers and orders. Nothing is written to
                it.
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

              <div
                role="group"
                aria-label="Example questions"
                className="flex flex-wrap gap-2"
              >
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    disabled={isLoading}
                    onClick={() => handleExample(q)}
                    className="hover:border-primary/40 hover:bg-primary/5 focus-visible:ring-ring/50 rounded-full border px-3 py-1.5 text-left text-sm transition-colors outline-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>

              {status && !status.database_configured && (
                <p className="text-destructive flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  The demo database is not configured on this server.
                </p>
              )}
              {status &&
                status.database_configured &&
                !status.llm_configured && (
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
              title="Tables the agent can query"
              copyContent={schema.schema_text}
            >
              <ResultText content={schema.schema_text} maxHeight="240px" />
            </ResultCard>
          )}

          <HowItWorksCard description="The agent reads the schema, writes one read-only query, runs it and explains the rows.">
            <p>
              <strong>Schema:</strong> tables, columns, primary and foreign keys
              are read from the database.
            </p>
            <p>
              <strong>SQL:</strong> a model writes a single <code>SELECT</code>.
              Anything that writes or changes the schema is refused, and a
              failed query is retried with its error.
            </p>
            <p>
              <strong>Answer:</strong> the rows are summarised in plain
              language, with the SQL and the rows shown beside it.
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
              description="The answer, the SQL and the rows show here."
              feedbackSlot={<FeedbackButton demoType="postgres-agent" />}
            />
          )}
        </div>
      </div>
    </PageTransition>
  );
}
