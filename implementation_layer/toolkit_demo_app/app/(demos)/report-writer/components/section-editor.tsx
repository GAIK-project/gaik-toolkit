"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import { useId } from "react";

export interface SectionRow {
  key: string;
  id: string; // explicit id, or "" to auto-derive from title
  title: string;
  instructions: string;
  depends_on: string[];
}

/** Derive a stable section id from its title (mirrors pipeline._slug). */
export function slugifyTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40) || "section";
}

/** Return the effective id for a section (explicit or derived). */
export function effectiveId(row: SectionRow): string {
  return row.id || slugifyTitle(row.title);
}

interface SectionEditorProps {
  sections: SectionRow[];
  onChange: (sections: SectionRow[]) => void;
  disabled?: boolean;
}

export function SectionEditor({ sections, onChange, disabled }: SectionEditorProps) {
  const baseId = useId();

  function update(key: string, patch: Partial<SectionRow>) {
    onChange(sections.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  }

  function remove(key: string) {
    onChange(sections.filter((s) => s.key !== key));
  }

  function move(key: string, dir: -1 | 1) {
    const idx = sections.findIndex((s) => s.key === key);
    if (idx < 0) return;
    const next = [...sections];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    onChange(next);
  }

  function add() {
    onChange([
      ...sections,
      {
        key: `${Date.now()}-${Math.random()}`,
        id: "",
        title: "",
        instructions: "",
        depends_on: [],
      },
    ]);
  }

  const otherIds = (key: string) =>
    sections
      .filter((s) => s.key !== key && s.title)
      .map((s) => ({ id: effectiveId(s), title: s.title }));

  return (
    <div className="space-y-2">
      {sections.map((row, idx) => (
        <div
          key={row.key}
          className="rounded-lg border bg-card px-4 py-3 space-y-3"
        >
          {/* Row header */}
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="shrink-0 text-xs">
              {idx + 1}
            </Badge>
            <Input
              id={`${baseId}-title-${row.key}`}
              placeholder="Section title (e.g. Findings)"
              value={row.title}
              onChange={(e) => update(row.key, { title: e.target.value })}
              disabled={disabled}
              className="flex-1 h-8 text-sm"
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => move(row.key, -1)}
              disabled={disabled || idx === 0}
              title="Move up"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => move(row.key, 1)}
              disabled={disabled || idx === sections.length - 1}
              title="Move down"
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-destructive hover:text-destructive"
              onClick={() => remove(row.key)}
              disabled={disabled}
              title="Remove section"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>

          {/* Instructions */}
          <Textarea
            id={`${baseId}-instr-${row.key}`}
            placeholder="Instructions: what should this section contain?"
            value={row.instructions}
            onChange={(e) => update(row.key, { instructions: e.target.value })}
            disabled={disabled}
            className="text-sm min-h-[72px] resize-none"
          />

          {/* Advanced (id + depends_on) */}
          <Accordion type="single" collapsible>
            <AccordionItem value="adv" className="border-none">
              <AccordionTrigger className="py-0 text-xs text-muted-foreground hover:no-underline">
                Advanced (id · depends_on)
                {row.depends_on.length > 0 && (
                  <span className="ml-2 text-primary font-medium">
                    {row.depends_on.length} dep{row.depends_on.length > 1 ? "s" : ""}
                  </span>
                )}
              </AccordionTrigger>
              <AccordionContent className="pt-2 space-y-3">
                {/* Section id */}
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">
                    Section id
                    <span className="ml-1 font-normal opacity-60">
                      (auto: {slugifyTitle(row.title || "section")})
                    </span>
                  </Label>
                  <Input
                    placeholder={slugifyTitle(row.title || "section")}
                    value={row.id}
                    onChange={(e) => update(row.key, { id: e.target.value })}
                    disabled={disabled}
                    className="h-7 text-xs font-mono"
                  />
                </div>

                {/* Depends on — chip-based selection */}
                {otherIds(row.key).length > 0 && (
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">
                      Depends on
                      <span className="ml-1 font-normal opacity-60">
                        — click to toggle; selected sections are written first and
                        passed as context
                      </span>
                    </Label>
                    <div className="flex flex-wrap gap-1.5">
                      {otherIds(row.key).map((o) => {
                        const selected = row.depends_on.includes(o.id);
                        return (
                          <button
                            key={o.id}
                            type="button"
                            disabled={disabled}
                            onClick={() => {
                              const next = selected
                                ? row.depends_on.filter((x) => x !== o.id)
                                : [...row.depends_on, o.id];
                              update(row.key, { depends_on: next });
                            }}
                            className={cn(
                              "rounded-full border px-2.5 py-0.5 text-xs font-mono transition-colors",
                              selected
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-border bg-muted text-muted-foreground hover:border-primary/50 hover:text-foreground",
                              disabled && "pointer-events-none opacity-50",
                            )}
                            title={selected ? `Remove dependency on ${o.id}` : `Add dependency on ${o.id}`}
                          >
                            {o.id}
                          </button>
                        );
                      })}
                    </div>
                    {row.depends_on.length === 0 && (
                      <p className="text-xs text-muted-foreground opacity-60">
                        No dependencies — this section runs in parallel with others.
                      </p>
                    )}
                  </div>
                )}
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      ))}

      <Button
        variant="outline"
        size="sm"
        onClick={add}
        disabled={disabled}
        className="w-full"
      >
        <Plus className="mr-2 h-4 w-4" />
        Add Section
      </Button>
    </div>
  );
}
