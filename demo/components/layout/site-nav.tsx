"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot,
  Boxes,
  ChevronDown,
  FileSearch,
  FileText,
  Lightbulb,
  LogOut,
  LucideIcon,
  Menu,
  Mic,
  ShieldAlert,
  Tags,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  Glimpse,
  GlimpseTrigger,
  GlimpseContent,
  GlimpseTitle,
  GlimpseDescription,
  GlimpseImage,
} from "@/components/kibo-ui/glimpse";
import { GitHubIcon } from "@/components/github-icon";
import { GITHUB_REPO_URL, type LinkPreview } from "@/lib/link-previews";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

interface NavGroup {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    label: "Use Cases",
    icon: Lightbulb,
    items: [
      { label: "Incident Report", href: "/incident-report", icon: ShieldAlert },
      { label: "RAG Builder", href: "/rag", icon: Bot },
    ],
  },
  {
    label: "Building Blocks",
    icon: Boxes,
    items: [
      { label: "Extractor", href: "/extractor", icon: FileSearch },
      { label: "Parser", href: "/parser", icon: FileText },
      { label: "Classifier", href: "/classifier", icon: Tags },
      { label: "Transcriber", href: "/transcriber", icon: Mic },
    ],
  },
];

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

interface GitHubLinkProps {
  preview?: LinkPreview | null;
  variant: "desktop" | "mobile";
}

function GitHubLink({ preview, variant }: GitHubLinkProps) {
  const isDesktop = variant === "desktop";

  const linkContent = (
    <a
      href={GITHUB_REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "flex items-center font-medium transition",
        isDesktop
          ? "gap-2 text-sm"
          : "text-muted-foreground hover:bg-muted hover:text-foreground gap-3 rounded-lg px-3 py-2.5 text-sm",
      )}
    >
      <GitHubIcon className={isDesktop ? "h-4 w-4" : "h-5 w-5"} />
      GitHub
    </a>
  );

  if (!preview) {
    return isDesktop ? (
      <a
        href={GITHUB_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 hidden h-8 shrink-0 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium shadow-xs transition-all sm:inline-flex"
      >
        <GitHubIcon className="h-4 w-4" />
        GitHub
      </a>
    ) : (
      linkContent
    );
  }

  return (
    <Glimpse>
      <GlimpseTrigger asChild>
        {isDesktop ? (
          <a
            href={GITHUB_REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 hidden h-8 shrink-0 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium shadow-xs transition-all sm:inline-flex"
          >
            <GitHubIcon className="h-4 w-4" />
            GitHub
          </a>
        ) : (
          linkContent
        )}
      </GlimpseTrigger>
      <GlimpseContent className="w-80">
        <a
          href={GITHUB_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-inherit no-underline"
        >
          {preview.image && (
            <GlimpseImage src={preview.image} alt={preview.title || "GitHub"} />
          )}
          <GlimpseTitle>{preview.title || "GAIK Toolkit"}</GlimpseTitle>
          <GlimpseDescription>
            {preview.description || "AI-powered document processing toolkit"}
          </GlimpseDescription>
        </a>
      </GlimpseContent>
    </Glimpse>
  );
}

interface NavDropdownProps {
  group: NavGroup;
  isActive: (href: string) => boolean;
}

function NavDropdown({ group, isActive }: NavDropdownProps) {
  const hasActiveItem = group.items.some((item) => isActive(item.href));
  const GroupIcon = group.icon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium whitespace-nowrap transition",
            hasActiveItem
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          <GroupIcon className="h-4 w-4" />
          <span>{group.label}</span>
          <ChevronDown className="h-3 w-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-48">
        {group.items.map((item) => {
          const ItemIcon = item.icon;
          const active = isActive(item.href);
          return (
            <DropdownMenuItem key={item.href} asChild>
              <Link
                href={item.href}
                className={cn(
                  "flex cursor-pointer items-center gap-2",
                  active && "bg-accent",
                )}
              >
                <ItemIcon className="h-4 w-4" />
                {item.label}
              </Link>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MobileMenuButton() {
  return (
    <Button variant="outline" size="icon" className="lg:hidden">
      <Menu className="h-5 w-5" />
      <span className="sr-only">Open menu</span>
    </Button>
  );
}

interface MobileNavProps {
  isActive: (href: string) => boolean;
  githubPreview?: LinkPreview | null;
  isLoggedIn?: boolean;
}

function MobileNav({ isActive, githubPreview, isLoggedIn }: MobileNavProps) {
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
        <nav className="mt-6 flex flex-col gap-4">
          {navGroups.map((group) => (
            <div key={group.label}>
              <div className="text-muted-foreground mb-2 flex items-center gap-2 px-3 text-xs font-semibold uppercase tracking-wider">
                <group.icon className="h-4 w-4" />
                {group.label}
              </div>
              <div className="flex flex-col gap-1">
                {group.items.map((item) => (
                  <NavLink
                    key={item.href}
                    {...item}
                    active={isActive(item.href)}
                    variant="mobile"
                  />
                ))}
              </div>
            </div>
          ))}
          <hr className="my-2" />
          <GitHubLink preview={githubPreview} variant="mobile" />
          {isLoggedIn && (
            <>
              <hr className="my-2" />
              <button
                type="button"
                className="text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
                onClick={async () => {
                  const res = await fetch("/api/auth/sign-out", {
                    method: "POST",
                  });
                  const data = await res.json();
                  if (data.redirectTo) {
                    window.location.href = data.redirectTo;
                  }
                }}
              >
                <LogOut className="h-5 w-5" />
                Sign out
              </button>
            </>
          )}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

export interface SiteNavProps {
  githubPreview?: LinkPreview | null;
  isLoggedIn?: boolean;
}

export function SiteNav({ githubPreview, isLoggedIn }: SiteNavProps) {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  }

  return (
    <header className="border-border/60 bg-background/80 sticky top-0 z-50 border-b backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 lg:justify-center lg:gap-6 lg:px-6 lg:py-4">
        <Link href="/" className="shrink-0">
          <Image
            src="/logos/gaik-logo-letter-only.png"
            alt="GAIK"
            width={40}
            height={40}
            className="h-9 w-9 lg:h-10 lg:w-10"
            priority
          />
        </Link>

        {/* Desktop Navigation */}
        <nav aria-label="Primary" className="hidden lg:block">
          <div className="border-border/70 bg-card/70 flex items-center gap-1 rounded-full border p-1.5 shadow-sm">
            {navGroups.map((group) => (
              <NavDropdown key={group.label} group={group} isActive={isActive} />
            ))}
          </div>
        </nav>

        <div className="flex items-center gap-2">
          <GitHubLink preview={githubPreview} variant="desktop" />
          {isLoggedIn && (
            <form action="/api/auth/sign-out" method="POST">
              <Button
                variant="ghost"
                size="sm"
                type="submit"
                className="text-muted-foreground hover:text-foreground hidden gap-1.5 sm:inline-flex"
                onClick={async (e) => {
                  e.preventDefault();
                  const res = await fetch("/api/auth/sign-out", {
                    method: "POST",
                  });
                  const data = await res.json();
                  if (data.redirectTo) {
                    window.location.href = data.redirectTo;
                  }
                }}
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </Button>
            </form>
          )}
          <MobileNav
            isActive={isActive}
            githubPreview={githubPreview}
            isLoggedIn={isLoggedIn}
          />
        </div>
      </div>
    </header>
  );
}
