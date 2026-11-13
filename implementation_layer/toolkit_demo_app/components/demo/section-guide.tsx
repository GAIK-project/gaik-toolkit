import { cn } from "@/lib/utils";
import { ChevronDown, CircleHelp, type LucideIcon } from "lucide-react";

export interface GuideStep {
  /** Kept for the callers; the step number marks the step, so the icon is not drawn. */
  icon?: LucideIcon;
  title: string;
  text: string;
}

/**
 * The guide of a section, closed at first so the demo itself leads: one line that
 * opens to numbered steps and a few things worth knowing before starting.
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
    <details className={cn("group/guide bg-card rounded-xl border", className)}>
      <summary className="hover:text-foreground text-muted-foreground focus-visible:ring-ring/50 flex cursor-pointer list-none items-center gap-2 rounded-xl px-5 py-3 text-sm font-medium outline-none focus-visible:ring-[3px] [&::-webkit-details-marker]:hidden">
        <CircleHelp className="size-4 shrink-0" aria-hidden />
        <span className="flex-1">{heading}</span>
        <ChevronDown
          className="size-4 shrink-0 transition-transform group-open/guide:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="px-5 pb-4">
        <ol
          className={cn(
            "grid gap-x-6 gap-y-3 sm:grid-cols-2",
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
      </div>
    </details>
  );
}
