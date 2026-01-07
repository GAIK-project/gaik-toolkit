"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Home", href: "/" },
  { label: "Pipeline", href: "/pipeline" },
  { label: "Extractor", href: "/extractor" },
  { label: "Parser", href: "/parser" },
  { label: "Classifier", href: "/classifier" },
  { label: "Transcriber", href: "/transcriber" },
];

export function SiteNav() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="border-border/60 bg-background/80 sticky top-0 z-50 border-b backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="bg-primary/10 text-primary flex h-9 w-9 items-center justify-center rounded-full">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="hidden flex-col leading-none sm:flex">
            <span className="text-sm tracking-tight">GAIK Toolkit</span>
            <span className="text-muted-foreground text-xs">Demos</span>
          </div>
        </Link>

        <nav className="flex-1" aria-label="Primary">
          <div className="border-border/70 bg-card/70 flex items-center gap-2 overflow-x-auto rounded-full border p-1 shadow-sm">
            {navItems.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap transition",
                    active
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <Button variant="outline" size="sm" asChild>
            <a
              href="https://github.com/GAIK-project/gaik-toolkit"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
              <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </Button>
        </div>
      </div>
    </header>
  );
}
