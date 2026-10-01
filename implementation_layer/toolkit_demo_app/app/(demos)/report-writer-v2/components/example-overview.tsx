"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  Download,
  FileAudio,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { effectiveId } from "../../report-writer/components/section-editor";
import type { useReportWriter } from "../use-report-writer";

type ReportWriter = ReturnType<typeof useReportWriter>;

interface Doc {
  name: string;
  group: "recording" | "document" | "sample";
  file: File | null;
}

const ext = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

function kindOf(name: string): {
  icon: LucideIcon;
  view: "audio" | "pdf" | "image" | "download";
  reads: string;
} {
  const e = ext(name);
  if (["mp3", "m4a", "wav", "ogg", "flac", "mp4", "webm"].includes(e))
    return {
      icon: FileAudio,
      view: "audio",
      reads: "A recording. Stage 1 transcribes it into text.",
    };
  if (e === "pdf")
    return {
      icon: FileText,
      view: "pdf",
      reads: "A PDF. Stage 1 parses it into text and keeps the page numbers.",
    };
  if (["png", "jpg", "jpeg", "webp", "gif"].includes(e))
    return {
      icon: FileImage,
      view: "image",
      reads: "An image. Stage 1 has a vision model describe it.",
    };
  if (["xlsx", "xls", "csv"].includes(e))
    return {
      icon: FileSpreadsheet,
      view: "download",
      reads: "A spreadsheet. Stage 1 reads it as tables, with the row numbers.",
    };
  return {
    icon: FileText,
    view: "download",
    reads: "A Word document. Stage 1 parses it into text.",
  };
}

const MIME: Record<string, string> = {
  pdf: "application/pdf",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  mp3: "audio/mpeg",
  m4a: "audio/mp4",
  wav: "audio/wav",
  ogg: "audio/ogg",
  flac: "audio/flac",
};

/** "rec1_exterior_attic.mp3" -> "Rec1 exterior attic". */
function labelOf(name: string): string {
  const base = name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
  return base.charAt(0).toUpperCase() + base.slice(1);
}

function Preview({ doc }: { doc: Doc }) {
  const kind = kindOf(doc.name);
  const [url, setUrl] = useState<string | null>(null);

  // A blob URL for the file, released when the file or the preview goes away.
  useEffect(() => {
    if (!doc.file) return;
    // The example files come without a type; the browser needs one to show a PDF or an image.
    const type = MIME[ext(doc.name)] ?? doc.file.type;
    const made = URL.createObjectURL(new Blob([doc.file], { type }));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the URL only exists once the effect has made it
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [doc.file, doc.name]);

  if (!doc.file || !url)
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin" />
        Loading the file…
      </p>
    );

  return (
    <div className="space-y-3">
      {kind.view === "audio" && (
        <audio key={url} controls src={url} className="w-full" />
      )}
      {kind.view === "pdf" && (
        <iframe
          title={doc.name}
          src={`${url}#toolbar=0`}
          className="h-[34rem] w-full rounded-lg border bg-white"
        />
      )}
      {kind.view === "image" && (
        // eslint-disable-next-line @next/next/no-img-element -- a local blob of the example file
        <img
          src={url}
          alt={labelOf(doc.name)}
          className="max-h-[34rem] w-auto rounded-lg border bg-white"
        />
      )}
      {kind.view === "download" && (
        <p className="text-muted-foreground text-sm">
          This file type has no preview here.
        </p>
      )}
      <Button asChild size="sm" variant="outline">
        <a href={url} download={doc.name}>
          <Download className="size-4" />
          Download {doc.name}
        </a>
      </Button>
    </div>
  );
}

/** The example before it runs: its sources to look at, and the report that will be written. */
export function ExampleOverview({ rw }: { rw: ReportWriter }) {
  const [selected, setSelected] = useState<string | null>(null);
  const example = rw.examples.find((e) => e.id === rw.loadedExampleId);

  const docs: Doc[] = [
    ...rw.sources.map((row) => ({
      name: row.name,
      group: (row.sourceClass === "primary"
        ? "recording"
        : "document") as Doc["group"],
      file: row.file,
    })),
    ...(rw.sample
      ? [
          {
            name: rw.sample.name,
            group: "sample" as const,
            file: rw.sample.file,
          },
        ]
      : []),
  ];
  const groups: { id: Doc["group"]; title: string; text: string }[] = [
    {
      id: "recording",
      title: "Site recordings",
      text: "Primary sources: the inspector's own observations.",
    },
    {
      id: "document",
      title: "Customer documents",
      text: "Secondary sources: older reports, a survey, a log and a plan.",
    },
    {
      id: "sample",
      title: "Sample report",
      text: "Gives the tone and layout. It gives no facts.",
    },
  ];
  const current = docs.find((doc) => doc.name === selected) ?? docs[0];

  if (!example || docs.length === 0)
    return (
      <Card>
        <CardContent className="text-muted-foreground flex items-center gap-2 pt-6 text-sm">
          <Loader2 className="size-4 animate-spin" />
          Loading the example…
        </CardContent>
      </Card>
    );

  return (
    <Card>
      <CardContent className="space-y-6 pt-6">
        <div className="space-y-1">
          <h3 className="font-serif text-xl font-semibold">{rw.title}</h3>
          <CardDescription>{example.description}</CardDescription>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <div className="space-y-4">
            {groups.map((group) => {
              const items = docs.filter((doc) => doc.group === group.id);
              if (items.length === 0) return null;
              return (
                <div key={group.id} className="space-y-2">
                  <div>
                    <h4 className="text-sm font-semibold">
                      {group.title}{" "}
                      <span className="text-muted-foreground font-normal">
                        ({items.length})
                      </span>
                    </h4>
                    <p className="text-muted-foreground text-xs">
                      {group.text}
                    </p>
                  </div>
                  <div
                    role="radiogroup"
                    aria-label={group.title}
                    className="space-y-1.5"
                  >
                    {items.map((doc) => {
                      const Icon = kindOf(doc.name).icon;
                      const active = doc.name === current.name;
                      return (
                        <button
                          key={doc.name}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          onClick={() => setSelected(doc.name)}
                          className={cn(
                            "flex w-full items-center gap-3 rounded-lg border-2 px-3 py-2 text-left transition-colors",
                            active
                              ? "border-primary bg-primary/5"
                              : "bg-card hover:border-primary/40",
                          )}
                        >
                          <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-md">
                            <Icon className="size-4" />
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">
                              {labelOf(doc.name)}
                            </span>
                            <span className="text-muted-foreground block truncate text-xs">
                              {doc.name}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="space-y-3 rounded-xl border p-4">
            <div>
              <h4 className="font-semibold">{labelOf(current.name)}</h4>
              <p className="text-muted-foreground text-sm">
                {current.group === "sample"
                  ? "A finished report whose layout and tone the new one copies."
                  : kindOf(current.name).reads}
              </p>
            </div>
            <Preview key={current.name} doc={current} />
          </div>
        </div>

        <div className="space-y-2 border-t pt-4">
          <h4 className="text-sm font-semibold">
            The report that will be written: {rw.sections.length} sections
          </h4>
          <ol className="grid gap-2 md:grid-cols-2">
            {rw.sections.map((section, index) => {
              const derived = section.depends_on.length > 0;
              return (
                <li
                  key={effectiveId(section)}
                  className="bg-card flex gap-3 rounded-lg border p-3"
                >
                  <span className="bg-primary/10 text-primary flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                    {index + 1}
                  </span>
                  <span className="min-w-0 space-y-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">
                        {section.title}
                      </span>
                      {derived && (
                        <Badge variant="outline" className="font-normal">
                          written from the other sections
                        </Badge>
                      )}
                    </span>
                    <span className="text-muted-foreground line-clamp-2 block text-xs">
                      {section.instructions}
                    </span>
                    {(section.required_items?.length ?? 0) > 0 && (
                      <span className="text-muted-foreground block text-xs">
                        Must cover {section.required_items!.length} items; any
                        that no source covers are marked as missing.
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
