"use client";

import { GitHubIcon } from "@/components/github-icon";
import {
  Glimpse,
  GlimpseContent,
  GlimpseDescription,
  GlimpseImage,
  GlimpseTitle,
  GlimpseTrigger,
} from "@/components/kibo-ui/glimpse";
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
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { GITHUB_REPO_URL, type LinkPreview } from "@/lib/link-previews";
import { cn } from "@/lib/utils";
import {
  AudioWaveform,
  Bot,
  Boxes,
  Cpu,
  Database,
  ExternalLink,
  FileBarChart,
  FileCode,
  FileOutput,
  FileSearch,
  FileText,
  GraduationCap,
  HardHat,
  Headset,
  Lightbulb,
  LogOut,
  LucideIcon,
  Menu,
  MessageSquare,
  Mic,
  Puzzle,
  Scale,
  ScanEye,
  Search,
  ShieldAlert,
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
  external?: boolean;
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
      {
        label: "Solution Wizard",
        href: "/solution-wizard",
        icon: Wand2,
        comingSoon: true,
      },
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
      { label: "Extractor", href: "/extractor", icon: FileSearch },
      { label: "Vision Extractor", href: "/vision-extractor", icon: ScanEye },
      { label: "Parser", href: "/parser", icon: FileText },
      { label: "Classifier", href: "/classifier", icon: Tags },
      { label: "Transcriber", href: "/transcriber", icon: Mic },
      { label: "Text-to-Speech", href: "/text-to-speech", icon: Volume2 },
      { label: "LLM Judge", href: "/llm-judge", icon: Scale },
      {
        label: "PostgreSQL Agent",
        href: "/postgres-agent",
        icon: Database,
      },
      { label: "Retriever", href: "#", icon: Search, comingSoon: true },
      { label: "Embedder", href: "#", icon: Cpu, comingSoon: true },
      { label: "Vector Database", href: "#", icon: Database, comingSoon: true },
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
      },
      {
        label: "Document → Structured",
        href: "/document-structured",
        icon: FileOutput,
      },
      { label: "RAG Builder", href: "/rag", icon: Bot },
      { label: "Report Writer", href: "/report-writer", icon: FileText },
    ],
  },
  {
    label: "No-code Assets",
    icon: FileCode,
    items: [
      {
        label: "Prompts",
        href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/prompts",
        icon: MessageSquare,
        external: true,
      },
      {
        label: "Agent Skills",
        href: "https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/agent-skills",
        icon: Wand2,
        external: true,
      },
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
}

function MobileNav({ isActive, githubPreview, isLoggedIn }: MobileNavProps) {
  const [mounted, setMounted] = useState(false);

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
              <div className="flex flex-col gap-0.5 pl-2">
                {group.items.map((item) => {
                  // Coming Soon items
                  if (item.comingSoon) {
                    return (
                      <div
                        key={item.label}
                        className="text-muted-foreground/60 flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium"
                      >
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
                        key={item.label}
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

                  return (
                    <NavLink
                      key={item.href}
                      {...item}
                      active={isActive(item.href)}
                      variant="mobile"
                    />
                  );
                })}
              </div>
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
}

export function SiteNav({
  pathname: initialPathname,
  githubPreview,
  isLoggedIn,
}: SiteNavProps) {
  // Use client pathname when available, fall back to server pathname for SSR
  const clientPathname = usePathname();
  const pathname = clientPathname ?? initialPathname;

  // Suppress hydration mismatch: GlimpseTrigger (Radix HoverCard asChild) renders
  // a different element on SSR vs client. Only pass the preview after mount so that
  // the server and client both render the plain <a> fallback on first render.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time SSR mount flag, not a cascade
    setMounted(true);
  }, []);

  function isActive(href: string): boolean {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  }

  return (
    <header className="border-border/60 bg-card/95 sticky top-0 z-50 border-b shadow-sm backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center px-4 py-3 md:px-6 md:py-4">
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
                      <NavigationMenuContent align={dropdownAlign}>
                        <ul className="grid w-[400px] gap-3 p-4 md:w-[500px] md:grid-cols-2 lg:w-[600px]">
                          {group.items.map((item) => {
                            const ItemIcon = item.icon;
                            const active = isActive(item.href);

                            // Coming Soon items
                            if (item.comingSoon) {
                              return (
                                <li key={item.label}>
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
                                <li key={item.label}>
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
                              <li key={item.href}>
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
                          })}
                        </ul>
                      </NavigationMenuContent>
                    </NavigationMenuItem>
                  );
                })}
              </NavigationMenuList>
            </NavigationMenu>
          </div>
        </nav>

        {/* Right: Actions */}
        <div className="flex min-w-0 flex-1 items-center justify-end gap-3">
          <GitHubLink preview={mounted ? githubPreview : null} variant="desktop" />
          {isLoggedIn && (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-foreground hidden gap-1.5 lg:inline-flex"
              onClick={handleSignOut}
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
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
