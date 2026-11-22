import { PROCESSES, processAnchor } from "@/lib/knowledge-processes";
import { cn } from "@/lib/utils";
import { ArrowDown } from "lucide-react";
import { components, inProcess } from "./demo-data";

/** "A and B", or the first two and how many more there are: one line per row. */
function nameLine(titles: string[]): string {
  if (titles.length <= 2) return titles.join(" and ");
  return `${titles[0]}, ${titles[1]} and ${titles.length - 2} more`;
}

/**
 * The three knowledge processes as one quiet list: each row names a few of the
 * process's components and jumps to its group in the Software Components
 * section. Beside the title from lg up, under the button below that; a phone
 * gets the names of the processes alone.
 */
export function ProcessOverview({ className }: { className?: string }) {
  return (
    <nav
      aria-label="Knowledge processes"
      className={cn(
        "flex items-center border-t pt-2 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-10",
        className,
      )}
    >
      <ul className="w-full divide-y">
        {PROCESSES.map((process) => (
          <li key={process.name}>
            <a
              href={`#${processAnchor(process.name)}`}
              className="group focus-visible:ring-ring/50 flex items-center gap-3 rounded-md py-3 outline-none focus-visible:ring-[3px] sm:py-3.5"
            >
              <span
                className={cn(
                  "flex size-9 shrink-0 items-center justify-center rounded-lg",
                  process.tile,
                )}
              >
                <process.icon className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn("block font-semibold", process.accent)}>
                  {process.name}
                </span>
                <span className="text-muted-foreground hidden text-sm sm:block">
                  {nameLine(
                    inProcess(components, process.name).map(
                      (demo) => demo.title,
                    ),
                  )}
                </span>
              </span>
              <ArrowDown
                className="text-muted-foreground/60 group-hover:text-foreground size-4 shrink-0 transition group-hover:translate-y-0.5 motion-reduce:transform-none"
                aria-hidden="true"
              />
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
