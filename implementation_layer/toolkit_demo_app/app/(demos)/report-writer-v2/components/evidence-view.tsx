"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  FileAudio,
  FileText,
  Pencil,
  Quote,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import {
  type SectionRow,
  effectiveId,
} from "../../report-writer/components/section-editor";

interface Unit {
  id: string;
  topic: string;
  summary: string;
  quote: string;
  source: { file: string; locator: string | null };
  source_class: string | null;
  confidence: string;
}

interface Conflict {
  topic: string;
  description: string;
  status: string;
  unit_ids?: string[];
}

interface Knowledge {
  units: Unit[];
  missing: string[];
  conflicts: Conflict[];
}

type KnowledgeData = Record<string, unknown> & Knowledge;

/** The list shows about this many facts at a time; the rest are a scroll away. */
const FACTS_IN_VIEW = 5;

/** The curated knowledge of one section, or null when the file is missing or not valid. */
export function parseKnowledge(text: string | undefined): Knowledge | null {
  if (!text) return null;
  try {
    const data = JSON.parse(text) as Partial<Knowledge>;
    if (!Array.isArray(data.units)) return null;
    return {
      units: data.units as Unit[],
      missing: Array.isArray(data.missing) ? data.missing : [],
      conflicts: Array.isArray(data.conflicts) ? data.conflicts : [],
    };
  } catch {
    return null;
  }
}

/**
 * The knowledge file with one change applied, as text to save. Everything else in the file
 * stays as it is.
 */
export function changeKnowledge(
  text: string,
  change: (data: KnowledgeData) => void,
): string {
  const data = JSON.parse(text) as KnowledgeData;
  change(data);
  return JSON.stringify(data, null, 2);
}

const isRecording = (file: string) =>
  /\.(mp3|m4a|wav|ogg|flac|mp4|webm)$/i.test(file);

function UnitCard({
  unit,
  disabled,
  onChangeSummary,
  onRemove,
}: {
  unit: Unit;
  disabled: boolean;
  onChangeSummary: (summary: string) => void;
  onRemove: () => void;
}) {
  const Icon = isRecording(unit.source.file) ? FileAudio : FileText;
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <li className="space-y-1.5 rounded-lg border p-3">
      {draft === null ? (
        <div className="flex items-start gap-2">
          <p className="flex-1 text-sm font-medium">{unit.summary}</p>
          <Button
            size="icon-xs"
            variant="ghost"
            title="Edit the summary"
            aria-label="Edit the summary"
            disabled={disabled}
            onClick={() => setDraft(unit.summary)}
          >
            <Pencil />
          </Button>
          <Button
            size="icon-xs"
            variant="ghost"
            title="Remove this fact"
            aria-label="Remove this fact"
            disabled={disabled}
            onClick={onRemove}
          >
            <Trash2 />
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="min-h-[64px] text-sm"
            aria-label="Summary of the fact"
          />
          <div className="flex gap-2">
            <Button
              size="xs"
              disabled={!draft.trim()}
              onClick={() => {
                onChangeSummary(draft.trim());
                setDraft(null);
              }}
            >
              <Check />
              Save
            </Button>
            <Button size="xs" variant="outline" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      <p className="text-muted-foreground flex gap-2 border-l-2 pl-3 text-sm italic">
        <Quote className="mt-0.5 size-3.5 shrink-0" />
        <span>{unit.quote}</span>
      </p>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="bg-muted inline-flex items-center gap-1.5 rounded-md px-2 py-0.5">
          <Icon className="size-3.5" />
          {unit.source.file}
          {unit.source.locator ? ` · ${unit.source.locator}` : ""}
        </span>
        {unit.source_class && (
          <Badge variant="outline" className="text-xs font-normal">
            {unit.source_class === "primary"
              ? "primary source"
              : "secondary source"}
          </Badge>
        )}
        <span className="text-muted-foreground">
          {unit.confidence} confidence
        </span>
      </div>
    </li>
  );
}

/**
 * A disagreement between sources. A resolved one is settled by the report instructions.
 * An unresolved one is shown with both sides in the report; you can settle it here by
 * saying which side to follow, and the next Stage 3 run writes it that way.
 */
function ConflictCard({
  conflict,
  units,
  disabled,
  onResolve,
}: {
  conflict: Conflict;
  units: Unit[];
  disabled: boolean;
  onResolve: (decision: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const unresolved = conflict.status === "unresolved";
  const facts = units.filter((unit) => conflict.unit_ids?.includes(unit.id));
  return (
    <li
      className={cn(
        "space-y-2 rounded-md border p-3 text-sm",
        unresolved && "border-amber-500/60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{conflict.topic}</span>
        <Badge
          variant="outline"
          className={cn(
            "font-normal",
            unresolved && "border-amber-500 text-amber-700",
          )}
        >
          {conflict.status}
        </Badge>
      </div>
      <p className="text-muted-foreground">{conflict.description}</p>
      {facts.length > 0 && (
        <ul className="space-y-1.5">
          {facts.map((fact) => (
            <li key={fact.id} className="bg-muted/40 rounded-md p-2 text-xs">
              <span className="font-medium">
                {fact.source.file}
                {fact.source.locator ? ` · ${fact.source.locator}` : ""}:
              </span>{" "}
              <span className="italic">{fact.quote}</span>
            </li>
          ))}
        </ul>
      )}
      {unresolved && draft === null && (
        <div className="space-y-1.5">
          <p className="text-muted-foreground text-xs">
            The report shows both sides and marks them <em>Unresolved:</em>.
            Decide which side is right, or leave it open for the reader.
          </p>
          <Button
            size="xs"
            variant="outline"
            disabled={disabled}
            onClick={() => setDraft(conflict.description)}
          >
            <Check />
            Settle it
          </Button>
        </div>
      )}
      {draft !== null && (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="min-h-[72px] text-sm"
            aria-label="Which side to follow"
          />
          <p className="text-muted-foreground text-xs">
            Say which side the report should follow and why. It is saved as
            resolved, and the next Stage 3 run is told to follow it. The report
            instructions still apply, so they can override it (for example a
            rule that an uncertain observation stays <em>Unresolved:</em>). To
            be sure of the wording, edit the section text yourself.
          </p>
          <div className="flex gap-2">
            <Button
              size="xs"
              disabled={!draft.trim()}
              onClick={() => {
                onResolve(draft.trim());
                setDraft(null);
              }}
            >
              Save as resolved
            </Button>
            <Button size="xs" variant="outline" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

/** The facts of a section in a scrollable list of fixed height, with a filter by source. */
function FactList({
  knowledge,
  disabled,
  onSave,
}: {
  knowledge: Knowledge;
  disabled: boolean;
  /** Receives the change to make to the knowledge file. */
  onSave: (change: (data: KnowledgeData) => void) => void;
}) {
  const [source, setSource] = useState<string | null>(null);

  const counts = new Map<string, number>();
  for (const unit of knowledge.units)
    counts.set(unit.source.file, (counts.get(unit.source.file) ?? 0) + 1);
  const filtered = source
    ? knowledge.units.filter((unit) => unit.source.file === source)
    : knowledge.units;
  const filters: [string | null, number][] = [
    [null, knowledge.units.length],
    ...Array.from(counts.entries()),
  ];

  return (
    <div className="space-y-2">
      <h5 className="text-sm font-semibold">
        Evidence{" "}
        <span className="text-muted-foreground font-normal">
          ({knowledge.units.length} facts)
        </span>
      </h5>

      {counts.size > 1 && (
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-label="Filter by source"
        >
          {filters.map(([file, count]) => (
            <button
              key={file ?? "all"}
              type="button"
              onClick={() => setSource(file)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                source === file
                  ? "border-primary bg-primary/10 text-primary"
                  : "hover:border-primary/40",
              )}
            >
              {file ?? "All sources"} ({count})
            </button>
          ))}
        </div>
      )}

      {/* About five facts tall; a longer list scrolls inside its own box. */}
      <ul
        className={cn(
          "space-y-2",
          filtered.length > FACTS_IN_VIEW &&
            "max-h-[34rem] overflow-y-auto overscroll-contain pr-2",
        )}
        tabIndex={filtered.length > FACTS_IN_VIEW ? 0 : undefined}
        aria-label="Facts of this section"
      >
        {filtered.map((unit) => (
          <UnitCard
            key={unit.id}
            unit={unit}
            disabled={disabled}
            onChangeSummary={(summary) =>
              onSave((data) => {
                const target = data.units.find((u) => u.id === unit.id);
                if (target) target.summary = summary;
              })
            }
            onRemove={() =>
              onSave((data) => {
                data.units = data.units.filter((u) => u.id !== unit.id);
              })
            }
          />
        ))}
      </ul>
      {filtered.length > FACTS_IN_VIEW && (
        <p className="text-muted-foreground text-xs">
          Showing {filtered.length} facts. Scroll the list to see them all.
        </p>
      )}
    </div>
  );
}

/** The text of a section, which can be edited here. */
function SectionText({
  text,
  disabled,
  onSave,
}: {
  text: string;
  disabled: boolean;
  onSave: (text: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <h5 className="text-sm font-semibold">Section text</h5>
        {draft === null && (
          <Button
            size="xs"
            variant="outline"
            disabled={disabled}
            onClick={() => setDraft(text)}
          >
            <Pencil />
            Edit
          </Button>
        )}
      </div>
      {draft === null ? (
        <div className="rounded-md border p-3">
          <MessageResponse className="text-sm">{text}</MessageResponse>
        </div>
      ) : (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="min-h-[240px] font-mono text-xs"
            aria-label="Section text"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={disabled}
              onClick={() => {
                onSave(draft);
                setDraft(null);
              }}
            >
              Save
            </Button>
            <Button size="sm" variant="outline" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * The report section by section, with the evidence it was written from: the facts, their
 * exact quotes and where each came from, plus the conflicts and the items no source covers.
 * Facts and section texts can be corrected here.
 */
export function EvidenceView({
  sections,
  artifacts,
  disabled,
  onSave,
  outOfDate,
  onDropRequirement,
}: {
  sections: SectionRow[];
  artifacts: Record<string, string>;
  disabled: boolean;
  onSave: (path: string, text: string) => void;
  /** The facts were changed after the report was written. */
  outOfDate: boolean;
  /** Stops the template from asking for an item that no source covers. */
  onDropRequirement: (sectionId: string, item: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const titles = Object.fromEntries(
    sections.map((s) => [effectiveId(s), s.title]),
  );

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">
        Every statement in the report comes from a quoted fact. Open a section
        to see its text and the evidence behind it. You can correct or remove a
        fact, or edit the text.
      </p>
      {outOfDate && (
        <p className="text-sm text-amber-700">
          The facts changed after the report was written. Run Stage 3 again to
          update the report.
        </p>
      )}
      {sections.map((section) => {
        const id = effectiveId(section);
        // The section files are numbered in report order: 04_wet_rooms.md.
        const textPath = Object.keys(artifacts).find(
          (path) =>
            path.startsWith("report/sections/") && path.endsWith(`_${id}.md`),
        );
        const text = textPath ? artifacts[textPath] : undefined;
        const knowledgePath = `knowledge/${id}.json`;
        const knowledgeText = artifacts[knowledgePath];
        const knowledge = parseKnowledge(knowledgeText);
        const derived = section.depends_on.length > 0;
        const isOpen = open === id;

        const saveKnowledge = (change: (data: KnowledgeData) => void) =>
          onSave(knowledgePath, changeKnowledge(knowledgeText, change));

        return (
          <div key={id} className="rounded-xl border">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : id)}
              aria-expanded={isOpen}
              className="hover:bg-muted/40 flex w-full flex-wrap items-center gap-2 rounded-xl px-4 py-3 text-left"
            >
              <span className="font-semibold">{section.title}</span>
              {derived ? (
                <Badge variant="outline" className="font-normal">
                  summary of other sections
                </Badge>
              ) : knowledge ? (
                <Badge variant="outline" className="font-normal">
                  {knowledge.units.length} facts
                </Badge>
              ) : null}
              {knowledge && knowledge.conflicts.length > 0 && (
                <Badge
                  variant="outline"
                  className="border-amber-500 font-normal text-amber-700"
                >
                  {knowledge.conflicts.length} conflict
                  {knowledge.conflicts.length === 1 ? "" : "s"}
                </Badge>
              )}
              {knowledge && knowledge.missing.length > 0 && (
                <Badge
                  variant="outline"
                  className="border-amber-500 font-normal text-amber-700"
                  title="Items this section must cover that no source mentions"
                >
                  {knowledge.missing.length} missing item
                  {knowledge.missing.length === 1 ? "" : "s"}
                </Badge>
              )}
              <span className="text-muted-foreground ml-auto text-xs">
                {isOpen ? "Hide" : "Show"}
              </span>
            </button>
            {isOpen && (
              <div className="space-y-5 border-t px-4 py-4">
                {knowledge && knowledge.missing.length > 0 && (
                  <div className="space-y-2 rounded-lg border border-amber-500/60 bg-amber-50/50 p-3">
                    <h5 className="flex items-center gap-2 text-sm font-semibold">
                      <AlertTriangle className="size-4 text-amber-600" />
                      Missing: required items that no source covers
                    </h5>
                    <p className="text-muted-foreground text-sm">
                      The template says this section must cover these items, but
                      none of the sources mentions them. The rest of the section
                      is still written, and the report marks each of these as{" "}
                      <em>(missing: …)</em> instead of guessing. You can add a
                      source that covers the item and run the stages again. Or,
                      if the report does not need it, choose{" "}
                      <strong>Don&apos;t require this</strong>: the item is
                      taken out of the template, and its marker goes when Stage
                      3 runs again.
                    </p>
                    <ul className="space-y-1">
                      {knowledge.missing.map((item) => (
                        <li
                          key={item}
                          className="flex items-center gap-2 text-sm"
                        >
                          <span className="flex-1">{item}</span>
                          <Button
                            size="xs"
                            variant="outline"
                            disabled={disabled}
                            onClick={() => {
                              onDropRequirement(id, item);
                              saveKnowledge((data) => {
                                data.missing = data.missing.filter(
                                  (m) => m !== item,
                                );
                              });
                            }}
                          >
                            <X />
                            Don&apos;t require this
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {text ? (
                  <SectionText
                    text={text}
                    disabled={disabled}
                    onSave={(next) => onSave(textPath!, next)}
                  />
                ) : (
                  <p className="text-muted-foreground text-sm">
                    This section has not been written yet.
                  </p>
                )}

                {derived && (
                  <p className="text-muted-foreground text-sm">
                    Written only from the finished text of{" "}
                    {section.depends_on
                      .map((dep) => titles[dep] ?? dep)
                      .join(", ")}
                    , not from the sources.
                  </p>
                )}

                {knowledge && knowledge.conflicts.length > 0 && (
                  <div className="space-y-2">
                    <h5 className="flex items-center gap-2 text-sm font-semibold">
                      <AlertTriangle className="size-4 text-amber-600" />
                      Conflicts between sources
                    </h5>
                    <ul className="space-y-2">
                      {knowledge.conflicts.map((conflict, index) => (
                        <ConflictCard
                          key={index}
                          conflict={conflict}
                          units={knowledge.units}
                          disabled={disabled}
                          onResolve={(decision) =>
                            saveKnowledge((data) => {
                              const target = data.conflicts[index];
                              if (target) {
                                target.status = "resolved";
                                target.description = decision;
                              }
                            })
                          }
                        />
                      ))}
                    </ul>
                  </div>
                )}

                {knowledge && knowledge.units.length > 0 && (
                  <FactList
                    knowledge={knowledge}
                    disabled={disabled}
                    onSave={saveKnowledge}
                  />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
