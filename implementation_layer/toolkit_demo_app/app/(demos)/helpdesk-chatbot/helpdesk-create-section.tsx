"use client";

import { FileUpload } from "@/components/demo/file-upload";
import { SectionGuide } from "@/components/demo/section-guide";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api-client";
import {
  LIMITS,
  buildKnowledge,
  loadDocument,
  ownExample,
  type LoadedDocument,
} from "@/lib/helpdesk-chatbot/own-knowledge";
import {
  AlertTriangle,
  ArrowRight,
  FileText,
  Info,
  Loader2,
  Table2,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { spreadsheetToCsv } from "@/lib/helpdesk-chatbot/spreadsheet";
import Link from "next/link";
import { useMemo, useState } from "react";
import { HelpdeskChat } from "./helpdesk-chat";

const ACCEPT = ".md,.markdown,.txt,.csv,.xlsx,.pdf,.docx";
const MAX_FILE_MB = 10;

const STEPS = [
  {
    title: "Add your documents",
    text: "A FAQ, guides or policies as Markdown, text, PDF or Word, and a list of your services, products or requests as CSV or Excel.",
  },
  {
    title: "Check what was read",
    text: "See how many articles and catalogue entries were found. Remove a file to leave it out.",
  },
  {
    title: "Ask questions",
    text: "The assistant answers only from your documents and shows the entries it used.",
  },
];

const NOTES = [
  "Nothing is saved. Your documents stay in this browser session, and their text is sent to the AI model with each question. Do not upload personal data or confidential material.",
  "A CSV or Excel list (each sheet is read as its own list) needs a column for the name (name, product, service, title or item). Columns such as category, price, description and availability are recognised by their names; other columns are added to the details.",
];

const USE_CASES = [
  {
    title: "Product or price catalogue",
    text: "Find the right product, a size or a price, and compare options. Use a PDF, or a CSV or Excel list with one row per product.",
  },
  {
    title: "Customer FAQ and policies",
    text: "Delivery, returns, warranty, opening hours, payment and similar questions. Use Markdown, text, Word or PDF.",
  },
  {
    title: "Internal helpdesk",
    text: "IT, HR or office guides and policies that staff ask about. Use Markdown, text, Word or PDF.",
  },
  {
    title: "Service, course or event list",
    text: "What is offered, for whom, when and at what price. Use a CSV or Excel list, or a document with a section for each.",
  },
];

/** What fits this test, and where to go for a tailored solution. */
function Guidance() {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">What you can test here</h3>
        <p className="text-muted-foreground text-sm">
          A helpdesk that answers questions from documents about products,
          services, rules or instructions. Any of these fit:
        </p>
        <ul className="grid gap-2 sm:grid-cols-2">
          {USE_CASES.map((item) => (
            <li
              key={item.title}
              className="bg-muted/30 rounded-lg border p-3 text-sm"
            >
              <p className="font-medium">{item.title}</p>
              <p className="text-muted-foreground">{item.text}</p>
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground text-sm">
          Documents work best with short, clearly titled sections or a question
          for each topic. Scanned pages that are only images of text may not be
          read.
        </p>
      </div>

      <div
        className="flex flex-col gap-3 rounded-lg border border-amber-300/60 bg-amber-50 p-4 text-sm sm:flex-row sm:items-center dark:border-amber-700/50 dark:bg-amber-950/20"
        role="note"
      >
        <Info className="size-5 shrink-0 text-amber-700 dark:text-amber-400" />
        <p className="flex-1">
          <span className="font-medium">This is a basic test.</span> It reads
          your documents as they are, without analysing your requirements, so
          the wording, structure and accuracy are general. If your use case is
          different, or you want better accuracy, use the Solution Configuration
          Wizard: it collects your complete requirements and builds a solution
          for them.
        </p>
        <Link
          href="/solution-wizard"
          className="text-primary inline-flex shrink-0 items-center gap-1 font-medium hover:underline"
        >
          Open the Solution Wizard
          <ArrowRight className="size-4" />
        </Link>
      </div>
    </div>
  );
}

type Status = "reading" | "ready" | "error";

interface Entry {
  id: number;
  name: string;
  status: Status;
  doc?: LoadedDocument;
  error?: string;
}

/** The text of a file: Markdown, text and CSV are read here; PDF and Word by the backend parser. */
async function readText(file: File): Promise<string> {
  if (/\.(md|markdown|txt|csv)$/i.test(file.name)) return file.text();
  const form = new FormData();
  form.append("file", file);
  form.append("parser_type", "auto");
  const response = await apiFetch("/api/parse", { method: "POST", body: form });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "The document could not be read.",
    );
  }
  const data = (await response.json()) as { text_content?: string };
  return String(data.text_content ?? "");
}

function describe(doc: LoadedDocument): string {
  const parts: string[] = [];
  if (doc.articles.length)
    parts.push(
      `${doc.articles.length} ${doc.articles.length === 1 ? "article" : "articles"}`,
    );
  if (doc.services.length)
    parts.push(
      `${doc.services.length} catalogue ${doc.services.length === 1 ? "entry" : "entries"}`,
    );
  return parts.join(", ") || "nothing readable";
}

/** Test on your own data: add documents, see what was read, ask the assistant about them. */
export function HelpdeskCreateSection() {
  const [organisation, setOrganisation] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [uploadKey, setUploadKey] = useState(0);
  const [nextId, setNextId] = useState(1);

  const docs = useMemo(
    () =>
      entries.flatMap((e) => (e.status === "ready" && e.doc ? [e.doc] : [])),
    [entries],
  );
  const usable = docs.filter((d) => d.articles.length + d.services.length > 0);

  const knowledge = useMemo(
    () =>
      usable.length > 0
        ? buildKnowledge(organisation || "Your organisation", usable)
        : null,
    [usable, organisation],
  );
  const example = useMemo(
    () => (knowledge ? ownExample(knowledge) : null),
    [knowledge],
  );
  // A new key starts a new conversation whenever the documents or the name change.
  const revision = `${organisation}|${usable.map((d) => `${d.name}:${d.articles.length}:${d.services.length}`).join(",")}`;

  async function addFile(file: File) {
    const id = nextId;
    setNextId(id + 1);
    setUploadKey((k) => k + 1); // empties the upload zone for the next file
    setEntries((list) => [...list, { id, name: file.name, status: "reading" }]);
    try {
      if (/\.xlsx$/i.test(file.name)) {
        // Each sheet of a workbook becomes its own list, read as CSV.
        const sheets = await spreadsheetToCsv(file);
        if (sheets.length === 0) throw new Error("The workbook has no data.");
        let next = id + 1;
        const ready: Entry[] = sheets.map((sheet, i) => ({
          id: i === 0 ? id : next++,
          name: sheet.name,
          status: "ready",
          doc: loadDocument(sheet.name, sheet.text),
        }));
        setNextId(next);
        setEntries((list) => list.flatMap((e) => (e.id === id ? ready : [e])));
        return;
      }
      const doc = loadDocument(file.name, await readText(file));
      setEntries((list) =>
        list.map((e) => (e.id === id ? { ...e, status: "ready", doc } : e)),
      );
    } catch (error) {
      setEntries((list) =>
        list.map((e) =>
          e.id === id
            ? {
                ...e,
                status: "error",
                error:
                  error instanceof Error
                    ? error.message
                    : "The document could not be read.",
              }
            : e,
        ),
      );
    }
  }

  const full = entries.length >= LIMITS.documents;

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to test your own data"
        steps={STEPS}
        notes={NOTES}
      />

      <Card>
        <CardContent className="space-y-6 pt-6">
          <CardDescription>
            Build a helpdesk from your own documents: it answers questions from
            them, names its sources, and passes a question to a person when the
            documents do not answer it.
          </CardDescription>

          <Guidance />

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="helpdesk-organisation">
                  Name of your organisation (optional)
                </Label>
                <Input
                  id="helpdesk-organisation"
                  value={organisation}
                  maxLength={LIMITS.organisationChars}
                  placeholder="Your organisation"
                  onChange={(e) => setOrganisation(e.target.value)}
                />
              </div>
              <FileUpload
                key={uploadKey}
                accept={ACCEPT}
                maxSize={MAX_FILE_MB}
                file={null}
                disabled={full}
                onFileSelect={(file) => void addFile(file)}
              />
              {full && (
                <p className="text-muted-foreground text-sm">
                  The limit is {LIMITS.documents} documents. Remove one to add
                  another.
                </p>
              )}
            </div>

            <div className="space-y-2" aria-live="polite">
              <h3 className="text-sm font-semibold">What was read</h3>
              {entries.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Nothing yet. Add a document to begin.
                </p>
              ) : (
                <ul className="space-y-2">
                  {entries.map((entry) => {
                    const Icon: LucideIcon = /\.csv$/i.test(entry.name)
                      ? Table2
                      : FileText;
                    return (
                      <li
                        key={entry.id}
                        className="bg-muted/30 flex items-start gap-3 rounded-lg border p-3 text-sm"
                      >
                        <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium">{entry.name}</p>
                          {entry.status === "reading" && (
                            <p className="text-muted-foreground flex items-center gap-1.5">
                              <Loader2 className="size-3.5 animate-spin" />
                              Reading…
                            </p>
                          )}
                          {entry.status === "error" && (
                            <p
                              className="text-destructive flex items-start gap-1.5"
                              role="alert"
                            >
                              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                              {entry.error}
                            </p>
                          )}
                          {entry.status === "ready" && entry.doc && (
                            <>
                              <p className="text-muted-foreground">
                                {describe(entry.doc)}
                              </p>
                              {entry.doc.warnings.map((warning) => (
                                <p
                                  key={warning}
                                  className="mt-0.5 text-amber-700 dark:text-amber-400"
                                >
                                  {warning}
                                </p>
                              ))}
                            </>
                          )}
                        </div>
                        <button
                          type="button"
                          aria-label={`Remove ${entry.name}`}
                          onClick={() =>
                            setEntries((list) =>
                              list.filter((e) => e.id !== entry.id),
                            )
                          }
                          className="text-muted-foreground hover:text-destructive shrink-0 rounded p-1"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              {knowledge && (
                <p className="text-muted-foreground pt-1 text-sm">
                  Your helpdesk knows {knowledge.articles.length}{" "}
                  {knowledge.articles.length === 1 ? "article" : "articles"} and{" "}
                  {knowledge.services.length} catalogue{" "}
                  {knowledge.services.length === 1 ? "entry" : "entries"}.
                </p>
              )}
            </div>
          </div>

          {example && <HelpdeskChat key={revision} example={example} />}
        </CardContent>
      </Card>
    </div>
  );
}
