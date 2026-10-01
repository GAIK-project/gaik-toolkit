"use client";

import { EmptyStateCard } from "@/components/demo/result-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { STAGES } from "@/lib/report-writer/workspace";
import { FilePen } from "lucide-react";
import { effectiveId } from "../../report-writer/components/section-editor";
import { STAGE_LABELS, type useReportWriter } from "../use-report-writer";
import { ArtifactBrowser } from "./artifact-browser";
import { EvidenceView } from "./evidence-view";
import { FinalReportCard } from "./final-report-card";

type ReportWriter = ReturnType<typeof useReportWriter>;

/** What a run produces: the report, the evidence behind it, and every file of the workspace. */
export function ReportResults({
  rw,
  emptyText,
}: {
  rw: ReportWriter;
  /** Shown while there is no workspace. Nothing is shown when omitted. */
  emptyText?: string;
}) {
  if (rw.paths.length === 0) {
    return emptyText ? (
      <EmptyStateCard
        icon={FilePen}
        title="No report yet"
        description={emptyText}
      />
    ) : null;
  }

  const sectionCount = Object.keys(rw.artifacts).filter((path) =>
    path.startsWith("report/sections/"),
  ).length;
  const hasEvidence = Object.keys(rw.artifacts).some((path) =>
    path.startsWith("knowledge/"),
  );

  return (
    <div className="space-y-4">
      <FinalReportCard
        title={rw.title}
        markdown={rw.artifacts["report/report.md"]}
        docx={rw.docx}
        sectionCount={sectionCount}
        stale={rw.stale}
        running={rw.running}
        onRebuild={() => rw.run(["rebuild"])}
        defaultPreview
      />

      {/* Starts on the evidence once there is some, whichever stage was reached first. */}
      <Tabs
        key={hasEvidence ? "evidence" : "files"}
        defaultValue={hasEvidence ? "evidence" : "files"}
      >
        <TabsList>
          <TabsTrigger value="evidence">Evidence by section</TabsTrigger>
          <TabsTrigger value="files">Workspace files</TabsTrigger>
          {Object.keys(rw.usage).length > 0 && (
            <TabsTrigger value="usage">Token usage</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="evidence" className="pt-4">
          <EvidenceView
            sections={rw.sections}
            artifacts={rw.artifacts}
            disabled={rw.busy}
            onSave={rw.saveArtifact}
            outOfDate={rw.stale.report}
            onDropRequirement={(sectionId, item) =>
              rw.setSections(
                rw.sections.map((section) =>
                  effectiveId(section) === sectionId
                    ? {
                        ...section,
                        required_items: (section.required_items ?? []).filter(
                          (required) => required.trim() !== item.trim(),
                        ),
                      }
                    : section,
                ),
              )
            }
          />
        </TabsContent>

        <TabsContent value="files" className="space-y-3 pt-4">
          <p className="text-muted-foreground text-sm">
            Every stage saves its result as files. Read them, and correct the
            knowledge files and the section texts before the next stage runs.
          </p>
          <ArtifactBrowser
            artifacts={rw.artifacts}
            docx={rw.docx}
            stale={rw.stale}
            disabled={rw.busy}
            onSave={rw.saveArtifact}
          />
        </TabsContent>

        <TabsContent value="usage" className="pt-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Token usage</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-xs">
              {STAGES.filter((stage) => rw.usage[stage]).map((stage) => (
                <p key={stage}>
                  <span className="font-medium">{STAGE_LABELS[stage]}:</span>{" "}
                  {Object.entries(rw.usage[stage]!)
                    .map(([key, value]) => `${key} ${value.toLocaleString()}`)
                    .join(" · ") || "no token counts reported"}
                </p>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
