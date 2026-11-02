"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  RAG_EXAMPLE_DOCUMENTS,
  RAG_EXAMPLE_ORGANISATION,
  RAG_EXAMPLE_QUESTION_TYPES,
} from "@/lib/rag-example";
import { cn } from "@/lib/utils";
import { ExternalLink, FileText, Loader2 } from "lucide-react";
import { useState } from "react";

interface RagExampleDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Loads the example. Not shown once the example is loaded. */
  onUse: () => void | Promise<void>;
  loading?: boolean;
  /** The example is already loaded: the dialog only explains it and shows the documents. */
  loaded?: boolean;
}

/** What the example is, its two documents (with a preview) and what to ask. */
export function RagExampleDialog({
  open,
  onOpenChange,
  onUse,
  loading = false,
  loaded = false,
}: RagExampleDialogProps) {
  const [selected, setSelected] = useState(0);
  const document = RAG_EXAMPLE_DOCUMENTS[selected];

  async function handleUse() {
    await onUse();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[92vw] max-w-5xl flex-col gap-4 sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Example: {RAG_EXAMPLE_ORGANISATION} documents
          </DialogTitle>
          <DialogDescription>
            Two documents of a fictional company, searched together.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1 text-sm">
          <section className="space-y-1.5">
            <h3 className="font-semibold">What this example does</h3>
            <p className="text-muted-foreground">
              It reads both documents, cuts them into searchable passages and
              stores them in an in-memory index. Each question finds the
              passages that fit best, from either document, and the answer names
              the document and page it came from. The documents were written for
              this test: {RAG_EXAMPLE_ORGANISATION} and everything in them is
              invented. They complement each other, so some questions need both.
            </p>
          </section>

          <section className="space-y-2">
            <h3 className="font-semibold">The documents</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {RAG_EXAMPLE_DOCUMENTS.map((doc, index) => (
                <button
                  key={doc.filename}
                  type="button"
                  onClick={() => setSelected(index)}
                  aria-pressed={selected === index}
                  className={cn(
                    "flex flex-col items-start justify-start rounded-lg border p-3 text-left transition-colors",
                    selected === index
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/50",
                  )}
                >
                  <p className="font-medium">{doc.title}</p>
                  <p className="text-muted-foreground text-xs">
                    {doc.kind}, PDF, {doc.pages} pages
                  </p>
                  <p className="text-muted-foreground mt-1.5">
                    {doc.description}
                  </p>
                  <p className="text-muted-foreground mt-1.5 text-xs">
                    {doc.topics.join(" · ")}
                  </p>
                </button>
              ))}
            </div>
            <div className="flex items-center justify-between gap-2">
              <p className="text-muted-foreground text-xs">
                Preview: {document.title}
              </p>
              <Button asChild variant="ghost" size="sm">
                <a
                  href={document.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Open in a new tab
                </a>
              </Button>
            </div>
            <iframe
              key={document.url}
              src={document.url}
              title={`Preview of ${document.title}`}
              className="bg-muted/30 h-[50vh] min-h-72 w-full rounded-md border"
            />
          </section>

          <section className="space-y-2">
            <h3 className="font-semibold">What you can ask</h3>
            <ul className="grid gap-2 sm:grid-cols-2">
              {RAG_EXAMPLE_QUESTION_TYPES.map((type) => (
                <li key={type.title} className="rounded-lg border p-3">
                  <p className="font-medium">{type.title}</p>
                  <p className="text-muted-foreground">{type.text}</p>
                  <p className="mt-1.5 italic">&ldquo;{type.example}&rdquo;</p>
                </li>
              ))}
            </ul>
          </section>

          <p className="text-muted-foreground text-xs">
            The documents are indexed with the parser chosen in Settings
            (Docling RAG by default). Vision+ reads only the first 10 pages of
            each document.
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {loaded ? "Close" : "Cancel"}
          </Button>
          {!loaded && (
            <Button onClick={() => void handleUse()} disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading...
                </>
              ) : (
                "Use this example"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
