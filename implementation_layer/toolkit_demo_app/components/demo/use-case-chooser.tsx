"use client";

import { cn } from "@/lib/utils";
import { Check, ChevronDown, Play, Wand2 } from "lucide-react";
import { useRef, useState, type ComponentType } from "react";

export type Choice = "example" | "create";

function Points({ items }: { items: string[] }) {
  return (
    <span className="mt-3 block space-y-1.5">
      {items.map((item) => (
        <span key={item} className="flex items-start gap-2 text-sm">
          <Check className="text-primary mt-0.5 size-4 shrink-0" />
          <span>{item}</span>
        </span>
      ))}
    </span>
  );
}

export interface UseCaseChooserProps {
  /** Which section is open at first. Neither, by default. */
  initialChoice?: Choice | null;
  exampleTitle?: string;
  exampleDescription: string;
  examplePoints: string[];
  createTitle: string;
  createDescription: string;
  createPoints: string[];
  /** Shown when the example is open. `onCreate` switches to the other section. */
  ExampleSection: ComponentType<{ onCreate: () => void }>;
  CreateSection: ComponentType;
}

/**
 * The two ways into a demo, as two cards that are always visible. Choosing one opens
 * its section below; choosing it again closes it. Neither is open at first, so nobody
 * has to scroll past one section to find the other.
 */
export function UseCaseChooser({
  initialChoice = null,
  exampleTitle = "See it work on an example",
  exampleDescription,
  examplePoints,
  createTitle,
  createDescription,
  createPoints,
  ExampleSection,
  CreateSection,
}: UseCaseChooserProps) {
  const [open, setOpen] = useState<Choice | null>(initialChoice);
  const contentRef = useRef<HTMLDivElement>(null);

  const choose = (choice: Choice) => {
    const next = open === choice ? null : choice;
    setOpen(next);
    if (next) {
      requestAnimationFrame(() =>
        contentRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      );
    }
  };

  return (
    <div className="space-y-6">
      <div
        role="tablist"
        aria-label="What would you like to do?"
        className="grid items-stretch gap-4 lg:grid-cols-2"
      >
        <button
          type="button"
          role="tab"
          aria-selected={open === "example"}
          onClick={() => choose("example")}
          className={cn(
            "bg-card flex items-start gap-4 rounded-2xl border-2 p-6 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md motion-reduce:hover:translate-y-0",
            open === "example" ? "border-primary" : "border-border",
          )}
        >
          <span className="bg-primary/10 text-primary flex size-11 shrink-0 items-center justify-center rounded-xl">
            <Play className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-lg font-semibold">{exampleTitle}</span>
            <span className="text-muted-foreground block text-sm">
              {exampleDescription}
            </span>
            <Points items={examplePoints} />
          </span>
          <ChevronDown
            className={cn(
              "text-muted-foreground mt-1 size-5 shrink-0 transition-transform",
              open === "example" && "rotate-180",
            )}
          />
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={open === "create"}
          onClick={() => choose("create")}
          className={cn(
            "border-primary/50 from-primary/15 via-card to-card ring-primary/20 flex items-start gap-5 rounded-2xl border-2 bg-gradient-to-br p-8 text-left shadow-lg ring-4 transition-all hover:-translate-y-0.5 hover:shadow-xl motion-reduce:hover:translate-y-0",
            open === "create" && "border-primary",
          )}
        >
          <span className="bg-primary text-primary-foreground flex size-14 shrink-0 items-center justify-center rounded-xl shadow-sm">
            <Wand2 className="size-7" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-serif text-xl font-semibold md:text-2xl">
              {createTitle}
            </span>
            <span className="text-muted-foreground block text-sm">
              {createDescription}
            </span>
            <Points items={createPoints} />
          </span>
          <ChevronDown
            className={cn(
              "text-primary mt-2 size-6 shrink-0 transition-transform",
              open === "create" && "rotate-180",
            )}
          />
        </button>
      </div>

      <div ref={contentRef} className="scroll-mt-24">
        {open === "example" && (
          <ExampleSection onCreate={() => choose("create")} />
        )}
        {open === "create" && <CreateSection />}
      </div>
    </div>
  );
}
