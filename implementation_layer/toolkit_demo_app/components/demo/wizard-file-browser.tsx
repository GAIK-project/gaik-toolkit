"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ChevronRight,
  Circle,
  Download,
  File as FileIcon,
  FileArchive,
  Folder,
  Home,
} from "lucide-react";
import { useMemo, useState } from "react";

interface WizardFileBrowserProps {
  files: string[]; // flat list of POSIX relative paths, e.g. "docs/user_guide.md"
  sessionId: string | null;
}

/** What a complete run leaves behind, in the order the wizard writes it. */
const EXPECTED_ARTIFACTS = [
  { label: "Blueprint", detail: "blueprint.json — the validated configuration" },
  { label: "Workflow diagrams", detail: "Mermaid and BPMN 2.0" },
  { label: "Schema", detail: "The extraction contract, when the use case needs one" },
  { label: "Proof of concept", detail: "Runnable Python you can execute locally" },
  { label: "Documentation", detail: "User and developer guides" },
] as const;

interface DirListing {
  folders: string[];
  files: { name: string; full: string }[];
}

function listDir(files: string[], path: string[]): DirListing {
  const prefix = path.length ? path.join("/") + "/" : "";
  const folders = new Set<string>();
  const filesHere: { name: string; full: string }[] = [];
  for (const f of files) {
    if (!f.startsWith(prefix)) continue;
    const rest = f.slice(prefix.length);
    const slash = rest.indexOf("/");
    if (slash === -1) {
      filesHere.push({ name: rest, full: f });
    } else {
      folders.add(rest.slice(0, slash));
    }
  }
  return {
    folders: [...folders].sort((a, b) => a.localeCompare(b)),
    files: filesHere.sort((a, b) => a.name.localeCompare(b.name)),
  };
}

export function WizardFileBrowser({ files, sessionId }: WizardFileBrowserProps) {
  const [path, setPath] = useState<string[]>([]);

  // If files change and the current path no longer exists, reset to root.
  const listing = useMemo(() => listDir(files, path), [files, path]);
  const atRoot = path.length === 0;
  const isEmptyHere =
    listing.folders.length === 0 && listing.files.length === 0;

  const fileHref = (full: string) =>
    `/api/wizard/files/${sessionId}/${full}`;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Folder className="h-4 w-4" />
          Generated files
        </h2>
        {files.length > 0 && sessionId && (
          <a href={`/api/wizard/download/${sessionId}`}>
            <Button size="sm" variant="default" className="h-7 px-2 text-xs">
              <FileArchive className="mr-1 h-3.5 w-3.5" />
              .zip
            </Button>
          </a>
        )}
      </div>

      {/* Breadcrumb */}
      <div className="text-muted-foreground mb-2 flex flex-wrap items-center gap-0.5 text-xs">
        <button
          type="button"
          className="hover:text-foreground flex items-center gap-1"
          onClick={() => setPath([])}
        >
          <Home className="h-3 w-3" />
          root
        </button>
        {path.map((seg, i) => (
          <span key={i} className="flex items-center gap-0.5">
            <ChevronRight className="h-3 w-3" />
            <button
              type="button"
              className="hover:text-foreground"
              onClick={() => setPath(path.slice(0, i + 1))}
            >
              {seg}
            </button>
          </span>
        ))}
      </div>

      {/* Listing */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {files.length === 0 ? (
          // An empty panel for the first several minutes reads as broken. The
          // checklist says what is coming and in what order, so the wait has a
          // shape — and it doubles as an explanation of what a run produces.
          <div>
            <p className="text-muted-foreground mb-3 text-xs">
              Nothing generated yet. A full run produces:
            </p>
            <ul className="space-y-2">
              {EXPECTED_ARTIFACTS.map((a) => (
                <li key={a.label} className="flex items-start gap-2">
                  <Circle className="text-muted-foreground/40 mt-1 h-2.5 w-2.5 shrink-0" />
                  <span className="min-w-0">
                    <span className="text-foreground/70 block text-xs font-medium">
                      {a.label}
                    </span>
                    <span className="text-muted-foreground block text-[11px]">
                      {a.detail}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : isEmptyHere ? (
          <p className="text-muted-foreground text-xs">This folder is empty.</p>
        ) : (
          <ul className="space-y-0.5">
            {listing.folders.map((folder) => (
              <li key={`d/${folder}`}>
                <button
                  type="button"
                  onClick={() => setPath([...path, folder])}
                  className="hover:bg-muted flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs"
                >
                  <Folder className="text-primary h-3.5 w-3.5 shrink-0" />
                  <span className="truncate font-medium">{folder}</span>
                  <ChevronRight className="text-muted-foreground ml-auto h-3 w-3 shrink-0" />
                </button>
              </li>
            ))}
            {listing.files.map((f) => (
              <li key={`f/${f.full}`}>
                <a
                  href={fileHref(f.full)}
                  className={cn(
                    "hover:bg-muted group flex items-center gap-1.5 rounded px-1.5 py-1 text-xs",
                  )}
                >
                  <FileIcon className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{f.name}</span>
                  <Download className="text-muted-foreground ml-auto h-3 w-3 shrink-0 opacity-0 group-hover:opacity-100" />
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
