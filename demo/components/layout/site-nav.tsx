"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  FileSearch,
  FileText,
  Home,
  LucideIcon,
  Menu,
  Mic,
  ShieldAlert,
  Tags,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Home", href: "/", icon: Home },
  { label: "Incident Report", href: "/incident-report", icon: ShieldAlert },
  { label: "Extractor", href: "/extractor", icon: FileSearch },
  { label: "Parser", href: "/parser", icon: FileText },
  { label: "Classifier", href: "/classifier", icon: Tags },
  { label: "Transcriber", href: "/transcriber", icon: Mic },
] as const;

interface NavLinkProps {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  variant: "desktop" | "mobile";
}

function NavLink({ href, label, icon: Icon, active, variant }: NavLinkProps) {
  const isDesktop = variant === "desktop";
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center text-sm font-medium transition",
        isDesktop
          ? "gap-2 rounded-full px-4 py-2 whitespace-nowrap"
          : "gap-3 rounded-lg px-3 py-2.5",
        active
          ? cn("bg-primary text-primary-foreground", isDesktop && "shadow-sm")
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className={isDesktop ? "h-4 w-4" : "h-5 w-5"} />
      {isDesktop ? <span>{label}</span> : label}
    </Link>
  );
}

function MobileMenuButton() {
  return (
    <Button variant="outline" size="icon" className="md:hidden">
      <Menu className="h-5 w-5" />
      <span className="sr-only">Open menu</span>
    </Button>
  );
}

interface MobileNavProps {
  isActive: (href: string) => boolean;
}

function MobileNav({ isActive }: MobileNavProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Render placeholder button during SSR to avoid hydration mismatch
  // Sheet uses Radix Portal which renders differently on server vs client
  if (!mounted) {
    return <MobileMenuButton />;
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <MobileMenuButton />
      </SheetTrigger>
      <SheetContent side="right" className="w-72">
        <SheetHeader>
          <SheetTitle>Navigation</SheetTitle>
        </SheetHeader>
        <nav className="mt-6 flex flex-col gap-2">
          {navItems.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={isActive(item.href)}
              variant="mobile"
            />
          ))}
          <hr className="my-2" />
          <a
            href="https://github.com/GAIK-project/gaik-toolkit"
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
          >
            <ArrowUpRight className="h-5 w-5" />
            GitHub
          </a>
        </nav>
      </SheetContent>
    </Sheet>
  );
}

export function SiteNav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  }

  return (
    <header className="border-border/60 bg-background/80 sticky top-0 z-50 border-b backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 md:justify-center md:gap-6 md:px-6 md:py-4">
        <Link href="/" className="shrink-0">
          <Image
            src="/logos/gaik-logo-letter-only.png"
            alt="GAIK"
            width={40}
            height={40}
            className="h-9 w-9 md:h-10 md:w-10"
            priority
          />
        </Link>

        {/* Desktop Navigation */}
        <nav aria-label="Primary" className="hidden md:block">
          <div className="border-border/70 bg-card/70 flex items-center gap-1 rounded-full border p-1.5 shadow-sm">
            {navItems.map((item) => (
              <NavLink
                key={item.href}
                {...item}
                active={isActive(item.href)}
                variant="desktop"
              />
            ))}
          </div>
        </nav>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            asChild
            className="hidden shrink-0 sm:inline-flex"
          >
            <a
              href="https://github.com/GAIK-project/gaik-toolkit"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ArrowUpRight className="mr-1 h-4 w-4" />
              GitHub
            </a>
          </Button>

          <MobileNav isActive={isActive} />
        </div>
      </div>
    </header>
  );
}
