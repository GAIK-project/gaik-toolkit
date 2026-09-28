"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { STAGES, type Stage, type Staleness, staleHint } from "@/lib/report-writer/workspace";
import { Download, Eye, EyeOff, FileText, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";

import { DOCX_MIME, downloadBlob } from "./artifact-browser";

interface FinalReportCardProps {
  title: string;
  markdown: string | undefined;
  docx: Uint8Array<ArrayBuffer> | null;
  sectionCount: number;
  stale: Staleness;
  running: Stage | null;
  onRebuild: () => void;
}

/** The finished report: its state, downloads and a preview. */
export function FinalReportCard({
  title,
  markdown,
  docx,
  sectionCount,
  stale,
  running,
  onRebuild,
}: FinalReportCardProps) {
  const [preview, setPreview] = useState(false);
  const hint = staleHint(stale, "report/report.md");
  const name = title.replace(/[\\/:*?"<>|]+/g, "").trim() || "report";
  const ready = markdown !== undefined && !running;
  const words = markdown?.split(/\s+/).filter(Boolean).length ?? 0;

  const status = running ? (
    <Badge variant="outline" className="gap-1">
      <Loader2 className="h-3 w-3 animate-spin" />
      {running === "rebuild"
        ? "Rebuilding…"
        : `Writing… (stage ${STAGES.indexOf(running) + 1} of 3)`}
    </Badge>
  ) : markdown === undefined ? (
    <Badge variant="outline" className="text-muted-foreground">
      Not written yet
    </Badge>
  ) : hint ? (
    <Badge variant="outline" className="border-amber-500 text-amber-600">
      Out of date
    </Badge>
  ) : (
    <Badge className="bg-green-600 text-white hover:bg-green-600">Report ready</Badge>
  );

  return (
    <Card className={ready && !hint ? "border-green-600/50" : undefined}>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" />
            Final report
          </CardTitle>
          <CardDescription>
            {markdown === undefined
              ? "Run all to write the report."
              : `${sectionCount} sections · ${words.toLocaleString()} words`}
          </CardDescription>
        </div>
        {status}
      </CardHeader>
      <CardContent className="space-y-3">
        {ready && hint && (
          <div className="flex items-center justify-between gap-2 text-xs text-amber-600">
            <span>Inputs changed after this report was written. {hint} to update it.</span>
            {hint === "Rebuild report" && (
              <Button size="xs" variant="outline" onClick={onRebuild}>
                <RefreshCw className="h-3 w-3" />
                Rebuild report
              </Button>
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {ready && !docx ? (
            <p className="w-full text-xs text-muted-foreground">
              This run wrote no DOCX. Turn on Generate DOCX under Settings, then
              rebuild the report.
            </p>
          ) : (
            <Button
              className="flex-1"
              disabled={!ready}
              onClick={() => downloadBlob(docx!, `${name}.docx`, DOCX_MIME)}
            >
              <Download className="mr-2 h-4 w-4" />
              Download report (.docx)
            </Button>
          )}
          <Button
            variant="outline"
            disabled={!ready}
            onClick={() => downloadBlob(markdown!, `${name}.md`, "text/markdown")}
          >
            <Download className="mr-2 h-4 w-4" />
            .md
          </Button>
          <Button variant="outline" disabled={!ready} onClick={() => setPreview((p) => !p)}>
            {preview ? <EyeOff className="mr-2 h-4 w-4" /> : <Eye className="mr-2 h-4 w-4" />}
            Preview
          </Button>
        </div>
        {ready && preview && (
          <div className="max-h-[480px] overflow-y-auto rounded-md border p-3">
            <MessageResponse className="text-sm">{markdown}</MessageResponse>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
