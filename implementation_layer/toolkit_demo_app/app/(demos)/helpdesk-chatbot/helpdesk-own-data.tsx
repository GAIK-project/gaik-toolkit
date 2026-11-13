"use client";

import { FileUpload } from "@/components/demo/file-upload";
import { Button } from "@/components/ui/button";
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
import { spreadsheetToCsv } from "@/lib/helpdesk-chatbot/spreadsheet";
import {
  AlertTriangle,
  FileText,
  Loader2,
  Table2,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { HelpdeskChat } from "./helpdesk-chat";

const ACCEPT = ".md,.markdown,.txt,.csv,.xlsx,.pdf,.docx";
const MAX_FILE_MB = 10;

/** A fictional bicycle workshop: a FAQ and a price list, in public/. */
const SAMPLES = [
  { name: "sample-faq.md", href: "/helpdesk-chatbot/samples/sample-faq.md" },
  {
    name: "sample-price-list.csv",
    href: "/helpdesk-chatbot/samples/sample-price-list.csv",
  },
];
const SAMPLE_ORGANISATION = "Kaarna Cycle Workshop";
const SAMPLE_STARTERS = [
  "How much is a full service, and how long does it take?",
  "Can I get a bike while mine is in the workshop?",
  "Huolletteko sähköpyöriä?",
];

type Status = "reading" | "ready" | "error";

interface Entry {
  id: number;
  name: string;
  status: Status;
  doc?: LoadedDocument;
  error?: string;
  /** Set on a sample document: where its text can be opened. */
  href?: string;
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

/** Your own documents: add them, see what was read, ask the helpdesk about them. */
export function HelpdeskOwnData() {
  const [organisation, setOrganisation] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [uploadKey, setUploadKey] = useState(0);
  const [nextId, setNextId] = useState(1);
  const [loadingSamples, setLoadingSamples] = useState(false);
  const [sampleError, setSampleError] = useState(false);

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
  // Starter questions fit the samples only, so they show while nothing else is added.
  const onlySamples = entries.length > 0 && entries.every((e) => e.href);
  const example = useMemo(
    () =>
      knowledge
        ? {
            ...ownExample(knowledge),
            starters: onlySamples ? SAMPLE_STARTERS : [],
          }
        : null,
    [knowledge, onlySamples],
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

  async function addSamples() {
    setLoadingSamples(true);
    setSampleError(false);
    try {
      const loaded = await Promise.all(
        SAMPLES.map(async (sample) => {
          const response = await fetch(sample.href);
          if (!response.ok) throw new Error(sample.name);
          return {
            ...sample,
            doc: loadDocument(sample.name, await response.text()),
          };
        }),
      );
      const ready: Entry[] = loaded.map((sample, i) => ({
        id: nextId + i,
        name: sample.name,
        href: sample.href,
        status: "ready",
        doc: sample.doc,
      }));
      setNextId(nextId + ready.length);
      setEntries((list) => [...list, ...ready]);
      setOrganisation((name) => name || SAMPLE_ORGANISATION);
    } catch {
      setSampleError(true);
    } finally {
      setLoadingSamples(false);
    }
  }

  const full = entries.length >= LIMITS.documents;
  const hasSamples = entries.some((e) => e.href);
  const roomForSamples = entries.length + SAMPLES.length <= LIMITS.documents;

  return (
    <div className="space-y-4">
      <div className="bg-card grid gap-6 rounded-2xl border p-5 shadow-sm lg:grid-cols-2">
        <div className="space-y-4">
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
          {!hasSamples && roomForSamples && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="text-muted-foreground">No file at hand?</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void addSamples()}
                disabled={loadingSamples}
              >
                {loadingSamples ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <FileText />
                )}
                Use sample documents
              </Button>
              {sampleError && (
                <span className="text-destructive" role="alert">
                  The samples could not be loaded.
                </span>
              )}
            </div>
          )}
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
        </div>

        <div className="space-y-2" aria-live="polite">
          <h2 className="text-sm font-semibold">What was read</h2>
          {entries.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              Nothing yet. Add a FAQ or a guide, and a list of services or
              prices if you have one.
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
                      {entry.href ? (
                        <a
                          href={entry.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block truncate font-medium underline-offset-4 hover:underline"
                        >
                          {entry.name}
                        </a>
                      ) : (
                        <p className="truncate font-medium">{entry.name}</p>
                      )}
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
                      title="Remove"
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
        </div>
      </div>

      <p className="text-muted-foreground text-sm">
        Nothing is saved. The text of your documents is sent to the AI model
        with each question, so leave out personal data and confidential
        material. This is a basic test: the documents are read as they are, with
        no tuning for your use case.
      </p>

      {example && <HelpdeskChat key={revision} example={example} />}
    </div>
  );
}
