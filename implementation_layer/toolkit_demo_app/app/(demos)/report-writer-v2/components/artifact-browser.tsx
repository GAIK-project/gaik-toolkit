"use client";

import { MessageResponse } from "@/components/ai-elements/message";
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
import { Textarea } from "@/components/ui/textarea";
import {
  DOCX_PATH,
  type Staleness,
  classifyArtifact,
  groupArtifacts,
  knowledgeJsonError,
  staleHint,
  zipWorkspace,
} from "@/lib/report-writer/workspace";
import { cn } from "@/lib/utils";
import { Download, FileArchive, FileText, Folder, Pencil } from "lucide-react";
import { useState } from "react";

export const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function downloadBlob(data: BlobPart, name: string, type = "") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const FOLDER_NOTE: Record<string, string> = {
  normalized: "parsed sources, view only",
  knowledge: "curated facts per section, editable",
  report: "sections editable, the rest view only",
};

function ArtifactView({ path, text }: { path: string; text: string }) {
  if (!path.endsWith(".json"))
    return <MessageResponse className="text-sm">{text}</MessageResponse>;
  let pretty: string;
  try {
    pretty = JSON.stringify(JSON.parse(text), null, 2);
  } catch (e) {
    return (
      <p className="text-xs text-destructive">
        This file is not valid JSON: {e instanceof Error ? e.message : String(e)}
      </p>
    );
  }
  return (
    <pre className="text-xs whitespace-pre-wrap break-words font-mono leading-relaxed">
      {pretty}
    </pre>
  );
}

export function ArtifactBrowser({
  artifacts,
  docx,
  stale,
  disabled,
  onSave,
}: {
  artifacts: Record<string, string>;
  docx: Uint8Array<ArrayBuffer> | null;
  stale: Staleness;
  disabled: boolean;
  onSave: (path: string, text: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  // The text an edit started from, so a save never overwrites a newer stage result.
  const [edit, setEdit] = useState<{ base: string; draft: string } | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const paths = [...Object.keys(artifacts), ...(docx ? [DOCX_PATH] : [])];
  const text = selected === null ? undefined : artifacts[selected];
  const editable = text !== undefined && classifyArtifact(selected!).editable;
  const hint = selected && staleHint(stale, selected);

  function select(path: string) {
    if (path === DOCX_PATH) return downloadBlob(docx!, "report.docx", DOCX_MIME);
    setSelected(path);
    setEdit(null);
    setEditError(null);
  }

  function download(path: string) {
    if (path === DOCX_PATH) return downloadBlob(docx!, "report.docx", DOCX_MIME);
    downloadBlob(artifacts[path], path.split("/").pop()!, "text/plain");
  }

  function save() {
    if (!selected || !edit) return;
    if (artifacts[selected] !== edit.base)
      return setEditError(
        "A stage rewrote this file after you started editing. Cancel and edit again.",
      );
    if (classifyArtifact(selected).kind === "knowledge") {
      const err = knowledgeJsonError(edit.draft);
      if (err) return setEditError(`Invalid JSON, not saved: ${err}`);
    }
    onSave(selected, edit.draft);
    setEdit(null);
    setEditError(null);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-3">
        <div>
          <CardTitle className="text-base">Workspace</CardTitle>
          <CardDescription>
            Each stage reads and rewrites these files. Edit knowledge or section
            files between stages.
          </CardDescription>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              downloadBlob(
                new Uint8Array(zipWorkspace(artifacts, docx)),
                "workspace.zip",
                "application/zip",
              )
            }
          >
            <FileArchive className="mr-1 h-3.5 w-3.5" />
            Download all (.zip)
          </Button>
          <FeedbackButton demoType="report-writer-v2" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {groupArtifacts(paths).map((g) => (
          <div key={g.folder || "root"}>
            {g.folder && (
              <p className="mb-1 flex items-center gap-1.5 text-xs font-medium">
                <Folder className="h-3.5 w-3.5 text-primary" />
                {g.folder}/
                <span className="font-normal text-muted-foreground">
                  ({FOLDER_NOTE[g.folder]})
                </span>
              </p>
            )}
            <ul className="space-y-0.5">
              {g.paths.map((p) => {
                const rowHint = staleHint(stale, p);
                return (
                  <li
                    key={p}
                    className={cn(
                      "flex items-center gap-1.5 rounded px-1.5 py-1 text-xs hover:bg-muted",
                      p === selected && "bg-muted",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => select(p)}
                      className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                    >
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate font-mono">
                        {g.folder ? p.slice(g.folder.length + 1) : p}
                      </span>
                      {p !== DOCX_PATH && classifyArtifact(p).editable && (
                        <Pencil className="h-3 w-3 shrink-0 text-muted-foreground" />
                      )}
                    </button>
                    {rowHint && (
                      <Badge variant="outline" className="border-amber-500 text-[10px] text-amber-600" title={rowHint}>
                        stale
                      </Badge>
                    )}
                    <button
                      type="button"
                      title="Download"
                      onClick={() => download(p)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}

        {selected && text !== undefined && (
          <div className="rounded-md border">
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <span className="flex-1 truncate font-mono text-xs">{selected}</span>
              {hint && (
                <Badge variant="outline" className="border-amber-500 text-xs text-amber-600">
                  Stale: {hint}
                </Badge>
              )}
              {editable && !edit && (
                <Button
                  size="xs"
                  variant="outline"
                  disabled={disabled}
                  onClick={() => setEdit({ base: text, draft: text })}
                >
                  <Pencil />
                  Edit
                </Button>
              )}
            </div>
            {edit ? (
              <div className="space-y-2 p-3">
                <Textarea
                  value={edit.draft}
                  onChange={(e) => setEdit({ ...edit, draft: e.target.value })}
                  className="min-h-[320px] font-mono text-xs"
                />
                {editError && <p className="text-xs text-destructive">{editError}</p>}
                <div className="flex gap-2">
                  <Button size="sm" onClick={save} disabled={disabled}>
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEdit(null);
                      setEditError(null);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="max-h-[480px] overflow-y-auto p-3">
                <ArtifactView path={selected} text={text} />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
