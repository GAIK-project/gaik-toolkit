import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export interface GuideStep {
  /** Kept for the callers; the step number marks the step, so the icon is not drawn. */
  icon?: LucideIcon;
  title: string;
  text: string;
}

/**
 * A short, always-visible guide at the top of a section: numbered steps for what to do,
 * and a few things worth knowing before starting. Kept quiet so the demo itself leads.
 */
export function SectionGuide({
  heading,
  steps,
  notes,
  className,
}: {
  heading: string;
  steps: GuideStep[];
  notes: string[];
  className?: string;
}) {
  return (
    <section
      aria-label={heading}
      className={cn("bg-card rounded-xl border px-5 py-4", className)}
    >
      <h2 className="text-sm font-semibold">{heading}</h2>
      <ol
        className={cn(
          "mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2",
          steps.length > 4 ? "lg:grid-cols-5" : "lg:grid-cols-4",
        )}
      >
        {steps.map((step, index) => (
          <li key={step.title} className="flex gap-2.5">
            <span className="border-primary/40 text-primary mt-px flex size-5 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tabular-nums">
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium">{step.title}</span>
              <span className="text-muted-foreground mt-0.5 block text-sm leading-5">
                {step.text}
              </span>
            </span>
          </li>
        ))}
      </ol>
      {notes.length > 0 && (
        <ul className="text-muted-foreground mt-4 space-y-1 border-t pt-3 text-sm">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
