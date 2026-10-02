"use client";

import { ModelSettingsButton } from "@/components/model-settings";
import { setModelSettings } from "@/lib/model-settings-store";

import { GitHubIcon } from "@/components/github-icon";
import {
  Glimpse,
  GlimpseContent,
  GlimpseDescription,
  GlimpseImage,
  GlimpseTitle,
  GlimpseTrigger,
} from "@/components/kibo-ui/glimpse";
import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { Button } from "@/components/ui/button";
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
} from "@/components/ui/navigation-menu";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { GITHUB_REPO_URL, type LinkPreview } from "@/lib/link-previews";
import {
  ACCESS,
  CAPTURE,
  type KnowledgeProcess,
  processStyle,
  SYNTHESIS,
} from "@/lib/knowledge-processes";
import { cn } from "@/lib/utils";
import {
  AudioWaveform,
  Bot,
  Boxes,
  Braces,
  ChevronDown,
  ChevronRight,
  Database,
  ExternalLink,
  FileBarChart,
  FileCode,
  FileOutput,
  FilePen,
  FileStack,
  LibraryBig,
  NotebookPen,
  FileSearch,
  FileText,
  GraduationCap,
  HardHat,
  Headset,
  House,
  Lightbulb,
  LogOut,
  LucideIcon,
  Menu,
  MessageSquare,
  Mic,
  Puzzle,
  Scale,
  ScanEye,
  ShieldAlert,
  Table2,
  Tags,
  Video,
  Volume2,
  Wand2,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useEffect, useState } from "react";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  comingSoon?: boolean;
  /** Built but gated behind beta access (e.g. the Solution Wizard `?key=`). */
  beta?: boolean;
  external?: boolean;
  /** Knowledge process this item belongs to; a heading shows where it changes. */
  section?: string;
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
      { label: "Construction Diary", href: "/diary", icon: HardHat },
      {
        label: "Video Transcription & Captioning",
        href: "/dental-transcription",
        icon: Mic,
      },
      {
        label: "Semantic Video Search",
        href: "/video-search",
        icon: Video,
      },
      {
        label: "Purchase Order Processing",
        href: "/luvata-order",
        icon: FileBarChart,
      },
      {
        label: "Construction Report Writing",
        href: "/report-writer-v2?example=house_condition_assessment",
        icon: House,
      },
      {
        label: "Solution Wizard",
        href: "/solution-wizard",
        icon: Wand2,
        beta: true,
      },
      {
        label: "Customer onboarding and sales assistant",
        href: "#",
        icon: Headset,
        comingSoon: true,
      },
      {
        label: "Sales Proposal Generation",
        href: "#",
        icon: FileBarChart,
        comingSoon: true,
      },
      {
        label: "Learning plans & recommendations",
        href: "#",
        icon: GraduationCap,
        comingSoon: true,
      },
    ],
  },
  {
    label: "Software Components",
    icon: Boxes,
    items: [
      {
        label: "Schema Generator",
        href: "/schema-generator",
        icon: Braces,
        section: CAPTURE,
      },
      {
        label: "Extractor",
        href: "/extractor",
        icon: FileSearch,
        section: CAPTURE,
      },
      {
        label: "Vision Extractor",
        href: "/vision-extractor",
        icon: ScanEye,
        section: CAPTURE,
      },
      { label: "Parser", href: "/parser", icon: FileText, section: CAPTURE },
      {
        label: "Classifier",
        href: "/classifier",
        icon: Tags,
        section: CAPTURE,
      },
      {
        label: "Transcriber",
        href: "/transcriber",
        icon: Mic,
        section: CAPTURE,
      },
      {
        label: "Source Normalizer",
        href: "/source-normalizer",
        icon: FileStack,
        section: CAPTURE,
      },
      {
        label: "Knowledge Curator",
        href: "/knowledge-curator",
        icon: LibraryBig,
        section: CAPTURE,
      },
      {
        label: "PostgreSQL Agent",
        href: "/postgres-agent",
        icon: Database,
        section: ACCESS,
      },
      {
        label: "Tabular Agent",
        href: "/tabular-agent",
        icon: Table2,
        section: ACCESS,
      },
      {
        label: "Text-to-Speech",
        href: "/text-to-speech",
        icon: Volume2,
        section: SYNTHESIS,
      },
      {
        label: "LLM Judge",
        href: "/llm-judge",
        icon: Scale,
        section: SYNTHESIS,
      },
      {
        label: "Knowledge Synthesizer",
        href: "/knowledge-synthesis",
        icon: NotebookPen,
        section: SYNTHESIS,
      },
    ],
  },
  {
    label: "Software Modules",
    icon: Puzzle,
    items: [
      {
        label: "Audio → Structured",
        href: "/audio-structured",
        icon: AudioWaveform,
        section: CAPTURE,
      },
      {
        label: "Document → Structured",
        href: "/document-structured",
        icon: FileOutput,
        section: CAPTURE,
      },
      { label: "RAG Builder", href: "/rag", icon: Bot, section: ACCESS },
      {
        label: "Report Writer",
        href: "/report-writer",
        icon: FileText,
        section: SYNTHESIS,
      },
      {
        label: "Report Writer v2",
        href: "/report-writer-v2",
        icon: FilePen,
        section: SYNTHESIS,
      },
    ],
  },
  {
    label: "No-code Assets",
    icon: FileCode,
    items: [
      {
        label: "Prompts",
        href: "/prompts",
        icon: MessageSquare,
      },
      {
        label: "Agent Skills",
        href: "/skills",
        icon: Wand2,
      },
    ],
  },
];

interface NavSection {
  name: string;
  items: NavItem[];
}

/** A menu group's items by knowledge process, in menu order. */
function groupBySection(items: NavItem[]): NavSection[] {
  const sections: NavSection[] = [];
  for (const item of items) {
    const name = item.section ?? "";
    const last = sections.at(-1);
    if (last && last.name === name) last.items.push(item);
    else sections.push({ name, items: [item] });
  }
  return sections;
}

/** Whether every item of the group belongs to a knowledge process. */
const isSectioned = (group: NavGroup): boolean =>
  group.items.length > 0 && group.items.every((item) => item.section);

interface ItemContext {
  isActive: (href: string) => boolean;
  hasWizardAccess?: boolean;
  openWizardAccess: () => void;
}

/** One entry of a desktop dropdown: a link, a beta tile, a coming-soon tile or an external link. */
function DesktopMenuItem({
  item,
  active,
  hasWizardAccess,
  openWizardAccess,
}: {
  item: NavItem;
  active: boolean;
  hasWizardAccess?: boolean;
  openWizardAccess: () => void;
}) {
  const ItemIcon = item.icon;

  // Beta items: built but gated behind beta access
  // (the Solution Wizard `?key=`). Clickable for
  // visitors who already hold the wizard_access cookie;
  // a locked "Beta" tile for everyone else.
  if (item.beta) {
    if (hasWizardAccess) {
      return (
        <li>
          <NavigationMenuLink asChild>
            <Link
              href={item.href}
              className={cn(
                "hover:bg-primary/5 hover:text-primary focus:bg-primary/5 focus:text-primary block h-full space-y-1 rounded-md p-3 leading-none no-underline transition-colors outline-none select-none",
                active && "bg-primary/10 text-primary",
              )}
            >
              <div className="flex items-center gap-2 text-sm leading-none font-medium">
                <ItemIcon className="h-4 w-4" />
                {item.label}
                <span className="bg-primary/10 text-primary ml-auto rounded px-1.5 py-0.5 text-[10px] font-normal">
                  Beta
                </span>
              </div>
              <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
                Configure a solution from a plain-language use case.
              </p>
            </Link>
          </NavigationMenuLink>
        </li>
      );
    }
    return (
      <li>
        <NavigationMenuLink asChild>
          <button
            type="button"
            onClick={openWizardAccess}
            className="hover:bg-primary/5 hover:text-primary focus:bg-primary/5 focus:text-primary block h-full w-full space-y-1 rounded-md p-3 text-left leading-none transition-colors outline-none select-none"
          >
            <span className="text-muted-foreground flex items-center gap-2 text-sm leading-none font-medium">
              <ItemIcon className="h-4 w-4" />
              {item.label}
              <span className="bg-primary/10 text-primary ml-auto rounded px-1.5 py-0.5 text-[10px] font-normal">
                Beta
              </span>
            </span>
            <span className="text-muted-foreground/70 line-clamp-2 block text-sm leading-snug">
              In beta — request access.
            </span>
          </button>
        </NavigationMenuLink>
      </li>
    );
  }

  // Coming Soon items
  if (item.comingSoon) {
    return (
      <li>
        <div className="block h-full cursor-not-allowed space-y-1 rounded-md p-3 leading-none opacity-50">
          <div className="text-muted-foreground flex items-center gap-2 text-sm leading-none font-medium">
            <ItemIcon className="h-4 w-4" />
            {item.label}
            <span className="bg-muted ml-auto rounded px-1.5 py-0.5 text-[10px] font-normal">
              Soon
            </span>
          </div>
          <p className="text-muted-foreground/70 line-clamp-2 text-sm leading-snug">
            Coming soon
          </p>
        </div>
      </li>
    );
  }

  // External links
  if (item.external) {
    return (
      <li>
        <NavigationMenuLink asChild>
          <a
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:bg-primary/5 hover:text-primary focus:bg-primary/5 focus:text-primary block h-full space-y-1 rounded-md p-3 leading-none no-underline transition-colors outline-none select-none"
          >
            <div className="flex items-center gap-2 text-sm leading-none font-medium">
              <ItemIcon className="h-4 w-4" />
              {item.label}
              <ExternalLink className="text-muted-foreground ml-auto h-3 w-3" />
            </div>
            <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
              View on GitHub
            </p>
          </a>
        </NavigationMenuLink>
      </li>
    );
  }

  return (
    <li>
      <NavigationMenuLink asChild>
        <Link
          href={item.href}
          className={cn(
            "hover:bg-primary/5 hover:text-primary focus:bg-primary/5 focus:text-primary block h-full space-y-1 rounded-md p-3 leading-none no-underline transition-colors outline-none select-none",
            active && "bg-primary/10 text-primary",
          )}
        >
          <div className="flex items-center gap-2 text-sm leading-none font-medium">
            <ItemIcon className="h-4 w-4" />
            {item.label}
          </div>
          <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
            Explore the {item.label} features.
          </p>
        </Link>
      </NavigationMenuLink>
    </li>
  );
}

/**
 * The dropdown of a group organised by knowledge process. Only the process names are shown
 * at first; choosing one (by hover, focus or click) lists its components, so the whole
 * catalogue is never on screen at once.
 */
/** Width of a sectioned dropdown at the current viewport, matching its responsive classes. */
function sectionedMenuWidth(viewport: number): number {
  if (viewport >= 1024) return 640;
  if (viewport >= 768) return 560;
  return 420;
}

function SectionedMenu({ group, ctx }: { group: NavGroup; ctx: ItemContext }) {
  const sections = groupBySection(group.items);
  const current = sections.find((section) =>
    section.items.some((item) => ctx.isActive(item.href)),
  );
  const [selected, setSelected] = useState((current ?? sections[0]).name);
  const shown =
    sections.find((section) => section.name === selected) ?? sections[0];

  return (
    <div className="grid w-[420px] md:w-[560px] md:grid-cols-[13rem_1fr] lg:w-[640px]">
      <ul
        aria-label={group.label}
        className="border-border/60 space-y-1 border-r p-3"
      >
        {sections.map((section) => {
          const isShown = section.name === shown.name;
          const style = processStyle(section.name as KnowledgeProcess);
          return (
            <li key={section.name}>
              <button
                type="button"
                aria-current={isShown}
                onMouseEnter={() => setSelected(section.name)}
                onFocus={() => setSelected(section.name)}
                onClick={() => setSelected(section.name)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm font-medium transition-colors outline-none",
                  isShown
                    ? cn("bg-muted", style.accent)
                    : "text-foreground hover:bg-muted focus:bg-muted",
                )}
              >
                <span
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-md",
                    style.tile,
                  )}
                >
                  <style.icon className="size-4" />
                </span>
                <span className="flex-1">{section.name}</span>
                <span className="text-muted-foreground text-xs font-normal">
                  {section.items.length}
                </span>
                <ChevronRight className="h-4 w-4 opacity-60" />
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="grid content-start gap-2 p-3 sm:grid-cols-2">
        {shown.items.map((item) => (
          <DesktopMenuItem
            key={item.label}
            item={item}
            active={ctx.isActive(item.href)}
            hasWizardAccess={ctx.hasWizardAccess}
            openWizardAccess={ctx.openWizardAccess}
          />
        ))}
      </ul>
    </div>
  );
}

/** One row of the mobile menu. */
function MobileMenuItem({ item, ctx }: { item: NavItem; ctx: ItemContext }) {
  const { hasWizardAccess, openWizardAccess, isActive } = ctx;
  // Beta items: clickable for beta-access holders, otherwise a
  // locked "Beta" row.
  if (item.beta) {
    if (hasWizardAccess) {
      return (
        <Link
          href={item.href}
          className="text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
        >
          <item.icon className="h-5 w-5" />
          {item.label}
          <span className="bg-primary/10 text-primary ml-auto rounded px-1.5 py-0.5 text-[10px]">
            Beta
          </span>
        </Link>
      );
    }
    return (
      <SheetClose asChild>
        <button
          type="button"
          onClick={openWizardAccess}
          className="text-muted-foreground hover:bg-muted hover:text-foreground flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition"
        >
          <item.icon className="h-5 w-5" />
          {item.label}
          <span className="bg-primary/10 text-primary ml-auto rounded px-1.5 py-0.5 text-[10px]">
            Beta
          </span>
        </button>
      </SheetClose>
    );
  }

  // Coming Soon items
  if (item.comingSoon) {
    return (
      <div className="text-muted-foreground/60 flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium">
        <item.icon className="h-5 w-5" />
        {item.label}
        <span className="bg-muted ml-auto rounded px-1.5 py-0.5 text-[10px]">
          Soon
        </span>
      </div>
    );
  }

  // External links
  if (item.external) {
    return (
      <a
        href={item.href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
      >
        <item.icon className="h-5 w-5" />
        {item.label}
        <ExternalLink className="text-muted-foreground/60 ml-auto h-4 w-4" />
      </a>
    );
  }

  return <NavLink {...item} active={isActive(item.href)} variant="mobile" />;
}

/** A group organised by knowledge process: one collapsible list per process, one open at a time. */
function MobileSectionedGroup({
  group,
  ctx,
}: {
  group: NavGroup;
  ctx: ItemContext;
}) {
  const sections = groupBySection(group.items);
  const current = sections.find((section) =>
    section.items.some((item) => ctx.isActive(item.href)),
  );
  const [open, setOpen] = useState<string | null>(current?.name ?? null);

  return (
    <div className="flex flex-col gap-0.5 pl-2">
      {sections.map((section) => {
        const expanded = open === section.name;
        return (
          <div key={section.name}>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : section.name)}
              className="text-muted-foreground hover:bg-muted hover:text-foreground flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition"
            >
              <span className="flex-1">{section.name}</span>
              <span className="text-xs font-normal">
                {section.items.length}
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform",
                  expanded && "rotate-180",
                )}
              />
            </button>
            {expanded && (
              <div className="flex flex-col gap-0.5 pl-3">
                {section.items.map((item) => (
                  <MobileMenuItem key={item.label} item={item} ctx={ctx} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface NavLinkProps {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  variant: "desktop" | "mobile";
}

function NavLink({ href, label, icon: Icon, active, variant }: NavLinkProps) {
  const isDesktop = variant === "desktop";

  // For desktop NavigationMenuLink, we'll handle outside this component if needed,
  // but for now we can just use Link directly in the menu content.
  // This component is mainly reused for mobile now or simple links.

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
        className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 hidden h-8 w-8 shrink-0 items-center justify-center rounded-md border shadow-xs transition-all xl:inline-flex"
        aria-label="GitHub"
      >
        <GitHubIcon className="h-4 w-4" />
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
            className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 hidden h-8 w-8 shrink-0 items-center justify-center rounded-md border shadow-xs transition-all xl:inline-flex"
            aria-label="GitHub"
          >
            <GitHubIcon className="h-4 w-4" />
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

/** Handles sign-out via API and redirects */
async function handleSignOut(): Promise<void> {
  setModelSettings(null);
  const res = await fetch("/api/auth/sign-out", { method: "POST" });
  const data = await res.json();
  if (data.redirectTo) {
    window.location.href = data.redirectTo;
  }
}

const MobileMenuButton = React.forwardRef<
  HTMLButtonElement,
  React.ComponentProps<typeof Button>
>(function MobileMenuButton(props, ref) {
  return (
    <Button
      ref={ref}
      variant="outline"
      size="icon"
      className="md:hidden"
      {...props}
    >
      <Menu className="h-5 w-5" />
      <span className="sr-only">Open menu</span>
    </Button>
  );
});

interface MobileNavProps {
  isActive: (href: string) => boolean;
  githubPreview?: LinkPreview | null;
  isLoggedIn?: boolean;
  hasWizardAccess?: boolean;
}

function MobileNav({
  isActive,
  githubPreview,
  isLoggedIn,
  hasWizardAccess,
}: MobileNavProps) {
  const { openWizardAccess } = useOnboarding();
  const [mounted, setMounted] = useState(false);
  const itemContext: ItemContext = {
    isActive,
    hasWizardAccess,
    openWizardAccess,
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time SSR mount flag, not a cascade
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
      <SheetContent
        side="right"
        className="flex w-[85vw] max-w-72 flex-col sm:w-72"
      >
        <SheetHeader className="shrink-0">
          <SheetTitle>Navigation</SheetTitle>
        </SheetHeader>
        <nav className="mt-4 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {navGroups.map((group, index) => (
            <div key={group.label} className={index > 0 ? "mt-2" : ""}>
              {index > 0 && <hr className="border-border/60 mb-3" />}
              <div className="text-primary/80 mb-2 flex items-center gap-2 px-3 py-1 text-xs font-semibold tracking-wider uppercase">
                <group.icon className="h-4 w-4" />
                {group.label}
              </div>
              {isSectioned(group) ? (
                <MobileSectionedGroup group={group} ctx={itemContext} />
              ) : (
                <div className="flex flex-col gap-0.5 pl-2">
                  {group.items.map((item) => (
                    <MobileMenuItem
                      key={item.label}
                      item={item}
                      ctx={itemContext}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
          <hr className="border-border/60 my-3" />
          <div className="px-2">
            <GitHubLink preview={githubPreview} variant="mobile" />
          </div>
          {isLoggedIn && (
            <div className="px-2">
              <button
                type="button"
                className="text-muted-foreground hover:bg-muted hover:text-foreground flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition"
                onClick={handleSignOut}
              >
                <LogOut className="h-5 w-5" />
                Sign out
              </button>
            </div>
          )}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

export interface SiteNavProps {
  pathname: string;
  githubPreview?: LinkPreview | null;
  isLoggedIn?: boolean;
  /** True when the visitor already holds wizard_access (beta) — server-read. */
  hasWizardAccess?: boolean;
}

export function SiteNav({
  pathname: initialPathname,
  githubPreview,
  isLoggedIn,
  hasWizardAccess,
}: SiteNavProps) {
  // Use client pathname when available, fall back to server pathname for SSR
  const clientPathname = usePathname();
  const pathname = clientPathname ?? initialPathname;

  const { openWizardAccess } = useOnboarding();

  // A sectioned dropdown opens to the right of its trigger; when it would run off the
  // screen it is shifted left by just the overflow.
  const [menuShift, setMenuShift] = useState<Record<string, number>>({});
  function trackMenuShift(
    group: NavGroup,
    event: React.SyntheticEvent<HTMLElement>,
  ): void {
    if (!isSectioned(group)) return;
    const left = event.currentTarget.getBoundingClientRect().left;
    const overflow =
      left + sectionedMenuWidth(window.innerWidth) - (window.innerWidth - 16);
    const shift = overflow > 0 ? -Math.min(overflow, left - 8) : 0;
    setMenuShift((prev) =>
      prev[group.label] === shift ? prev : { ...prev, [group.label]: shift },
    );
  }

  // Suppress hydration mismatch: GlimpseTrigger (Radix HoverCard asChild) renders
  // a different element on SSR vs client. Only pass the preview after mount so that
  // the server and client both render the plain <a> fallback on first render.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time SSR mount flag, not a cascade
    setMounted(true);
  }, []);

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  const itemContext: ItemContext = {
    isActive,
    hasWizardAccess,
    openWizardAccess,
  };

  return (
    <header className="border-border/60 bg-card/95 sticky top-0 z-50 border-b shadow-sm backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 md:px-6 md:py-4">
        {/* Left: Logo */}
        <div className="flex min-w-0 flex-1 items-center">
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
        </div>

        {/* Center: Desktop Navigation */}
        <nav aria-label="Primary" className="hidden min-w-0 shrink md:block">
          <div className="border-border/70 bg-card flex items-center gap-0.5 rounded-full border p-1 shadow-sm lg:gap-1">
            <NavigationMenu>
              <NavigationMenuList>
                {navGroups.map((group, index) => {
                  const isGroupActive = group.items.some((item) =>
                    isActive(item.href),
                  );
                  // Align dropdown: first half opens right, second half opens left
                  const dropdownAlign =
                    index < navGroups.length / 2 ? "start" : "end";
                  return (
                    <NavigationMenuItem key={group.label}>
                      <NavigationMenuTrigger
                        onPointerEnter={(event) => trackMenuShift(group, event)}
                        onFocus={(event) => trackMenuShift(group, event)}
                        className={cn(
                          "h-9 rounded-full bg-transparent px-3 text-sm font-medium whitespace-nowrap transition-colors lg:h-10 lg:px-4",
                          isGroupActive
                            ? "bg-primary/10 text-primary hover:bg-primary/15 data-[state=open]:bg-primary/15"
                            : "hover:bg-muted data-[state=open]:bg-muted",
                        )}
                      >
                        <group.icon className="mr-1.5 h-4 w-4 lg:mr-2" />
                        <span className="hidden lg:inline">{group.label}</span>
                        <span className="lg:hidden">
                          {group.label === "Use Cases"
                            ? "Cases"
                            : group.label === "Software Components"
                              ? "Components"
                              : group.label === "Software Modules"
                                ? "Modules"
                                : group.label === "No-code Assets"
                                  ? "Assets"
                                  : group.label}
                        </span>
                      </NavigationMenuTrigger>
                      <NavigationMenuContent
                        align={isSectioned(group) ? "start" : dropdownAlign}
                        style={
                          isSectioned(group)
                            ? { left: menuShift[group.label] ?? 0 }
                            : undefined
                        }
                      >
                        {isSectioned(group) ? (
                          <SectionedMenu group={group} ctx={itemContext} />
                        ) : (
                          <ul className="grid w-[400px] gap-3 p-4 md:w-[500px] md:grid-cols-2 lg:w-[600px]">
                            {group.items.map((item) => (
                              <DesktopMenuItem
                                key={item.label}
                                item={item}
                                active={isActive(item.href)}
                                hasWizardAccess={hasWizardAccess}
                                openWizardAccess={openWizardAccess}
                              />
                            ))}
                          </ul>
                        )}
                      </NavigationMenuContent>
                    </NavigationMenuItem>
                  );
                })}
              </NavigationMenuList>
            </NavigationMenu>
          </div>
        </nav>

        {/* Right: Actions. min-w-fit keeps them from sliding under the nav. */}
        <div className="flex min-w-0 flex-1 items-center justify-end gap-3 md:min-w-fit">
          <ModelSettingsButton />
          <GitHubLink
            preview={mounted ? githubPreview : null}
            variant="desktop"
          />
          {isLoggedIn && (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-foreground hidden gap-1.5 md:inline-flex"
              onClick={handleSignOut}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          )}
          <MobileNav
            isActive={isActive}
            githubPreview={githubPreview}
            isLoggedIn={isLoggedIn}
            hasWizardAccess={hasWizardAccess}
          />
        </div>
      </div>
    </header>
  );
}
