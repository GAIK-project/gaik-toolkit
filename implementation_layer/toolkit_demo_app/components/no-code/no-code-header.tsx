import { prompts, skills } from "@/lib/no-code/catalog";
import { cn } from "@/lib/utils";
import { MessageSquare, Wand2 } from "lucide-react";
import Link from "next/link";
import { ViewTransition } from "react";

const tabs = [
  { href: "/skills", label: "Agent skills", count: skills.length, icon: Wand2 },
  {
    href: "/prompts",
    label: "Prompts",
    count: prompts.length,
    icon: MessageSquare,
  },
] as const;

/**
 * Shared top of /skills and /prompts: title and a two-way switch. `lede`
 * replaces the shared sentence with one about the page itself.
 *
 * Each page renders its own copy, so the active tab's background carries a
 * shared view-transition name and glides to the other tab on navigation
 * (`.tab-glide` in globals.css). The labels are named too: a named group is
 * drawn above the page snapshot, and their z-index keeps them above the
 * background while it moves.
 */
export function NoCodeHeader({
  active,
  lede,
}: {
  active: "/skills" | "/prompts";
  lede?: string;
}) {
  return (
    <header className="space-y-5">
      <div className="space-y-2">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          No-code assets
        </h1>
        <p className="text-muted-foreground max-w-xl">
          {lede ??
            "Ready-made skills and prompts. Download, copy or open them in the assistant you already use."}
        </p>
      </div>
      <nav
        aria-label="No-code assets"
        className="bg-muted isolate inline-flex rounded-lg p-1"
      >
        {tabs.map(({ href, label, count, icon: Icon }) => {
          const current = href === active;
          return (
            <Link
              key={href}
              href={href}
              aria-current={current ? "page" : undefined}
              className={cn(
                "relative rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
                current
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {current && (
                <ViewTransition
                  name="no-code-tab"
                  share="tab-glide"
                  default="none"
                >
                  <span
                    aria-hidden="true"
                    className="bg-background absolute inset-0 rounded-md shadow-sm"
                  />
                </ViewTransition>
              )}
              <ViewTransition
                name={`no-code-tab-label-${href.slice(1)}`}
                share="tab-label"
                default="none"
              >
                <span className="relative z-10 flex items-center gap-2">
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                  <span className="text-muted-foreground text-xs">{count}</span>
                </span>
              </ViewTransition>
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
