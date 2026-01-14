"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowUpRight,
  FileSearch,
  FileText,
  Home,
  Mic,
  ShieldAlert,
  Tags,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Home", href: "/", icon: Home },
  { label: "Incident Report", href: "/incident-report", icon: ShieldAlert },
  { label: "Extractor", href: "/extractor", icon: FileSearch },
  { label: "Parser", href: "/parser", icon: FileText },
  { label: "Classifier", href: "/classifier", icon: Tags },
  { label: "Transcriber", href: "/transcriber", icon: Mic },
];

export function SiteNav() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="border-border/60 bg-background/80 sticky top-0 z-50 border-b backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-center gap-6 px-6 py-4">
        <Link href="/" className="shrink-0">
          <Image
            src="/logos/gaik-logo-letter-only.png"
            alt="GAIK"
            width={40}
            height={40}
            className="h-10 w-10"
            priority
          />
        </Link>

        <nav aria-label="Primary">
          <div className="border-border/70 bg-card/70 flex items-center gap-1 overflow-x-auto rounded-full border p-1.5 shadow-sm">
            {navItems.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium whitespace-nowrap transition",
                    active
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        <Button variant="outline" size="sm" asChild className="shrink-0">
          <a
            href="https://github.com/GAIK-project/gaik-toolkit"
            target="_blank"
            rel="noopener noreferrer"
          >
            <ArrowUpRight className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">GitHub</span>
          </a>
        </Button>
      </div>
    </header>
  );
}
