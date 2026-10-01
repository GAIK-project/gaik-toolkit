import { cn } from "@/lib/utils";
import { Info, type LucideIcon } from "lucide-react";

export interface GuideStep {
  icon: LucideIcon;
  title: string;
  text: string;
}

/**
 * A short, always-visible guide at the top of a section: numbered steps for what to do,
 * and a few things worth knowing before starting.
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
      className={cn(
        "from-primary/5 to-card rounded-xl border bg-gradient-to-br p-5",
        className,
      )}
    >
      <h3 className="text-sm font-semibold tracking-wide uppercase">
        {heading}
      </h3>
      <ol
        className={cn(
          "mt-4 grid gap-3 sm:grid-cols-2",
          steps.length > 4 ? "lg:grid-cols-5" : "lg:grid-cols-4",
        )}
      >
        {steps.map((step, index) => (
          <li
            key={step.title}
            className="bg-card flex gap-3 rounded-lg border p-3 shadow-xs"
          >
            <span className="bg-primary text-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                <step.icon
                  className="text-primary size-4 shrink-0"
                  aria-hidden
                />
                {step.title}
              </span>
              <span className="text-muted-foreground mt-1 block text-sm leading-5">
                {step.text}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <ul className="text-muted-foreground mt-4 space-y-1.5 text-sm">
        {notes.map((note) => (
          <li key={note} className="flex items-start gap-2">
            <Info className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{note}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
