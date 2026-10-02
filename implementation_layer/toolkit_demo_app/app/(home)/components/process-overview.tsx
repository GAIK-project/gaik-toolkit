import { PROCESSES, processAnchor } from "@/lib/knowledge-processes";
import { cn } from "@/lib/utils";

/** The three knowledge processes as a pipeline, each linking to its components. */
export function ProcessOverview({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col items-stretch gap-3", className)}>
      {PROCESSES.map((process) => {
        return (
          <div key={process.name} className="flex flex-col items-stretch">
            <a
              href={`#${processAnchor(process.name)}`}
              className={cn(
                "bg-background/70 group rounded-xl border p-3.5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:hover:translate-y-0",
                process.hoverBorder,
              )}
            >
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "flex size-9 shrink-0 items-center justify-center rounded-lg",
                    process.tile,
                  )}
                >
                  <process.icon className="size-4" />
                </span>
                <div className="min-w-0">
                  <p className={cn("font-semibold", process.accent)}>
                    {process.name}
                  </p>
                </div>
              </div>
            </a>
          </div>
        );
      })}
    </div>
  );
}
