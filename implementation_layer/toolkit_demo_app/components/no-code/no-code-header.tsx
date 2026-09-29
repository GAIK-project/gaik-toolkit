import { prompts, skills } from "@/lib/no-code/catalog";
import { cn } from "@/lib/utils";
import Link from "next/link";

const tabs = [
  { href: "/skills", label: "Agent skills", count: skills.length },
  { href: "/prompts", label: "Prompts", count: prompts.length },
] as const;

/** Shared top of /skills and /prompts: title and a two-way switch. */
export function NoCodeHeader({ active }: { active: "/skills" | "/prompts" }) {
  return (
    <header className="space-y-5">
      <div className="space-y-2">
        <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
          No-code assets
        </h1>
        <p className="text-muted-foreground max-w-xl">
          Ready-made skills and prompts. Download, copy or open them in the
          assistant you already use.
        </p>
      </div>
      <nav aria-label="No-code assets" className="bg-muted inline-flex rounded-lg p-1">
        {tabs.map(({ href, label, count }) => (
          <Link
            key={href}
            href={href}
            aria-current={href === active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition",
              href === active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
            <span className="text-muted-foreground text-xs">{count}</span>
          </Link>
        ))}
      </nav>
    </header>
  );
}
