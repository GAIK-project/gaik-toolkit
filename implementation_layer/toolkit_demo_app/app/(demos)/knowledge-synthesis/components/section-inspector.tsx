"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { SectionKnowledge } from "@/lib/knowledge-curator/workspace";
import type {
  ReportSection,
  ReviewEdit,
  ReviewEntry,
} from "@/lib/knowledge-synthesis/workspace";
import { Pencil, Undo2 } from "lucide-react";
import { useState } from "react";

import { SectionView } from "../../knowledge-curator/components/section-view";

function EditList({ edits, empty }: { edits: ReviewEdit[]; empty: string }) {
  if (edits.length === 0)
    return <p className="text-muted-foreground text-xs">{empty}</p>;
  return (
    <ul className="space-y-2">
      {edits.map((e, i) => (
        <li key={i} className="space-y-1 rounded border px-2 py-1.5 text-xs">
          <p className="text-muted-foreground">{e.reason}</p>
          <p>
            <span className="rounded bg-red-100 px-1 text-red-900 line-through">
              {e.search}
            </span>{" "}
            {e.replace ? (
              <span className="rounded bg-green-100 px-1 text-green-900">
                {e.replace}
              </span>
            ) : (
              <span className="text-muted-foreground">(deleted)</span>
            )}
          </p>
        </li>
      ))}
    </ul>
  );
}

/** One report section: its text (editable), where its facts came from, and what the reviewer changed. */
export function SectionInspector({
  section,
  original,
  derived,
  knowledge,
  prerequisites,
  review,
  citations,
  disabled,
  onSaveText,
  onResetText,
}: {
  section: ReportSection;
  original: string;
  derived: boolean;
  knowledge: SectionKnowledge | null;
  prerequisites: { id: string; title: string }[];
  review: ReviewEntry | undefined;
  citations: boolean;
  disabled: boolean;
  onSaveText: (id: string, text: string) => void;
  onResetText: (id: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const edited = section.text !== original;
  const missing = (section.text.match(/\(missing:/g) ?? []).length;

  return (
    <div className="rounded-md border">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className="flex-1 truncate text-sm font-medium">
          {section.title}
        </span>
        <Badge variant="outline" className="text-[10px]">
          {derived ? "derived" : "from knowledge"}
        </Badge>
        {missing > 0 && (
          <Badge
            variant="outline"
            className="border-amber-500 text-[10px] text-amber-600"
          >
            {missing} missing marker{missing === 1 ? "" : "s"}
          </Badge>
        )}
        {edited && (
          <Badge
            variant="outline"
            className="border-amber-500 text-[10px] text-amber-600"
          >
            edited
          </Badge>
        )}
      </div>

      <Tabs defaultValue="text" className="p-3">
        <TabsList>
          <TabsTrigger value="text">Text</TabsTrigger>
          <TabsTrigger value="source">
            {derived ? "Written from" : "Facts used"}
          </TabsTrigger>
          <TabsTrigger value="review">
            Review
            {review && review.applied.length + review.unresolved.length > 0 && (
              <span className="text-muted-foreground ml-1">
                ({review.applied.length + review.unresolved.length})
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="text" className="space-y-2 pt-2">
          {draft === null ? (
            <>
              <div className="max-h-[360px] overflow-y-auto rounded border p-3">
                <MessageResponse className="text-sm">
                  {section.text}
                </MessageResponse>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="xs"
                  variant="outline"
                  disabled={disabled}
                  onClick={() => setDraft(section.text)}
                >
                  <Pencil />
                  Edit text
                </Button>
                {edited && (
                  <Button
                    size="xs"
                    variant="ghost"
                    disabled={disabled}
                    onClick={() => onResetText(section.id)}
                  >
                    <Undo2 />
                    Restore the written text
                  </Button>
                )}
              </div>
              <p className="text-muted-foreground text-xs">
                To change a fact, edit it in the Knowledge Curator and
                synthesize again. Text edits here only need{" "}
                <strong>Rebuild report</strong> to reach the .docx; no model is
                called.
              </p>
            </>
          ) : (
            <div className="space-y-2">
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="min-h-[240px] font-mono text-xs"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    onSaveText(section.id, draft);
                    setDraft(null);
                  }}
                >
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDraft(null)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="source" className="space-y-2 pt-2">
          {derived ? (
            <div className="space-y-2 text-xs">
              <p>
                This section is <strong>derived</strong>. It was written only
                from the finished text of{" "}
                {prerequisites.length
                  ? prerequisites.map((p) => p.title).join(", ")
                  : "its prerequisite sections"}
                . It did <strong>not</strong> see the sources or their facts, so
                it can only repeat or reorganize what those sections say. A fact
                that none of them mentions cannot appear here.
              </p>
            </div>
          ) : knowledge ? (
            <div className="space-y-2">
              <p className="text-muted-foreground text-xs">
                The writer saw only these curated facts and nothing else from
                the sources.{" "}
                {citations
                  ? "With citations on, each fact is cited by its file and location."
                  : "With citations off, the facts are written as plain statements."}{" "}
                An item listed as missing became a (missing: …) marker in the
                text.
              </p>
              <div className="max-h-[360px] overflow-y-auto">
                <SectionView knowledge={knowledge} failures={[]} />
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground text-xs">
              No knowledge is loaded for this section.
            </p>
          )}
        </TabsContent>

        <TabsContent value="review" className="space-y-3 pt-2">
          <p className="text-muted-foreground text-xs">
            A second model checks each draft against its material and proposes
            small search-and-replace corrections. The text above is the reviewed
            text.
          </p>
          <div className="space-y-1">
            <p className="text-xs font-medium">
              Applied ({review?.applied.length ?? 0})
            </p>
            <EditList
              edits={review?.applied ?? []}
              empty="The reviewer made no changes."
            />
          </div>
          {(review?.unresolved.length ?? 0) > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-amber-600">
                Not applied ({review!.unresolved.length})
              </p>
              <p className="text-muted-foreground text-xs">
                The reviewer proposed these, but their search text was not found
                exactly once in the draft, so they were left out. Check the text
                by hand.
              </p>
              <EditList edits={review!.unresolved} empty="" />
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
