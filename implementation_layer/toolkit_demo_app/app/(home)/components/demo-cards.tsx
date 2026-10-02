"use client";

import { useHasMounted } from "@/hooks/use-has-mounted";
import {
  type KnowledgeProcess,
  PROCESSES,
  processAnchor,
  processStyle,
} from "@/lib/knowledge-processes";
import { prompts, skills } from "@/lib/no-code/catalog";
import { cn } from "@/lib/utils";
import {
  ArrowUpRight,
  Lock,
  type LucideIcon,
  MessageSquare,
  Wand2,
} from "lucide-react";
import { motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { type ReactNode, useEffect } from "react";
import {
  type ComingSoon,
  comingSoonComponents,
  comingSoonUseCases,
  components,
  type Demo,
  featuredUseCases,
  inProcess,
  modules,
  useCases,
} from "./demo-data";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: "easeOut" as const },
  },
};

interface CardLook {
  tile: string;
  accent: string;
  hoverBorder: string;
}

// Use cases span several processes, so they keep the site's primary colour.
const USE_CASE_LOOK: CardLook = {
  tile: "bg-primary/10 text-primary",
  accent: "text-primary",
  hoverBorder: "hover:border-primary/40",
};

const lookOf = (demo: Demo): CardLook =>
  demo.process ? processStyle(demo.process) : USE_CASE_LOOK;

const cardClassName =
  "group bg-card relative flex h-full flex-col rounded-xl border shadow-xs transition-[border-color,box-shadow] duration-200 hover:shadow-md";

interface DemoCardsProps {
  isUnlocked: boolean;
}

/**
 * A block that fades in with its section once the page has mounted. The first render
 * is static: motion's initial="hidden" (opacity 0) blanks the page on a hard reload
 * with React 19 + Framer Motion v12 (SSR mismatch).
 */
function Reveal({
  animated,
  className,
  id,
  tour,
  children,
}: {
  animated: boolean;
  className?: string;
  id?: string;
  tour?: string;
  children: ReactNode;
}) {
  return animated ? (
    <motion.div
      variants={itemVariants}
      id={id}
      className={className}
      data-tour={tour}
    >
      {children}
    </motion.div>
  ) : (
    <div id={id} className={className} data-tour={tour}>
      {children}
    </div>
  );
}

function IconTile({ icon: Icon, tile }: { icon: LucideIcon; tile: string }) {
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg",
        tile,
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

/** Top-right marker: an arrow to open the demo, or a lock until the user signs in. */
function OpenMarker({ locked }: { locked: boolean }) {
  return locked ? (
    <Lock className="text-muted-foreground size-4 shrink-0" />
  ) : (
    <ArrowUpRight className="text-muted-foreground/60 group-hover:text-foreground size-4 shrink-0 transition-colors" />
  );
}

function FeatureChips({ demo }: { demo: Demo }) {
  if (!demo.featureList) return null;
  return (
    <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
      {demo.featureList.map((feature) => (
        <span
          key={feature.label}
          className="bg-muted/70 text-foreground/75 inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs"
        >
          <feature.icon className={cn("size-3", lookOf(demo).accent)} />
          {feature.label}
        </span>
      ))}
    </div>
  );
}

/** The standard card: icon, title and description, with feature chips if it has any. */
function DemoCard({
  demo,
  isUnlocked,
  showProcess,
}: {
  demo: Demo;
  isUnlocked: boolean;
  showProcess?: boolean;
}) {
  const look = lookOf(demo);
  return (
    <Link
      href={isUnlocked ? demo.href : "/sign-in"}
      title={isUnlocked ? undefined : "Sign in to open"}
      className={cn(cardClassName, "gap-2.5 p-4", look.hoverBorder)}
    >
      <div className="flex items-center gap-3">
        <IconTile icon={demo.icon} tile={look.tile} />
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] leading-snug font-semibold">
            {demo.title}
          </h3>
          {showProcess && demo.process && (
            <p className={cn("text-xs font-medium", look.accent)}>
              {demo.process}
            </p>
          )}
        </div>
        <OpenMarker locked={!isUnlocked} />
      </div>
      <p className="text-muted-foreground text-sm leading-relaxed">
        {demo.description}
      </p>
      <FeatureChips demo={demo} />
    </Link>
  );
}

/** A use case with a screenshot: the image beside the text on wider screens. */
function ImageCard({ demo, isUnlocked }: { demo: Demo; isUnlocked: boolean }) {
  const look = lookOf(demo);
  return (
    <Link
      href={isUnlocked ? demo.href : "/sign-in"}
      title={isUnlocked ? undefined : "Sign in to open"}
      className={cn(
        cardClassName,
        "overflow-hidden sm:flex-row",
        look.hoverBorder,
      )}
    >
      {demo.image && (
        <div className="bg-muted relative h-40 shrink-0 overflow-hidden sm:h-auto sm:w-[42%]">
          <Image
            src={demo.image}
            alt={`${demo.title} demo`}
            fill
            sizes="(min-width: 1024px) 240px, (min-width: 640px) 40vw, 100vw"
            className="object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            style={{ objectPosition: demo.imagePosition || "center" }}
          />
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2.5 p-4 sm:p-5">
        <div className="flex items-center gap-3">
          <IconTile icon={demo.icon} tile={look.tile} />
          <h3 className="min-w-0 flex-1 text-base leading-snug font-semibold">
            {demo.title}
          </h3>
          <OpenMarker locked={!isUnlocked} />
        </div>
        <p className="text-muted-foreground text-sm leading-relaxed">
          {demo.description}
        </p>
        <FeatureChips demo={demo} />
      </div>
    </Link>
  );
}

function ComingSoonLine({ items }: { items: ComingSoon[] }) {
  return (
    <p className="text-muted-foreground text-sm">
      <span className="text-foreground font-medium">Coming soon:</span>{" "}
      {items.map(({ title }) => title).join(" · ")}
    </p>
  );
}

function SectionHeading({
  title,
  intro,
  count,
}: {
  title: string;
  intro: string;
  count: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-1 border-b pb-3">
      <div className="space-y-1">
        <h2 className="font-serif text-2xl font-semibold tracking-tight">
          {title}
        </h2>
        <p className="text-muted-foreground text-sm">{intro}</p>
      </div>
      <span className="text-muted-foreground text-sm">{count}</span>
    </div>
  );
}

function ProcessHeading({
  process,
  count,
  id,
}: {
  process: KnowledgeProcess;
  count: string;
  id?: string;
}) {
  const style = processStyle(process);
  return (
    <div
      id={id}
      className="flex scroll-mt-24 flex-wrap items-center gap-x-2.5 gap-y-0.5 text-sm"
    >
      <style.icon className={cn("size-4", style.accent)} />
      <h3 className={cn("font-semibold", style.accent)}>{style.name}</h3>
      <span className="text-muted-foreground/70 text-xs">{count}</span>
      <span className="text-muted-foreground hidden md:inline">
        · {style.summary}
      </span>
    </div>
  );
}

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

const noCodeLinks: {
  title: string;
  description: string;
  href: string;
  count: number;
  icon: LucideIcon;
}[] = [
  {
    title: "Agent skills",
    description:
      "Download a skill for Claude Desktop or install the plugin in a coding agent.",
    href: "/skills",
    count: skills.length,
    icon: Wand2,
  },
  {
    title: "Prompts",
    description:
      "Copy a prompt into ChatGPT or Claude to extract structured data. Nothing to install.",
    href: "/prompts",
    count: prompts.length,
    icon: MessageSquare,
  },
];

function Sections({
  isUnlocked,
  animated,
}: DemoCardsProps & { animated: boolean }) {
  return (
    <>
      {!isUnlocked && (
        <Reveal
          animated={animated}
          className="bg-muted/50 border-primary/20 flex items-center gap-3 rounded-lg border px-4 py-3"
        >
          <Lock className="text-primary size-4 shrink-0" />
          <p className="text-muted-foreground text-sm">
            <Link href="/sign-in" className="text-primary hover:underline">
              Sign in
            </Link>{" "}
            to access the interactive demos. Don&apos;t have an account?{" "}
            <Link href="/sign-up" className="text-primary hover:underline">
              Sign up
            </Link>
            .
          </p>
        </Reveal>
      )}

      <Reveal
        animated={animated}
        id="use-cases"
        className="scroll-mt-24 space-y-5"
        tour="use-cases"
      >
        <SectionHeading
          title="Use Cases"
          intro="End-to-end applications for real business tasks, built from the modules and components below."
          count={plural(featuredUseCases.length + useCases.length, "demo")}
        />
        <div className="grid gap-4 lg:grid-cols-2">
          {featuredUseCases.map((demo) => (
            <Reveal key={demo.href} animated={animated}>
              <ImageCard demo={demo} isUnlocked={isUnlocked} />
            </Reveal>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {useCases.map((demo) => (
            <Reveal key={demo.href} animated={animated}>
              <DemoCard demo={demo} isUnlocked={isUnlocked} />
            </Reveal>
          ))}
        </div>
        <ComingSoonLine items={comingSoonUseCases} />
      </Reveal>

      <Reveal
        animated={animated}
        id="modules"
        className="scroll-mt-24 space-y-5"
      >
        <SectionHeading
          title="Software Modules"
          intro="Ready-made pipelines that combine several components into one workflow."
          count={plural(modules.length, "module")}
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((demo) => (
            <Reveal key={demo.href} animated={animated}>
              <DemoCard demo={demo} isUnlocked={isUnlocked} showProcess />
            </Reveal>
          ))}
        </div>
      </Reveal>

      <Reveal
        animated={animated}
        id="components"
        className="scroll-mt-24 space-y-5"
        tour="components"
      >
        <SectionHeading
          title="Software Components"
          intro="Single building blocks, each usable on its own from the gaik Python package."
          count={plural(components.length, "component")}
        />
        {PROCESSES.map(({ name }) => {
          const demos = inProcess(components, name);
          if (demos.length === 0) return null;
          return (
            <div key={name} className="space-y-3">
              <ProcessHeading
                process={name}
                count={plural(demos.length, "component")}
                id={processAnchor(name)}
              />
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {demos.map((demo) => (
                  <Reveal key={demo.href} animated={animated}>
                    <DemoCard demo={demo} isUnlocked={isUnlocked} />
                  </Reveal>
                ))}
              </div>
            </div>
          );
        })}
        <ComingSoonLine items={comingSoonComponents} />
      </Reveal>

      <Reveal
        animated={animated}
        id="no-code"
        className="scroll-mt-24 space-y-5"
      >
        <SectionHeading
          title="No-code Assets"
          intro="Use GAIK's extraction know-how without writing code."
          count={plural(skills.length + prompts.length, "asset")}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          {noCodeLinks.map(
            ({ title, description, href, count, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  cardClassName,
                  "hover:border-primary/40 gap-2.5 p-4",
                )}
              >
                <div className="flex items-center gap-3">
                  <IconTile icon={Icon} tile={USE_CASE_LOOK.tile} />
                  <h3 className="min-w-0 flex-1 text-[15px] font-semibold">
                    {title}
                  </h3>
                  <span className="text-muted-foreground text-xs">
                    {count} available
                  </span>
                  <OpenMarker locked={false} />
                </div>
                <p className="text-muted-foreground text-sm leading-relaxed">
                  {description}
                </p>
              </Link>
            ),
          )}
        </div>
      </Reveal>
    </>
  );
}

export function DemoCards({ isUnlocked }: DemoCardsProps) {
  const mounted = useHasMounted();

  // Links from other pages (the footer's /#modules) arrive before this page has
  // rendered, so Next.js cannot scroll to the anchor; do it once the sections exist,
  // and again when the entrance animation has moved them into place.
  useEffect(() => {
    if (!mounted || !window.location.hash) return;
    const target = document.getElementById(window.location.hash.slice(1));
    if (!target) return;
    const frame = requestAnimationFrame(() => target.scrollIntoView());
    const settled = window.setTimeout(() => target.scrollIntoView(), 1000);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settled);
    };
  }, [mounted]);

  if (!mounted) {
    return (
      <section id="demos" className="scroll-mt-24 space-y-14">
        <Sections isUnlocked={isUnlocked} animated={false} />
      </section>
    );
  }

  return (
    <motion.section
      id="demos"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="scroll-mt-24 space-y-14"
    >
      <Sections isUnlocked={isUnlocked} animated />
    </motion.section>
  );
}
